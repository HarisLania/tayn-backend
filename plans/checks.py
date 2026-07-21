"""Startup check for plans that exist locally but not in Stripe.

The seed migration creates plans offline and deliberately does not call Stripe
(migrations run in tests, in CI, and on machines with no API keys, and a rolled
back transaction cannot un-create a Stripe product). The trade-off is that a
plan can sit in the database without a price, so surface that drift loudly on
every management command instead of discovering it at checkout.
"""
from django.conf import settings
from django.core.checks import Warning, register


@register()
def unsynced_plans(app_configs, **kwargs):
    if getattr(settings, "TESTING", False):
        return []
    if not settings.STRIPE_SECRET_KEY:
        return []  # payments disabled; an empty price id is expected

    from plans.models import Plan

    try:
        names = list(
            Plan.objects.filter(is_active=True, stripe_price_id="")
            .values_list("name", flat=True)
        )
    except Exception:
        return []  # database not migrated yet

    if not names:
        return []
    return [
        Warning(
            f"{len(names)} active plan(s) have no Stripe price: {', '.join(names)}.",
            hint="Run `python manage.py sync_stripe_prices`. Until then these "
                 "plans are hidden from /api/plans/ and cannot be purchased.",
            id="plans.W001",
        )
    ]
