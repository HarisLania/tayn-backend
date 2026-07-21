from django.contrib import admin

from .models import Plan


@admin.register(Plan)
class PlanAdmin(admin.ModelAdmin):
    list_display = ("name", "category", "price_per_meal", "synced", "is_active")
    list_filter = ("category", "is_active")
    search_fields = ("name",)
    # The price id is owned by `manage.py sync_stripe_prices`; editing it by
    # hand is how a plan ends up pointing at the wrong Stripe object.
    readonly_fields = ("stripe_price_id",)

    @admin.display(boolean=True, description="In Stripe")
    def synced(self, obj):
        return bool(obj.stripe_price_id)
