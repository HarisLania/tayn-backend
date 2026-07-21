import json

from django.contrib.auth.models import User
from django.db import transaction
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.generics import ListAPIView
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import CustomerProfile
from accounts.views import tokens_for
from plans.models import Plan

from . import services, webhooks
from .models import Invoice, Subscription, first_delivery_on_or_after
from .serializers import (
    ChangeDeliveryDaysSerializer,
    ChangePlanSerializer,
    CheckoutSessionSerializer,
    InvoiceSerializer,
    QuoteSerializer,
    SubscriptionSerializer,
)


def quote_for(plan, delivery_days, start_date=None):
    """The cycle arithmetic, in one place: 4 weeks x one meal per chosen day."""
    meals_per_week = len(delivery_days)
    meals_per_cycle = meals_per_week * Subscription.CYCLE_WEEKS
    payload = {
        "plan_id": plan.id,
        # Money as 2dp strings, matching how DRF serializes DecimalField
        # elsewhere, so the frontend never sees two shapes for a price.
        "price_per_meal": f"{plan.price_per_meal:.2f}",
        "meals_per_week": meals_per_week,
        "meals_per_cycle": meals_per_cycle,
        "price_per_cycle": f"{plan.price_per_meal * meals_per_cycle:.2f}",
        "cycle_days": Subscription.CYCLE_DAYS,
    }
    if start_date:
        payload["first_delivery_date"] = first_delivery_on_or_after(
            start_date, delivery_days
        )
    return payload


class QuoteView(APIView):
    """Price a selection before checkout. Creates nothing."""

    permission_classes = [AllowAny]

    @extend_schema(
        request=QuoteSerializer,
        responses={200: OpenApiResponse(description="Meal count and cycle price")},
        summary="Price a plan + delivery-day selection",
    )
    def post(self, request):
        serializer = QuoteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        plan = Plan.objects.get(id=data["plan_id"])
        return Response(
            quote_for(plan, data["delivery_days"], data.get("start_date"))
        )


