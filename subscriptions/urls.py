from django.urls import path

from .views import (
    CancelSubscriptionView,
    ChangeDeliveryDaysView,
    ChangePlanView,
    CreateCheckoutSessionView,
    MySubscriptionView,
    QuoteView,
    StripeWebhookView,
    SubscriptionDeliveriesView,
    SubscriptionInvoicesView,
)

urlpatterns = [
    path("checkout/quote/", QuoteView.as_view(), name="checkout-quote"),
    path("checkout/create-session/", CreateCheckoutSessionView.as_view(),
         name="checkout-create-session"),
    path("subscriptions/me/", MySubscriptionView.as_view(), name="subscription-me"),
    path("subscriptions/<int:pk>/invoices/", SubscriptionInvoicesView.as_view(),
         name="subscription-invoices"),
    path("subscriptions/<int:pk>/deliveries/", SubscriptionDeliveriesView.as_view(),
         name="subscription-deliveries"),
    path("subscriptions/<int:pk>/change-plan/", ChangePlanView.as_view(),
         name="subscription-change-plan"),
    path("subscriptions/<int:pk>/delivery-days/", ChangeDeliveryDaysView.as_view(),
         name="subscription-delivery-days"),
    path("subscriptions/<int:pk>/cancel/", CancelSubscriptionView.as_view(),
         name="subscription-cancel"),
    path("webhooks/stripe/", StripeWebhookView.as_view(), name="stripe-webhook"),
]
