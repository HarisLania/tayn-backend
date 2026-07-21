from django.urls import path

from .views import CategoryListView, MealListView

urlpatterns = [
    path("categories/", CategoryListView.as_view(), name="category-list"),
    path("meals/", MealListView.as_view(), name="meal-list"),
]
