from rest_framework import serializers

from .models import Category, Meal


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ("id", "name", "slug", "description")


class MealSerializer(serializers.ModelSerializer):
    category = serializers.SlugRelatedField(slug_field="slug", read_only=True)
    meal_type_display = serializers.CharField(
        source="get_meal_type_display", read_only=True
    )

    class Meta:
        model = Meal
        fields = (
            "id", "category", "name", "description",
            "meal_type", "meal_type_display",
            "image", "calories", "protein_g", "is_active",
        )
