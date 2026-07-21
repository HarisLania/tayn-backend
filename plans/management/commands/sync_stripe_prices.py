"""
Create/refresh the Stripe Product + Price backing every Plan.

One price per plan, holding the *per-meal* rate and recurring every 4 weeks.
The meal count is the subscription line item's quantity, so a plan needs only
this single price no matter how many delivery days a customer picks.

Idempotent: each plan's price is keyed by a stable Stripe `lookup_key`
(`tayn_plan_<id>`), so re-running only creates what is missing. Stripe prices
are immutable, so when a rate changes the old price is archived and the lookup
key transfers to a freshly created one; existing subscribers keep theirs until
migrated deliberately.

    python manage.py sync_stripe_prices           # create/update
    python manage.py sync_stripe_prices --dry-run # show what would change
"""
import stripe
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from plans.models import Plan
from subscriptions.models import Subscription

RECURRING = {"interval": "week", "interval_count": Subscription.CYCLE_WEEKS}


class Command(BaseCommand):
    help = "Create Stripe products/prices for every Plan and store their ids."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true",
                            help="Report the changes without calling Stripe writes.")
        parser.add_argument("--check", action="store_true",
                            help="Verify every plan is in sync; exit non-zero if not. "
                                 "Writes nothing. Intended for CI and deploys.")

    def handle(self, *args, **options):
        if not settings.STRIPE_SECRET_KEY:
            raise CommandError("STRIPE_SECRET_KEY is not set; nothing to sync.")
        stripe.api_key = settings.STRIPE_SECRET_KEY
        if options["check"]:
            return self._check(settings.STRIPE_CURRENCY.lower())
        self.dry_run = options["dry_run"]
        currency = settings.STRIPE_CURRENCY.lower()

        plans = Plan.objects.filter(is_active=True).select_related("category")
        if not plans:
            raise CommandError(
                "No active plans in the database. Run `python manage.py migrate` "
                "(plans.0002_seed_plans) or create plans in the admin first."
            )

        for plan in plans:
            # Resolve the existing price first: it is the authoritative link to
            # this plan's product, so a stale `stripe_price_id` cannot trick us
            # into creating a second, orphaned product.
            current = self._existing_price(plan)
            product_id = self._ensure_product(plan, current)
            price_id = self._ensure_price(plan, product_id, currency, current)
            if price_id and plan.stripe_price_id != price_id and not self.dry_run:
                plan.stripe_price_id = price_id
                plan.save(update_fields=["stripe_price_id"])

        self.stdout.write(self.style.SUCCESS(
            f"{'Would sync' if self.dry_run else 'Synced'} {len(plans)} plan(s) to Stripe."
        ))

    def _check(self, currency):
        """Read-only drift report: local price ids vs. what Stripe actually has."""
        problems = []
        for plan in Plan.objects.filter(is_active=True):
            if not plan.stripe_price_id:
                problems.append(f"{plan.name}: no stripe_price_id stored")
                continue
            try:
                price = stripe.Price.retrieve(plan.stripe_price_id)
            except stripe.error.StripeError as exc:
                problems.append(f"{plan.name}: price {plan.stripe_price_id} "
                                f"not retrievable ({exc.user_message or exc})")
                continue

            expected = int(plan.price_per_meal * 100)
            if price["unit_amount"] != expected:
                problems.append(
                    f"{plan.name}: Stripe has {price['unit_amount'] / 100:.2f} "
                    f"{price['currency'].upper()}, database says "
                    f"{plan.price_per_meal} {currency.upper()}"
                )
            elif price["currency"] != currency:
                problems.append(f"{plan.name}: Stripe currency is "
                                f"{price['currency'].upper()}, expected {currency.upper()}")
            elif not price["active"]:
                problems.append(f"{plan.name}: price {price['id']} is archived")
            else:
                self.stdout.write(f"  ok  {plan.name} -> {price['id']}")

        if problems:
            raise CommandError(
                "Plans are out of sync with Stripe:\n  - "
                + "\n  - ".join(problems)
                + "\nRun `python manage.py sync_stripe_prices` to fix."
            )
        self.stdout.write(self.style.SUCCESS("All active plans are in sync."))

    # -- Stripe helpers ----------------------------------------------------

    @staticmethod
    def _existing_price(plan):
        """The live price carrying this plan's lookup key, if there is one."""
        lookup_key = f"tayn_plan_{plan.id}"
        found = stripe.Price.list(lookup_keys=[lookup_key], active=True, limit=1)["data"]
        return found[0] if found else None

    def _ensure_product(self, plan, current):
        """Reuse the product behind the plan's price, else create one."""
        if current:
            return current["product"]
        if plan.stripe_price_id:
            try:
                return stripe.Price.retrieve(plan.stripe_price_id)["product"]
            except stripe.error.StripeError:
                pass  # stale id (e.g. copied from another account)

        if self.dry_run:
            self.stdout.write(f"  [dry-run] create product {plan.name!r}")
            return None
        product = stripe.Product.create(
            name=plan.name,
            description=f"{plan.category.name} meal plan, billed per meal.",
            metadata={"tayn_plan_id": str(plan.id)},
        )
        self.stdout.write(f"  created product {product['id']} ({plan.name})")
        return product["id"]

    def _ensure_price(self, plan, product_id, currency, current):
        lookup_key = f"tayn_plan_{plan.id}"
        unit_amount = int(plan.price_per_meal * 100)  # AED -> fils

        if current and (current["unit_amount"] == unit_amount
                        and current["currency"] == currency):
            return current["id"]

        label = (f"{plan.name} @ {unit_amount / 100:.2f} {currency.upper()}/meal "
                 f"every {Subscription.CYCLE_WEEKS} weeks")
        if self.dry_run:
            verb = "replace price for" if current else "create price"
            self.stdout.write(f"  [dry-run] {verb} {label}")
            return None

        price = stripe.Price.create(
            product=product_id,
            currency=currency,
            unit_amount=unit_amount,
            recurring=RECURRING,
            lookup_key=lookup_key,
            transfer_lookup_key=bool(current),
            metadata={"tayn_plan_id": str(plan.id)},
        )
        if current:
            # Prices are immutable; retire the superseded one so it cannot be
            # attached to new subscriptions. Existing subscribers keep theirs.
            stripe.Price.modify(current["id"], active=False)
        self.stdout.write(f"  created price {price['id']} ({label})")
        return price["id"]
