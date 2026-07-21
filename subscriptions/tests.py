from datetime import date, timedelta
from decimal import Decimal
from itertools import combinations
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth.models import User
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import CustomerProfile
from menu.models import Category
from plans.models import Plan
from subscriptions import services, webhooks
from subscriptions.models import (
    WEEKDAYS,
    Invoice,
    Subscription,
    WebhookEvent,
    first_delivery_on_or_after,
)

LEAD = settings.MIN_START_LEAD_DAYS


def make_plan(slug="standard", name="Standard", price="40.00", **overrides):
    cat, _ = Category.objects.get_or_create(slug=slug, defaults={"name": name})
    defaults = dict(category=cat, name=name, price_per_meal=Decimal(price),
                    stripe_price_id=f"price_{slug}")
    defaults.update(overrides)
    return Plan.objects.create(**defaults)


def a_start_date(days=7):
    return date.today() + timedelta(days=days)


class CycleArithmeticTests(APITestCase):
    """The 28-day invariant everything else depends on."""

    def setUp(self):
        Category.objects.all().delete()
        self.plan = make_plan()

    def test_every_cycle_holds_four_of_each_weekday(self):
        """Whatever the start day and day selection, meals == 4 x days chosen."""
        sub = Subscription(plan=self.plan, start_date=date.today())
        for start_offset in range(7):  # every possible starting weekday
            start = date(2026, 7, 20) + timedelta(days=start_offset)
            for size in range(1, 8):
                for days in combinations(WEEKDAYS, size):
                    sub.delivery_days = list(days)
                    sub.start_date = start
                    dates = sub.delivery_dates()
                    self.assertEqual(
                        len(dates), 4 * size,
                        f"start={start} days={days} gave {len(dates)}",
                    )

    def test_mid_week_start_thursday_friday(self):
        """The worked example: Wed 22 Jul 2026 start, Thu + Fri, Standard."""
        sub = Subscription(plan=self.plan, start_date=date(2026, 7, 22),
                           delivery_days=["thu", "fri"])
        self.assertEqual(date(2026, 7, 22).strftime("%A"), "Wednesday")
        self.assertEqual(sub.meals_per_week, 2)
        self.assertEqual(sub.meals_per_cycle, 8)
        self.assertEqual(sub.price_per_cycle, Decimal("320.00"))
        # Billing anchors on the first delivery, not the start date.
        self.assertEqual(sub.first_delivery_date, date(2026, 7, 23))
        dates = sub.delivery_dates()
        self.assertEqual(len(dates), 8)
        self.assertEqual(dates[0], date(2026, 7, 23))
        self.assertEqual(dates[-1], date(2026, 8, 14))

    def test_first_delivery_is_start_date_when_it_matches(self):
        # 20 Jul 2026 is a Monday and "mon" is selected, so no shifting.
        self.assertEqual(
            first_delivery_on_or_after(date(2026, 7, 20), ["mon", "thu"]),
            date(2026, 7, 20),
        )

    def test_first_delivery_never_more_than_six_days_out(self):
        for offset in range(7):
            start = date(2026, 7, 20) + timedelta(days=offset)
            first = first_delivery_on_or_after(start, ["sun"])
            self.assertLessEqual((first - start).days, 6)
            self.assertGreaterEqual((first - start).days, 0)

    def test_price_scales_with_days_only(self):
        """Which days are chosen never changes the price; how many does."""
        a = Subscription(plan=self.plan, start_date=date.today(),
                         delivery_days=["thu", "fri"])
        b = Subscription(plan=self.plan, start_date=date.today(),
                         delivery_days=["mon", "sat"])
        self.assertEqual(a.price_per_cycle, b.price_per_cycle)
        self.assertEqual(a.price_per_cycle, Decimal("320.00"))


class CheckoutBillingTests(APITestCase):
    """The first cycle is charged at checkout, not deferred to the first delivery."""

    def setUp(self):
        Category.objects.all().delete()
        self.plan = make_plan()

    @patch("subscriptions.services.stripe")
    @patch("subscriptions.services.stripe_enabled", return_value=True)
    def test_checkout_session_sends_no_trial(self, m_enabled, m_stripe):
        m_stripe.checkout.Session.create.return_value = {"url": "https://stripe.test/s"}
        services.create_checkout_session(
            customer_id="cus_1", price_id="price_standard", quantity=12,
            metadata={"plan_id": "1"},
        )
        kwargs = m_stripe.checkout.Session.create.call_args.kwargs
        sub_data = kwargs["subscription_data"]
        self.assertNotIn("trial_end", sub_data)
        self.assertNotIn("trial_settings", sub_data)
        self.assertEqual(kwargs["line_items"][0]["quantity"], 12)


