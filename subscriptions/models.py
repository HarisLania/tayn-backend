from datetime import timedelta

from django.db import models

from accounts.models import CustomerProfile
from plans.models import Plan

# Weekday codes used by `Subscription.delivery_days`, indexed to match
# `datetime.date.weekday()` (Monday == 0).
WEEKDAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


class Subscription(models.Model):
    """A recurring meal subscription billed per meal, every 4 weeks.

    A cycle is 28 days == exactly 4 weeks, so it always contains exactly four
    of each weekday no matter which day it starts on. That makes the meal count
    -- and therefore the charge -- identical for every cycle:

        meals_per_cycle = 4 * len(delivery_days)
        charge          = plan.price_per_meal * meals_per_cycle

    Which days were chosen never affects the price, only the schedule, so it is
    kept here rather than being pushed to Stripe.
    """

    STATUS_CHOICES = [
        ("scheduled", "Scheduled"),  # paid for, deliveries not started yet
        ("active", "Active"),
        ("past_due", "Past Due"),
        ("canceled", "Canceled"),
    ]
    CYCLE_WEEKS = 4
    CYCLE_DAYS = CYCLE_WEEKS * 7

    customer = models.ForeignKey(
        CustomerProfile, on_delete=models.CASCADE, related_name="subscriptions"
    )
    plan = models.ForeignKey(Plan, on_delete=models.PROTECT)
    stripe_subscription_id = models.CharField(max_length=255, blank=True)
    delivery_days = models.JSONField(default=list)  # e.g. ["mon","wed","fri"]
    start_date = models.DateField()
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default="scheduled")
    current_period_end = models.DateTimeField(null=True, blank=True)
    cancel_at_period_end = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Subscription<{self.customer_id}:{self.plan.name}:{self.status}>"

    @property
    def meals_per_week(self):
        return len(self.delivery_days)

    @property
    def meals_per_cycle(self):
        """Stripe line-item quantity: one meal per delivery day, four weeks."""
        return self.meals_per_week * self.CYCLE_WEEKS

    @property
    def price_per_cycle(self):
        return self.plan.price_per_meal * self.meals_per_cycle

    @property
    def first_delivery_date(self):
        return first_delivery_on_or_after(self.start_date, self.delivery_days)

    def delivery_dates(self, cycle_start=None):
        """Every delivery date in the 28 days from `cycle_start`.

        Defaults to the first cycle. Always returns `meals_per_cycle` dates.
        """
        start = cycle_start or self.first_delivery_date
        if start is None:
            return []
        wanted = {WEEKDAYS.index(d) for d in self.delivery_days}
        return [
            day
            for i in range(self.CYCLE_DAYS)
            for day in [start + timedelta(days=i)]
            if day.weekday() in wanted
        ]


def first_delivery_on_or_after(start_date, delivery_days):
    """First chosen weekday falling on or after `start_date`.

    Billing is anchored here rather than to `start_date` so that the charge date
    is always a delivery date -- a customer starting Wednesday who only picked
    Thursdays is charged on the Thursday, not a day early.
    """
    if not delivery_days:
        return None
    wanted = {WEEKDAYS.index(d) for d in delivery_days}
    for i in range(7):
        day = start_date + timedelta(days=i)
        if day.weekday() in wanted:
            return day
    return start_date


class Invoice(models.Model):
    STATUS_CHOICES = [
        ("paid", "Paid"),
        ("failed", "Failed"),
        ("pending", "Pending"),
    ]
    subscription = models.ForeignKey(
        Subscription, on_delete=models.CASCADE, related_name="invoices"
    )
    stripe_invoice_id = models.CharField(max_length=255, blank=True)
    amount = models.DecimalField(max_digits=8, decimal_places=2)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES)
    paid_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)

    def __str__(self):
        return f"Invoice<{self.stripe_invoice_id or self.pk}:{self.status}>"


class WebhookEvent(models.Model):
    """Raw log of every Stripe event received - for debugging + idempotency."""

    stripe_event_id = models.CharField(max_length=255, unique=True)
    event_type = models.CharField(max_length=100)
    payload = models.JSONField()
    processed = models.BooleanField(default=False)
    received_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.event_type}:{self.stripe_event_id}"
