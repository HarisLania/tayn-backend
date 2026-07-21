from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from menu.models import Category, Meal


class MenuTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        # Migrations seed the real catalogue; drop it so the counts below are
        # about this fixture only. Cascades to Meal and Plan.
        Category.objects.all().delete()
        cls.standard = Category.objects.create(name="Standard", slug="standard")
        cls.protein = Category.objects.create(name="Protein Power", slug="protein-power")
        Meal.objects.create(category=cls.standard, name="Grilled Chicken",
                            meal_type="main", calories=520, protein_g=45)
        Meal.objects.create(category=cls.standard, name="Fruit Cup",
                            meal_type="snack", calories=120, protein_g=2)
        Meal.objects.create(category=cls.protein, name="Steak Bowl",
                            meal_type="main", calories=700, protein_g=60)
        Meal.objects.create(category=cls.protein, name="Hidden Meal",
                            meal_type="main", is_active=False)

    def test_categories_public(self):
        res = self.client.get(reverse("category-list"))
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(len(res.data), 2)

    def test_meals_filter_by_category(self):
        res = self.client.get(reverse("meal-list"), {"category": "protein-power"})
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        # Hidden Meal is inactive, so only Steak Bowl
        self.assertEqual(len(res.data), 1)
        self.assertEqual(res.data[0]["name"], "Steak Bowl")

    def test_meals_filter_by_type(self):
        res = self.client.get(reverse("meal-list"), {"meal_type": "snack"})
        self.assertEqual(len(res.data), 1)
        self.assertEqual(res.data[0]["name"], "Fruit Cup")

    def test_inactive_meals_excluded(self):
        res = self.client.get(reverse("meal-list"))
        names = [m["name"] for m in res.data]
        self.assertNotIn("Hidden Meal", names)