class QuoteTests(APITestCase):
    def setUp(self):
        Category.objects.all().delete()
        self.plan = make_plan()

    def test_quote_math(self):
        res = self.client.post(reverse("checkout-quote"), {
            "plan_id": self.plan.id, "delivery_days": ["thu", "fri"],
            "start_date": a_start_date().isoformat(),
        }, format="json")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["meals_per_week"], 2)
        self.assertEqual(res.data["meals_per_cycle"], 8)
        self.assertEqual(res.data["price_per_cycle"], "320.00")

    def test_quote_rejects_bad_day(self):
        res = self.client.post(reverse("checkout-quote"), {
            "plan_id": self.plan.id, "delivery_days": ["funday"],
        }, format="json")
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)


class DeliveryDayValidationTests(APITestCase):
    def setUp(self):
        Category.objects.all().delete()
        self.plan = make_plan()

    def _post(self, days):
        return self.client.post(reverse("checkout-quote"), {
            "plan_id": self.plan.id, "delivery_days": days,
        }, format="json")

    def test_rejects_duplicates(self):
        self.assertEqual(self._post(["mon", "mon"]).status_code, 400)

    def test_rejects_more_than_seven(self):
        self.assertEqual(self._post(WEEKDAYS + ["mon"]).status_code, 400)

    def test_rejects_empty(self):
        self.assertEqual(self._post([]).status_code, 400)

    def test_accepts_all_seven(self):
        res = self._post(WEEKDAYS)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["meals_per_cycle"], 28)

    def test_normalises_case_and_order(self):
        res = self._post(["FRI", "Mon"])
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["meals_per_cycle"], 8)


