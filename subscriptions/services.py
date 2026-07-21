"""
Thin wrapper around the Stripe SDK.

Every function that talks to Stripe is isolated here so that:
  * views stay readable,
  * the whole payment layer can be mocked in tests, and
  * the backend degrades gracefully when Stripe keys are not configured.

Billing model: one Stripe Price per plan holding the *per-meal* rate, recurring
every 4 weeks. The number of meals in a cycle is the line item's `quantity`, so
changing how many days a customer eats is a quantity update, not a new price.

The first cycle is charged at checkout, before any deliveries. A customer who
cancels keeps the meals for the cycle they have already paid for, so money is
never held against food that will not be delivered.
"""
import stripe
from django.conf import settings

from rest_framework.exceptions import APIException


class StripeNotConfigured(APIException):
    status_code = 503
    default_detail = (
        "Payments are not configured on this server. "
        "Set STRIPE_SECRET_KEY (and STRIPE_WEBHOOK_SECRET) in the environment."
    )
    default_code = "stripe_not_configured"


def stripe_enabled() -> bool:
    return bool(settings.STRIPE_SECRET_KEY)


def _client():
    if not stripe_enabled():
        raise StripeNotConfigured()
    stripe.api_key = settings.STRIPE_SECRET_KEY
    return stripe


def get_or_create_customer(profile, email, name):
    """Return a Stripe customer id, creating (and caching) one if needed."""
    client = _client()
    if profile.stripe_customer_id:
        return profile.stripe_customer_id
    customer = client.Customer.create(email=email, name=name)
    profile.stripe_customer_id = customer["id"]
    profile.save(update_fields=["stripe_customer_id"])
    return customer["id"]


def create_checkout_session(*, customer_id, price_id, quantity, metadata):
    """Checkout that charges the first full cycle immediately.

    No trial: the customer pays for cycle one at checkout, so a dead card fails
    here rather than on the morning of the first delivery. Stripe therefore
    anchors the billing period to checkout time, a day or so ahead of the
    delivery period -- deliveries are scheduled locally from
    `first_delivery_date` and are unaffected by that offset.
    """
    client = _client()
    session = client.checkout.Session.create(
        mode="subscription",
        customer=customer_id,
        line_items=[{"price": price_id, "quantity": quantity}],
        success_url=settings.CHECKOUT_SUCCESS_URL,
        cancel_url=settings.CHECKOUT_CANCEL_URL,
        metadata=metadata,
        subscription_data={"metadata": metadata},
    )
    return session["url"]


def _subscription_item(client, stripe_subscription_id):
    sub = client.Subscription.retrieve(stripe_subscription_id)
    return sub, sub["items"]["data"][0]


def preview_change(*, stripe_subscription_id, new_price_id=None, new_quantity=None):
    """Prorated amount for a price and/or quantity change, without charging."""
    client = _client()
    sub, item = _subscription_item(client, stripe_subscription_id)
    change = {"id": item["id"]}
    if new_price_id:
        change["price"] = new_price_id
    if new_quantity is not None:
        change["quantity"] = new_quantity

    upcoming = client.Invoice.upcoming(
        customer=sub["customer"],
        subscription=stripe_subscription_id,
        subscription_items=[change],
        subscription_proration_behavior="create_prorations",
    )
    return {
        "amount_due": upcoming["amount_due"] / 100,
        "currency": upcoming["currency"],
    }


def apply_change(*, stripe_subscription_id, new_price_id=None, new_quantity=None):
    """Switch plan and/or meal count, prorating against the current cycle."""
    client = _client()
    _, item = _subscription_item(client, stripe_subscription_id)
    change = {"id": item["id"]}
    if new_price_id:
        change["price"] = new_price_id
    if new_quantity is not None:
        change["quantity"] = new_quantity

    return client.Subscription.modify(
        stripe_subscription_id,
        items=[change],
        proration_behavior="create_prorations",
    )


def cancel_at_period_end(*, stripe_subscription_id):
    client = _client()
    return client.Subscription.modify(
        stripe_subscription_id, cancel_at_period_end=True
    )


def construct_event(payload, sig_header):
    """Verify the webhook signature and return the parsed event."""
    if not settings.STRIPE_WEBHOOK_SECRET:
        raise StripeNotConfigured()
    stripe.api_key = settings.STRIPE_SECRET_KEY
    return stripe.Webhook.construct_event(
        payload, sig_header, settings.STRIPE_WEBHOOK_SECRET
    )
