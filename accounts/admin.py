from django.contrib import admin

from .models import CustomerProfile


@admin.register(CustomerProfile)
class CustomerProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "phone", "stripe_customer_id", "created_at")
    search_fields = ("user__username", "user__email", "phone", "stripe_customer_id")
