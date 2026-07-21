from decimal import Decimal

from django.db import migrations

# Price of a single meal in AED, by category slug. What a customer pays is this
# figure times the meals in their 4-week cycle (4 x delivery days chosen), so
# there is exactly one plan per category.
PRICE_PER_MEAL = {
    "standard": Decimal("40.00"),
    "low-cal": Decimal("35.00"),
    "weight-gain": Decimal("50.00"),
    "protein-power": Decimal("75.00"),
}


def seed_plans(apps, schema_editor):
    Category = apps.get_model("menu", "Category")
    Plan = apps.get_model("plans", "Plan")

    for slug, price_per_meal in PRICE_PER_MEAL.items():
        category = Category.objects.filter(slug=slug).first()
        if category is None:  # menu seed migration did not run
            continue
        Plan.objects.get_or_create(
            category=category,
            defaults={"name": category.name, "price_per_meal": price_per_meal},
        )


def remove_plans(apps, schema_editor):
    Category = apps.get_model("menu", "Category")
    Plan = apps.get_model("plans", "Plan")
    Plan.objects.filter(
        category__in=Category.objects.filter(slug__in=PRICE_PER_MEAL)
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("plans", "0001_initial"),
        ("menu", "0002_seed_dummy_meals"),
    ]

    operations = [
        migrations.RunPython(seed_plans, remove_plans),
    ]
