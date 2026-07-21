from django.db import models


class Category(models.Model):
    """Standard, Low Cal, Weight Gain, Protein Power."""

    name = models.CharField(max_length=50)
    slug = models.SlugField(unique=True)
    description = models.TextField(blank=True)

    class Meta:
        verbose_name_plural = "categories"

    def __str__(self):
        return self.name


class Meal(models.Model):
    MEAL_TYPE_CHOICES = [
        ("main", "Main Course"),
        ("snack", "Snack"),
        ("dessert", "Dessert"),
    ]
    category = models.ForeignKey(
        Category, on_delete=models.CASCADE, related_name="meals"
    )
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    meal_type = models.CharField(max_length=10, choices=MEAL_TYPE_CHOICES)
    image = models.ImageField(upload_to="meals/", blank=True)
    calories = models.PositiveIntegerField(null=True, blank=True)
    protein_g = models.PositiveIntegerField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.name} ({self.get_meal_type_display()})"
