from rest_framework import serializers

from menu.serializers import CategorySerializer

from .models import Plan


class PlanSerializer(serializers.ModelSerializer):
    category = CategorySerializer(read_only=True)

    class Meta:
        model = Plan
        fields = ("id", "category", "name", "price_per_meal", "is_active")
