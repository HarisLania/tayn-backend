from django.db import models

from menu.models import Category


class Plan(models.Model):
    """The per-meal rate card for a menu category.

    Pricing is per meal: what a customer pays is decided by how many meals they
    receive in a billing cycle, not by the plan itself. See
    `subscriptions.models.Subscription` for the cycle arithmetic.
    """

    category = models.OneToOneField(
        Category, on_delete=models.CASCADE, related_name="plan"
    )
    name = models.CharField(max_length=100)  # e.g. "Protein Power"
    price_per_meal = models.DecimalField(max_digits=6, decimal_places=2)  # AED
    stripe_price_id = models.CharField(max_length=255, blank=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.name} ({self.price_per_meal} AED/meal)"