class CheckoutTests(APITestCase):
    def setUp(self):
        Category.objects.all().delete()
        self.plan = make_plan()
        self.start = a_start_date().isoformat()

    def _payload(self, **overrides):
        data = {
            "plan_id": self.plan.id,
            "start_date": self.start,
            "delivery_days": ["mon", "wed", "fri"],
            "name": "Omar Ali",
            "email": "omar@example.com",
            "phone": "+971500000001",
            "delivery_address": "5 JBR, Dubai",
            "password": "SuperSecret123",
            "confirm_password": "SuperSecret123",
        }
        data.update(overrides)
        return data

    @patch("subscriptions.services.create_checkout_session", return_value="https://stripe.test/session")
    @patch("subscriptions.services.get_or_create_customer", return_value="cus_123")
    def test_anonymous_checkout_creates_account(self, m_cust, m_sess):
        res = self.client.post(reverse("checkout-create-session"), self._payload(), format="json")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["checkout_url"], "https://stripe.test/session")
        self.assertIn("tokens", res.data)
        self.assertTrue(User.objects.filter(username="omar@example.com").exists())

    @patch("subscriptions.services.create_checkout_session", return_value="https://stripe.test/session")
    @patch("subscriptions.services.get_or_create_customer", return_value="cus_123")
    def test_quantity_sent_to_stripe_is_meals_per_cycle(self, m_cust, m_sess):
        self.client.post(reverse("checkout-create-session"), self._payload(), format="json")
        kwargs = m_sess.call_args.kwargs
        self.assertEqual(kwargs["quantity"], 12)  # 3 days x 4 weeks
        self.assertEqual(kwargs["price_id"], "price_standard")
        self.assertEqual(kwargs["metadata"]["delivery_days"], '["mon", "wed", "fri"]')

    @patch("subscriptions.services.create_checkout_session", return_value="https://stripe.test/session")
    @patch("subscriptions.services.get_or_create_customer", return_value="cus_123")
    def test_response_carries_the_cycle_price(self, m_cust, m_sess):
        res = self.client.post(reverse("checkout-create-session"), self._payload(), format="json")
        self.assertEqual(res.data["meals_per_cycle"], 12)
        self.assertEqual(res.data["price_per_cycle"], "480.00")

    def test_start_date_inside_lead_time_rejected(self):
        too_soon = (date.today() + timedelta(days=LEAD - 1)).isoformat()
        res = self.client.post(reverse("checkout-create-session"),
                               self._payload(start_date=too_soon), format="json")
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("start_date", res.data)

    def test_plan_without_stripe_price_rejected(self):
        Plan.objects.filter(id=self.plan.id).update(stripe_price_id="")
        res = self.client.post(reverse("checkout-create-session"),
                               self._payload(), format="json")
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_anonymous_checkout_requires_account_fields(self):
        payload = self._payload()
        del payload["password"]
        del payload["confirm_password"]
        res = self.client.post(reverse("checkout-create-session"), payload, format="json")
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    @patch("subscriptions.services.create_checkout_session", return_value="https://stripe.test/session")
    @patch("subscriptions.services.get_or_create_customer", return_value="cus_123")
    def test_authenticated_checkout_skips_account_creation(self, m_cust, m_sess):
        user = User.objects.create_user(username="ret@example.com", email="ret@example.com",
                                        password="SuperSecret123")
        CustomerProfile.objects.create(user=user, phone="+9715", delivery_address="x")
        self.client.force_authenticate(user=user)
        res = self.client.post(
            reverse("checkout-create-session"),
            {"plan_id": self.plan.id, "start_date": self.start,
             "delivery_days": ["mon", "tue"]},
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertNotIn("tokens", res.data)


class DashboardTests(APITestCase):
    def setUp(self):
        Category.objects.all().delete()
        self.user = User.objects.create_user(username="c@example.com", email="c@example.com",
                                             password="SuperSecret123")
        self.profile = CustomerProfile.objects.create(user=self.user, phone="+9715",
                                                      delivery_address="x")
        self.plan = make_plan()
        self.sub = Subscription.objects.create(
            customer=self.profile, plan=self.plan, stripe_subscription_id="sub_1",
            delivery_days=["mon", "wed", "fri"], start_date=a_start_date(),
            status="active",
        )
        self.client.force_authenticate(user=self.user)

    def test_my_subscription(self):
        res = self.client.get(reverse("subscription-me"))
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["id"], self.sub.id)
        self.assertEqual(res.data["meals_per_cycle"], 12)
        self.assertEqual(res.data["price_per_cycle"], "480.00")

    def test_my_subscription_none(self):
        Subscription.objects.all().delete()
        res = self.client.get(reverse("subscription-me"))
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)

    def test_deliveries_endpoint_lists_the_cycle(self):
        res = self.client.get(reverse("subscription-deliveries", args=[self.sub.id]))
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(len(res.data["dates"]), 12)

    def test_invoices_list_scoped_to_owner(self):
        Invoice.objects.create(subscription=self.sub, stripe_invoice_id="in_1",
                               amount=Decimal("480.00"), status="paid")
        res = self.client.get(reverse("subscription-invoices", args=[self.sub.id]))
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(len(res.data), 1)

    def test_cannot_see_others_subscription(self):
        other = User.objects.create_user(username="o@example.com", password="x")
        self.client.force_authenticate(user=other)
        res = self.client.get(reverse("subscription-me"))
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)

    @patch("subscriptions.services.preview_change",
           return_value={"amount_due": Decimal("55.00"), "currency": "aed"})
    def test_change_plan_preview(self, m_prev):
        new_plan = make_plan(slug="protein-power", name="Protein Power", price="75.00")
        res = self.client.post(
            reverse("subscription-change-plan", args=[self.sub.id]),
            {"new_plan_id": new_plan.id, "preview": True},
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertTrue(res.data["preview"])
        self.assertEqual(m_prev.call_args.kwargs["new_price_id"], "price_protein-power")

    @patch("subscriptions.services.apply_change", return_value={})
    def test_change_plan_confirm(self, m_change):
        new_plan = make_plan(slug="protein-power", name="Protein Power", price="75.00")
        res = self.client.post(
            reverse("subscription-change-plan", args=[self.sub.id]),
            {"new_plan_id": new_plan.id, "preview": False},
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.sub.refresh_from_db()
        self.assertEqual(self.sub.plan_id, new_plan.id)

    @patch("subscriptions.services.apply_change", return_value={})
    def test_change_delivery_days_updates_quantity(self, m_change):
        res = self.client.post(
            reverse("subscription-delivery-days", args=[self.sub.id]),
            {"delivery_days": ["mon", "tue", "wed", "thu", "fri"]},
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(m_change.call_args.kwargs["new_quantity"], 20)
        self.sub.refresh_from_db()
        self.assertEqual(self.sub.meals_per_cycle, 20)

    @patch("subscriptions.services.apply_change", return_value={})
    def test_same_day_count_does_not_touch_stripe(self, m_change):
        res = self.client.post(
            reverse("subscription-delivery-days", args=[self.sub.id]),
            {"delivery_days": ["tue", "thu", "sat"]},  # still 3 days
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        m_change.assert_not_called()
        self.sub.refresh_from_db()
        self.assertEqual(self.sub.delivery_days, ["tue", "thu", "sat"])

    @patch("subscriptions.services.cancel_at_period_end", return_value={})
    def test_cancel_sets_flag(self, m_cancel):
        res = self.client.post(reverse("subscription-cancel", args=[self.sub.id]))
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.sub.refresh_from_db()
        self.assertTrue(self.sub.cancel_at_period_end)


class WebhookHandlerTests(APITestCase):
    def setUp(self):
        Category.objects.all().delete()
        self.user = User.objects.create_user(username="w@example.com", email="w@example.com",
                                             password="x")
        self.profile = CustomerProfile.objects.create(user=self.user, phone="+9715",
                                                      delivery_address="x")
        self.plan = make_plan()

    def _sub(self, stripe_id, days=("mon", "tue")):
        return Subscription.objects.create(
            customer=self.profile, plan=self.plan, stripe_subscription_id=stripe_id,
            delivery_days=list(days), start_date=a_start_date())

    def test_checkout_completed_creates_scheduled_subscription(self):
        webhooks.dispatch("checkout.session.completed", {
            "subscription": "sub_new",
            "metadata": {
                "customer_profile_id": str(self.profile.id),
                "plan_id": str(self.plan.id),
                "start_date": a_start_date().isoformat(),
                "delivery_days": '["mon","thu"]',
            },
        })
        sub = Subscription.objects.get(stripe_subscription_id="sub_new")
        self.assertEqual(sub.delivery_days, ["mon", "thu"])
        self.assertEqual(sub.status, "scheduled")
        self.assertEqual(sub.meals_per_cycle, 8)

    def test_invoice_paid_records_and_activates_once_delivering(self):
        sub = self._sub("sub_x")
        # Well in the past, so the first delivery has landed whatever weekday
        # today happens to be.
        Subscription.objects.filter(id=sub.id).update(
            start_date=date.today() - timedelta(days=30))
        webhooks.dispatch("invoice.paid", {
            "id": "in_9", "subscription": "sub_x", "amount_paid": 32000,
            "status_transitions": {"paid_at": 1700000000},
            "period_end": 1700600000,
        })
        inv = Invoice.objects.get(stripe_invoice_id="in_9")
        self.assertEqual(inv.status, "paid")
        self.assertEqual(inv.amount, Decimal("320.00"))
        self.assertEqual(Subscription.objects.get(stripe_subscription_id="sub_x").status,
                         "active")

    def test_invoice_paid_before_first_delivery_stays_scheduled(self):
        """Paying at checkout must not make a not-yet-delivering plan "active"."""
        self._sub("sub_early")  # start_date is a week out
        webhooks.dispatch("invoice.paid", {
            "id": "in_e", "subscription": "sub_early", "amount_paid": 32000,
            "status_transitions": {"paid_at": 1700000000},
        })
        self.assertTrue(Invoice.objects.filter(stripe_invoice_id="in_e").exists())
        self.assertEqual(
            Subscription.objects.get(stripe_subscription_id="sub_early").status,
            "scheduled",
        )

    def test_stripe_active_before_first_delivery_stays_scheduled(self):
        self._sub("sub_a")  # start_date is a week out
        webhooks.dispatch("customer.subscription.updated",
                          {"id": "sub_a", "status": "active"})
        self.assertEqual(Subscription.objects.get(stripe_subscription_id="sub_a").status,
                         "scheduled")

    def test_invoice_paid_new_api_shape(self):
        """2025+ moved the subscription id under invoice.parent."""
        self._sub("sub_new_shape")
        webhooks.dispatch("invoice.paid", {
            "id": "in_new", "amount_paid": 32000,
            "parent": {"subscription_details": {"subscription": "sub_new_shape"}},
            "status_transitions": {"paid_at": 1700000000},
        })
        self.assertTrue(Invoice.objects.filter(stripe_invoice_id="in_new").exists())

    def _checkout_meta(self, days='["mon","thu"]'):
        return {
            "customer_profile_id": str(self.profile.id),
            "plan_id": str(self.plan.id),
            "start_date": a_start_date().isoformat(),
            "delivery_days": days,
        }

    def test_invoice_paid_arriving_before_checkout_completed(self):
        """Stripe sent invoice.paid 23ms *before* checkout.session.completed.

        The payment must not be dropped just because the subscription row does
        not exist yet.
        """
        meta = self._checkout_meta()
        webhooks.dispatch("invoice.paid", {
            "id": "in_race", "amount_paid": 56000,
            "parent": {"subscription_details": {"subscription": "sub_race",
                                                "metadata": meta}},
            "status_transitions": {"paid_at": 1700000000},
        })
        sub = Subscription.objects.get(stripe_subscription_id="sub_race")
        self.assertEqual(sub.delivery_days, ["mon", "thu"])
        inv = Invoice.objects.get(stripe_invoice_id="in_race")
        self.assertEqual(inv.amount, Decimal("560.00"))
        self.assertEqual(inv.subscription_id, sub.id)

        # ...and the late checkout event must not duplicate or clobber it.
        webhooks.dispatch("checkout.session.completed",
                          {"subscription": "sub_race", "metadata": meta})
        self.assertEqual(
            Subscription.objects.filter(stripe_subscription_id="sub_race").count(), 1)
        self.assertEqual(Invoice.objects.filter(stripe_invoice_id="in_race").count(), 1)

    def test_invoice_paid_ignored_when_metadata_is_unusable(self):
        """No metadata and no existing row: nothing to attach the payment to."""
        webhooks.dispatch("invoice.paid", {
            "id": "in_orphan", "subscription": "sub_unknown", "amount_paid": 100})
        self.assertFalse(Invoice.objects.filter(stripe_invoice_id="in_orphan").exists())

    def test_payment_failed_sets_past_due(self):
        self._sub("sub_y")
        webhooks.dispatch("invoice.payment_failed", {
            "id": "in_f", "subscription": "sub_y", "amount_due": 32000})
        self.assertEqual(Subscription.objects.get(stripe_subscription_id="sub_y").status,
                         "past_due")

    def test_trialing_maps_to_scheduled(self):
        self._sub("sub_t")
        webhooks.dispatch("customer.subscription.updated",
                          {"id": "sub_t", "status": "trialing"})
        self.assertEqual(Subscription.objects.get(stripe_subscription_id="sub_t").status,
                         "scheduled")

    def test_subscription_period_end_from_items(self):
        """2025+ moved current_period_end onto the subscription items."""
        self._sub("sub_items")
        webhooks.dispatch("customer.subscription.updated", {
            "id": "sub_items", "status": "active",
            "items": {"data": [{"current_period_end": 1700600000}]},
        })
        sub = Subscription.objects.get(stripe_subscription_id="sub_items")
        self.assertIsNotNone(sub.current_period_end)

    def test_subscription_deleted_cancels(self):
        self._sub("sub_z")
        webhooks.dispatch("customer.subscription.deleted", {"id": "sub_z"})
        self.assertEqual(Subscription.objects.get(stripe_subscription_id="sub_z").status,
                         "canceled")

    @patch("subscriptions.services.construct_event")
    def test_webhook_endpoint_idempotent(self, m_construct):
        m_construct.return_value = {
            "id": "evt_1", "type": "customer.subscription.deleted",
            "data": {"object": {"id": "sub_none"}},
        }
        url = reverse("stripe-webhook")
        r1 = self.client.post(url, data=b"{}", content_type="application/json",
                              HTTP_STRIPE_SIGNATURE="sig")
        r2 = self.client.post(url, data=b"{}", content_type="application/json",
                              HTTP_STRIPE_SIGNATURE="sig")
        self.assertEqual(r1.status_code, status.HTTP_200_OK)
        self.assertEqual(r2.status_code, status.HTTP_200_OK)
        self.assertEqual(WebhookEvent.objects.filter(stripe_event_id="evt_1").count(), 1)

    @patch("subscriptions.services.construct_event", side_effect=ValueError("bad sig"))
    def test_webhook_bad_signature_rejected(self, m_construct):
        res = self.client.post(reverse("stripe-webhook"), data=b"{}",
                               content_type="application/json", HTTP_STRIPE_SIGNATURE="x")
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
