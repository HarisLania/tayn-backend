from django.contrib import admin

from .models import Invoice, Subscription, WebhookEvent


class InvoiceInline(admin.TabularInline):
    model = Invoice
    extra = 0


@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = ("id", "customer", "plan", "start_date", "meals_per_cycle",
                    "price_per_cycle", "status", "current_period_end",
                    "cancel_at_period_end")
    list_filter = ("status", "plan")
    inlines = [InvoiceInline]


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = ("stripe_invoice_id", "subscription", "amount", "status", "paid_at")
    list_filter = ("status",)


@admin.register(WebhookEvent)
class WebhookEventAdmin(admin.ModelAdmin):
    list_display = ("stripe_event_id", "event_type", "processed", "received_at")
    list_filter = ("event_type", "processed")
    readonly_fields = ("stripe_event_id", "event_type", "payload", "received_at")