class CreateCheckoutSessionView(APIView):
    """Create a Stripe Checkout Session. Doubles as sign-up for anonymous users."""

    permission_classes = [AllowAny]

    @extend_schema(
        request=CheckoutSessionSerializer,
        responses={200: OpenApiResponse(description="Returns checkout_url (+ tokens if new account)")},
        summary="Create subscription checkout session",
    )
    def post(self, request):
        serializer = CheckoutSessionSerializer(
            data=request.data, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        plan = data["plan"]
        delivery_days = data["delivery_days"]
        quote = quote_for(plan, delivery_days, data["start_date"])

        new_tokens = None
        with transaction.atomic():
            if request.user.is_authenticated:
                profile = request.user.profile
                email = request.user.email
                name = request.user.get_full_name() or request.user.username
            else:
                name = data["name"].strip()
                first, _, last = name.partition(" ")
                user = User.objects.create_user(
                    username=data["email"].lower(),
                    email=data["email"].lower(),
                    password=data["password"],
                    first_name=first,
                    last_name=last,
                )
                profile = CustomerProfile.objects.create(
                    user=user,
                    phone=data["phone"],
                    delivery_address=data["delivery_address"],
                    dietary_notes=data.get("dietary_notes", ""),
                )
                email = user.email
                new_tokens = tokens_for(user)

        customer_id = services.get_or_create_customer(profile, email, name)
        metadata = {
            "customer_profile_id": str(profile.id),
            "plan_id": str(plan.id),
            "start_date": data["start_date"].isoformat(),
            "delivery_days": json.dumps(delivery_days),
        }
        checkout_url = services.create_checkout_session(
            customer_id=customer_id,
            price_id=plan.stripe_price_id,
            quantity=quote["meals_per_cycle"],
            metadata=metadata,
        )

        payload = {"checkout_url": checkout_url, **quote}
        if new_tokens:
            payload["tokens"] = new_tokens
        return Response(payload)


class MySubscriptionView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(responses=SubscriptionSerializer,
                   summary="Current active subscription for the logged-in customer")
    def get(self, request):
        sub = (
            Subscription.objects.filter(customer__user=request.user)
            .exclude(status="canceled")
            .select_related("plan", "plan__category")
            .order_by("-created_at")
            .first()
        )
        if sub is None:
            return Response(
                {"detail": "No active subscription."},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response(SubscriptionSerializer(sub).data)


class SubscriptionInvoicesView(ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = InvoiceSerializer

    def get_queryset(self):
        return Invoice.objects.filter(
            subscription_id=self.kwargs["pk"],
            subscription__customer__user=self.request.user,
        )


class SubscriptionDeliveriesView(APIView):
    """Delivery dates for the subscription's current 28-day cycle."""

    permission_classes = [IsAuthenticated]

    @extend_schema(responses={200: OpenApiResponse(description="List of delivery dates")},
                   summary="Upcoming delivery dates")
    def get(self, request, pk):
        sub = _get_owned_subscription(request.user, pk)
        if sub is None:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        return Response({
            "delivery_days": sub.delivery_days,
            "first_delivery_date": sub.first_delivery_date,
            "meals_per_cycle": sub.meals_per_cycle,
            "dates": sub.delivery_dates(),
        })


def _get_owned_subscription(user, pk):
    return (
        Subscription.objects.filter(pk=pk, customer__user=user)
        .select_related("plan")
        .first()
    )


class ChangePlanView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        request=ChangePlanSerializer,
        responses={200: OpenApiResponse(description="Proration preview, or confirmation")},
        summary="Preview or confirm a plan upgrade/downgrade",
    )
    def post(self, request, pk):
        sub = _get_owned_subscription(request.user, pk)
        if sub is None:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        serializer = ChangePlanSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        new_plan = Plan.objects.get(id=serializer.validated_data["new_plan_id"])

        # Meal count is unchanged by a plan switch — only the per-meal rate moves.
        if serializer.validated_data["preview"]:
            proration = services.preview_change(
                stripe_subscription_id=sub.stripe_subscription_id,
                new_price_id=new_plan.stripe_price_id,
            )
            return Response({"preview": True, "new_plan_id": new_plan.id, **proration})

        services.apply_change(
            stripe_subscription_id=sub.stripe_subscription_id,
            new_price_id=new_plan.stripe_price_id,
        )
        sub.plan = new_plan
        sub.save(update_fields=["plan"])
        return Response({"preview": False, "plan": SubscriptionSerializer(sub).data})


class ChangeDeliveryDaysView(APIView):
    """Change which days meals arrive — a quantity change when the count moves."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        request=ChangeDeliveryDaysSerializer,
        responses={200: OpenApiResponse(description="Proration preview, or confirmation")},
        summary="Preview or confirm a delivery-day change",
    )
    def post(self, request, pk):
        sub = _get_owned_subscription(request.user, pk)
        if sub is None:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        serializer = ChangeDeliveryDaysSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        new_days = serializer.validated_data["delivery_days"]
        new_quantity = len(new_days) * Subscription.CYCLE_WEEKS

        if serializer.validated_data["preview"]:
            # Same number of days costs the same; skip the round trip to Stripe.
            if new_quantity == sub.meals_per_cycle:
                return Response({"preview": True, "amount_due": 0,
                                 "meals_per_cycle": new_quantity})
            proration = services.preview_change(
                stripe_subscription_id=sub.stripe_subscription_id,
                new_quantity=new_quantity,
            )
            return Response({"preview": True, "meals_per_cycle": new_quantity,
                             **proration})

        if new_quantity != sub.meals_per_cycle:
            services.apply_change(
                stripe_subscription_id=sub.stripe_subscription_id,
                new_quantity=new_quantity,
            )
        sub.delivery_days = new_days
        sub.save(update_fields=["delivery_days"])
        return Response({"preview": False,
                         "subscription": SubscriptionSerializer(sub).data})


class CancelSubscriptionView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        request=None,
        responses={200: OpenApiResponse(description="Marked to cancel at period end")},
        summary="Cancel subscription at end of current billing period",
    )
    def post(self, request, pk):
        sub = _get_owned_subscription(request.user, pk)
        if sub is None:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        services.cancel_at_period_end(stripe_subscription_id=sub.stripe_subscription_id)
        sub.cancel_at_period_end = True
        sub.save(update_fields=["cancel_at_period_end"])
        return Response(
            {
                "detail": "Subscription will remain active until the end of the current period.",
                "active_until": sub.current_period_end,
            }
        )


class StripeWebhookView(APIView):
    """Single Stripe webhook endpoint: verify signature, dedupe, dispatch."""

    permission_classes = [AllowAny]
    authentication_classes = []

    @extend_schema(request=None, responses={200: OpenApiResponse(description="Acknowledged")},
                   summary="Stripe webhook receiver")
    def post(self, request):
        from .models import WebhookEvent

        sig_header = request.META.get("HTTP_STRIPE_SIGNATURE", "")
        try:
            event = services.construct_event(request.body, sig_header)
        except services.StripeNotConfigured:
            raise
        except Exception:
            return Response({"detail": "Invalid signature."},
                            status=status.HTTP_400_BAD_REQUEST)

        event_id = event["id"]
        # Idempotency: skip events we have already fully processed.
        log, created = WebhookEvent.objects.get_or_create(
            stripe_event_id=event_id,
            defaults={"event_type": event["type"], "payload": event.get("data", {})},
        )
        if not created and log.processed:
            return Response({"detail": "Already processed."}, status=status.HTTP_200_OK)

        webhooks.dispatch(event["type"], event["data"]["object"])
        log.processed = True
        log.save(update_fields=["processed"])
        return Response({"received": True}, status=status.HTTP_200_OK)
