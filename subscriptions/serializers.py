from datetime import date, timedelta

from django.conf import settings
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from plans.models import Plan
from plans.serializers import PlanSerializer

from .models import WEEKDAYS, Invoice, Subscription


class InvoiceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Invoice
        fields = ("id", "stripe_invoice_id", "amount", "status", "paid_at", "created_at")


class SubscriptionSerializer(serializers.ModelSerializer):
    plan = PlanSerializer(read_only=True)
    meals_per_week = serializers.IntegerField(read_only=True)
    meals_per_cycle = serializers.IntegerField(read_only=True)
    price_per_cycle = serializers.DecimalField(
        max_digits=10, decimal_places=2, read_only=True
    )
    first_delivery_date = serializers.DateField(read_only=True)

    class Meta:
        model = Subscription
        fields = (
            "id", "plan", "delivery_days", "start_date", "first_delivery_date",
            "meals_per_week", "meals_per_cycle", "price_per_cycle",
            "status", "current_period_end", "cancel_at_period_end", "created_at",
        )


def validate_delivery_days(value):
    """1-7 unique weekday codes. Normalised to lowercase."""
    days = [str(d).strip().lower() for d in value]
    unknown = [d for d in days if d not in WEEKDAYS]
    if unknown:
        raise serializers.ValidationError(
            f"Unknown weekday(s): {', '.join(unknown)}. Use {', '.join(WEEKDAYS)}."
        )
    if len(set(days)) != len(days):
        raise serializers.ValidationError("Duplicate delivery days.")
    if not 1 <= len(days) <= 7:
        raise serializers.ValidationError("Choose between 1 and 7 delivery days.")
    # Store in week order so ["fri","mon"] and ["mon","fri"] are the same record.
    return sorted(days, key=WEEKDAYS.index)


def validate_start_date(value):
    earliest = date.today() + timedelta(days=settings.MIN_START_LEAD_DAYS)
    if value < earliest:
        raise serializers.ValidationError(
            f"Earliest start date is {earliest.isoformat()} "
            f"({settings.MIN_START_LEAD_DAYS} days from today)."
        )
    return value


class CheckoutSessionSerializer(serializers.Serializer):
    plan_id = serializers.IntegerField()
    start_date = serializers.DateField(validators=[validate_start_date])
    delivery_days = serializers.ListField(
        child=serializers.CharField(), allow_empty=False,
    )

    # Account fields — required only when the requester is anonymous.
    name = serializers.CharField(required=False)
    email = serializers.EmailField(required=False)
    phone = serializers.CharField(required=False)
    delivery_address = serializers.CharField(required=False)
    dietary_notes = serializers.CharField(required=False, allow_blank=True, default="")
    password = serializers.CharField(required=False, write_only=True)
    confirm_password = serializers.CharField(required=False, write_only=True)

    def validate_delivery_days(self, value):
        return validate_delivery_days(value)

    def validate(self, attrs):
        plan = Plan.objects.filter(id=attrs["plan_id"], is_active=True).first()
        if plan is None:
            raise serializers.ValidationError({"plan_id": "Plan not found."})
        if not plan.stripe_price_id:
            raise serializers.ValidationError(
                {"plan_id": "This plan is not available for purchase yet."}
            )
        attrs["plan"] = plan

        request = self.context.get("request")
        if not (request and request.user.is_authenticated):
            required = ["name", "email", "phone", "delivery_address", "password", "confirm_password"]
            missing = [f for f in required if not attrs.get(f)]
            if missing:
                raise serializers.ValidationError(
                    {f: "This field is required for new accounts." for f in missing}
                )
            if attrs["password"] != attrs["confirm_password"]:
                raise serializers.ValidationError(
                    {"confirm_password": "Passwords do not match."}
                )
        return attrs


class QuoteSerializer(serializers.Serializer):
    """Price a basket without creating anything — for the live UI total."""

    plan_id = serializers.IntegerField()
    delivery_days = serializers.ListField(
        child=serializers.CharField(), allow_empty=False,
    )
    start_date = serializers.DateField(required=False)

    def validate_delivery_days(self, value):
        return validate_delivery_days(value)

    def validate_plan_id(self, value):
        if not Plan.objects.filter(id=value, is_active=True).exists():
            raise serializers.ValidationError("Plan not found.")
        return value


class ChangePlanSerializer(serializers.Serializer):
    new_plan_id = serializers.IntegerField()
    preview = serializers.BooleanField(default=False)

    def validate_new_plan_id(self, value):
        if not Plan.objects.filter(id=value, is_active=True).exists():
            raise serializers.ValidationError("Plan not found.")
        return value


class ChangeDeliveryDaysSerializer(serializers.Serializer):
    delivery_days = serializers.ListField(
        child=serializers.CharField(), allow_empty=False,
    )
    preview = serializers.BooleanField(default=False)

    def validate_delivery_days(self, value):
        return validate_delivery_days(value)
