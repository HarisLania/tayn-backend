from decimal import Decimal

from django.test import override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from menu.models import Category
from plans.checks import unsynced_plans
from plans.models import Plan


class PlanTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        # Migrations seed the real catalogue; drop it so the counts below are
        # about this fixture only. Cascades to Plan.
        Category.objects.all().delete()
        cls.cat = Category.objects.create(name="Protein Power", slug="protein-power")
        cls.plan = Plan.objects.create(
            category=cls.cat, name="Protein Power", price_per_meal=Decimal("75.00"),
            stripe_price_id="price_protein",
        )

    def test_list_plans_public(self):
        res = self.client.get(reverse("plan-list"))
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(len(res.data), 1)
        self.assertEqual(res.data[0]["price_per_meal"], "75.00")
        self.assertEqual(res.data[0]["category"]["slug"], "protein-power")

    def test_filter_by_category(self):
        other = Category.objects.create(name="Low Cal", slug="low-cal")
        Plan.objects.create(category=other, name="Low Cal",
                            price_per_meal=Decimal("35.00"),
                            stripe_price_id="price_lowcal")
        res = self.client.get(reverse("plan-list"), {"category": "protein-power"})
        self.assertEqual(len(res.data), 1)

    def test_plan_detail(self):
        res = self.client.get(reverse("plan-detail", args=[self.plan.id]))
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["name"], "Protein Power")

    def test_inactive_plans_hidden(self):
        Plan.objects.filter(id=self.plan.id).update(is_active=False)
        res = self.client.get(reverse("plan-list"))
        self.assertEqual(len(res.data), 0)


@override_settings(STRIPE_SECRET_KEY="sk_test_x", TESTING=False)
class UnsyncedPlanTests(APITestCase):
    """A plan with no Stripe price is not purchasable, so it is not offered."""

    def setUp(self):
        Category.objects.all().delete()
        cat = Category.objects.create(name="Standard", slug="standard")
        self.plan = Plan.objects.create(category=cat, name="Standard",
                                        price_per_meal=Decimal("40.00"))

    def test_hidden_from_list(self):
        res = self.client.get(reverse("plan-list"))
        self.assertEqual(len(res.data), 0)

    def test_hidden_from_detail(self):
        res = self.client.get(reverse("plan-detail", args=[self.plan.id]))
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)

    def test_visible_once_synced(self):
        Plan.objects.filter(id=self.plan.id).update(stripe_price_id="price_abc")
        res = self.client.get(reverse("plan-list"))
        self.assertEqual(len(res.data), 1)

    def test_system_check_warns(self):
        warnings = unsynced_plans(None)
        self.assertEqual(len(warnings), 1)
        self.assertEqual(warnings[0].id, "plans.W001")
        self.assertIn("Standard", warnings[0].msg)

    def test_system_check_silent_once_synced(self):
        Plan.objects.filter(id=self.plan.id).update(stripe_price_id="price_abc")
        self.assertEqual(unsynced_plans(None), [])


class StripeDisabledTests(APITestCase):
    """With payments off, a blank price id is expected and must not hide plans."""

    @override_settings(STRIPE_SECRET_KEY="", TESTING=False)
    def test_plans_still_listed(self):
        Category.objects.all().delete()
        cat = Category.objects.create(name="Standard", slug="standard")
        Plan.objects.create(category=cat, name="Standard",
                            price_per_meal=Decimal("40.00"))
        res = self.client.get(reverse("plan-list"))
        self.assertEqual(len(res.data), 1)
        self.assertEqual(unsynced_plans(None), [])
