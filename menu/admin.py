from django.contrib import admin

from .models import Category, Meal


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "slug")
    prepopulated_fields = {"slug": ("name",)}


@admin.register(Meal)
class MealAdmin(admin.ModelAdmin):
    list_display = ("name", "category", "meal_type", "calories", "protein_g", "is_active")
    list_filter = ("category", "meal_type", "is_active")
    search_fields = ("name",)
