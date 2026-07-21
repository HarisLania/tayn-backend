from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.permissions import AllowAny
from rest_framework import generics

from .models import Category, Meal
from .serializers import CategorySerializer, MealSerializer


class CategoryListView(generics.ListAPIView):
    permission_classes = [AllowAny]
    serializer_class = CategorySerializer
    queryset = Category.objects.all().order_by("id")


@extend_schema(
    parameters=[
        OpenApiParameter("category", str, description="Filter by category slug"),
        OpenApiParameter("meal_type", str, description="main | snack | dessert"),
    ]
)
class MealListView(generics.ListAPIView):
    permission_classes = [AllowAny]
    serializer_class = MealSerializer

    def get_queryset(self):
        qs = Meal.objects.filter(is_active=True).select_related("category")
        category = self.request.query_params.get("category")
        meal_type = self.request.query_params.get("meal_type")
        if category:
            qs = qs.filter(category__slug=category)
        if meal_type:
            qs = qs.filter(meal_type=meal_type)
        return qs.order_by("id")
