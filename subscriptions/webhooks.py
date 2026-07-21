"""Stripe webhook event handlers. Kept separate from the view for testability."""
import json
from datetime import date, datetime, timezone
from decimal import Decimal

from django.utils.timezone import localdate

from accounts.models import CustomerProfile
from plans.models import Plan

from .models import Invoice, Subscription


def _ts_to_dt(ts):
    if ts is None:
        return None
    return datetime.fromtimestamp(ts, tz=timezone.utc)


def _paid_status(sub):
    """"active" once deliveries have begun, "scheduled" while they are pending.

    The first cycle is paid at checkout, days before the first delivery, so a
    paid subscription is not necessarily a delivering one.
    """
    first = sub.first_delivery_date
    if first is None or first <= localdate():
        return "active"
    return "scheduled"


def _invoice_subscription_id(obj):
    """Subscription id on an invoice, across Stripe API versions.

    <= 2025-02-24 exposes `invoice.subscription`; later versions moved it to
    `invoice.parent.subscription_details.subscription`, with the line items as
    a final fallback.
    """
    sub = obj.get("subscription")
    if isinstance(sub, dict):
        sub = sub.get("id")
    if sub:
        return sub
    parent = obj.get("parent") or {}
    details = parent.get("subscription_details") or {}
    sub = details.get("subscription")
    if isinstance(sub, dict):
        sub = sub.get("id")
    if sub:
        return sub
    for line in obj.get("lines", {}).get("data", []):
        sub = line.get("subscription") or (
            line.get("parent", {}).get("subscription_item_details", {}).get("subscription")
        )
        if isinstance(sub, dict):
            sub = sub.get("id")
        if sub:
            return sub
    return ""


def _invoice_metadata(obj):
    """Subscription metadata carried on an invoice, across Stripe API versions."""
    parent = obj.get("parent") or {}
    details = parent.get("subscription_details") or {}
    if details.get("metadata"):
        return details["metadata"]
    return obj.get("subscription_details", {}).get("metadata") or {}


def _start_date(meta):
    """Metadata is strings over the wire; the model and cycle maths need a date."""
    raw = meta.get("start_date")
    if isinstance(raw, date) or raw is None:
        return raw
    try:
        return date.fromisoformat(raw)
    except ValueError:
        return None


def _delivery_days(meta):
    """Metadata values are strings over the wire, so the list arrives as JSON."""
    days = meta.get("delivery_days", [])
    if not isinstance(days, str):
        return days
    try:
        return json.loads(days)
    except ValueError:
        return [d for d in days.split(",") if d]


def _upsert_subscription(stripe_sub_id, meta):
    """Create or update the local Subscription from an event's metadata.

    `checkout.session.completed` and `invoice.paid` carry the same metadata and
    arrive within milliseconds of each other now that the first cycle is charged
    at checkout -- in testing the invoice won by 23ms. Stripe guarantees no
    ordering, so either event must be able to create the row; whichever loses
    the race just updates it.
    """
    if not stripe_sub_id:
        return None
    profile = CustomerProfile.objects.filter(id=meta.get("customer_profile_id")).first()
    plan = Plan.objects.filter(id=meta.get("plan_id")).first()
    start_date = _start_date(meta)
    if not (profile and plan and start_date):
        return None
    # `status` is deliberately not in defaults: it belongs to whichever handler
    # knows about payment, and must survive the other one arriving later.
    sub, _ = Subscription.objects.update_or_create(
        stripe_subscription_id=stripe_sub_id,
        defaults={
            "customer": profile,
            "plan": plan,
            "delivery_days": _delivery_days(meta),
            "start_date": start_date,
        },
    )
    return sub


def _invoice_period_end(obj):
    """Current period end for an invoice, across Stripe API versions.

    The line items are authoritative, not the invoice's own `period_end`: on a
    subscription's first invoice Stripe sets the invoice period to the instant
    it was created (period_start == period_end), while the line carries the real
    cycle boundary. Reading the invoice field first stored a period end that had
    already passed.
    """
    ends = [
        line.get("period", {}).get("end")
        for line in obj.get("lines", {}).get("data", [])
        if line.get("period", {}).get("end")
    ]
    if ends:
        return _ts_to_dt(max(ends))
    return _ts_to_dt(obj.get("period_end"))


def _subscription_period_end(obj):
    """`current_period_end` moved onto the items in 2025-03-31 and later."""
    ts = obj.get("current_period_end")
    if not ts:
        ends = [
            item.get("current_period_end")
            for item in obj.get("items", {}).get("data", [])
            if item.get("current_period_end")
        ]
        ts = max(ends) if ends else None
    return _ts_to_dt(ts)


def handle_checkout_completed(obj):
    """Create the local Subscription once Stripe confirms checkout.

    New rows default to "scheduled": paid, but the first delivery is still at
    least MIN_START_LEAD_DAYS away. `_paid_status` promotes them once it lands.
    """
    stripe_sub_id = obj.get("subscription") or ""
    if isinstance(stripe_sub_id, dict):  # expanded object
        stripe_sub_id = stripe_sub_id.get("id", "")
    _upsert_subscription(stripe_sub_id, obj.get("metadata", {}))


def handle_invoice_paid(obj):
    stripe_sub_id = _invoice_subscription_id(obj)
    sub = Subscription.objects.filter(stripe_subscription_id=stripe_sub_id).first()
    if sub is None:
        # The invoice beat checkout.session.completed. It carries the same
        # metadata, so create the row rather than dropping a real payment.
        sub = _upsert_subscription(stripe_sub_id, _invoice_metadata(obj))
    if sub is None:
        return
    Invoice.objects.update_or_create(
        stripe_invoice_id=obj.get("id", ""),
        defaults={
            "subscription": sub,
            "amount": Decimal(str(obj.get("amount_paid", 0) / 100)),
            "status": "paid",
            "paid_at": _ts_to_dt(obj.get("status_transitions", {}).get("paid_at")),
        },
    )
    period_end = _invoice_period_end(obj)
    if period_end:
        sub.current_period_end = period_end
    sub.status = _paid_status(sub)
    sub.save(update_fields=["current_period_end", "status"])


def handle_invoice_payment_failed(obj):
    sub = Subscription.objects.filter(
        stripe_subscription_id=_invoice_subscription_id(obj)
    ).first()
    if not sub:
        return
    Invoice.objects.update_or_create(
        stripe_invoice_id=obj.get("id", ""),
        defaults={
            "subscription": sub,
            "amount": Decimal(str(obj.get("amount_due", 0) / 100)),
            "status": "failed",
        },
    )
    sub.status = "past_due"
    sub.save(update_fields=["status"])


def handle_subscription_updated(obj):
    sub = Subscription.objects.filter(
        stripe_subscription_id=obj.get("id", "")
    ).first()
    if not sub:
        return
    status_map = {"active": "active", "past_due": "past_due",
                  "canceled": "canceled", "unpaid": "past_due",
                  "trialing": "scheduled", "incomplete": "scheduled"}
    mapped = status_map.get(obj.get("status"), sub.status)
    if mapped == "active":
        # Stripe calls it active the moment checkout is paid, which is days
        # before the first delivery.
        mapped = _paid_status(sub)
    sub.status = mapped
    sub.cancel_at_period_end = bool(obj.get("cancel_at_period_end"))
    cpe = _subscription_period_end(obj)
    if cpe:
        sub.current_period_end = cpe
    sub.save(update_fields=["status", "cancel_at_period_end", "current_period_end"])


def handle_subscription_deleted(obj):
    sub = Subscription.objects.filter(
        stripe_subscription_id=obj.get("id", "")
    ).first()
    if not sub:
        return
    sub.status = "canceled"
    sub.save(update_fields=["status"])


HANDLERS = {
    "checkout.session.completed": handle_checkout_completed,
    "invoice.paid": handle_invoice_paid,
    "invoice.payment_failed": handle_invoice_payment_failed,
    "customer.subscription.updated": handle_subscription_updated,
    "customer.subscription.deleted": handle_subscription_deleted,
}


def dispatch(event_type, data_object):
    handler = HANDLERS.get(event_type)
    if handler:
        handler(data_object)
        return True
    return False
