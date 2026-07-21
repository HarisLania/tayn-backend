from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import generics
from rest_framework.permissions import AllowAny

from subscriptions.services import stripe_enabled

from .models import Plan
from .serializers import PlanSerializer


def purchasable_plans():
    """Active plans a customer could actually check out with.

    When Stripe is configured, a plan with no price id is not buyable, so hide
    it rather than offer it and reject it at checkout. With Stripe off (local
    development) a blank price id is expected, so nothing is filtered and the
    catalogue still browses.
    """
    qs = Plan.objects.filter(is_active=True).select_related("category")
    if stripe_enabled():
        qs = qs.exclude(stripe_price_id="")
    return qs


@extend_schema(
    parameters=[OpenApiParameter("category", str, description="Filter by category slug")]
)
class PlanListView(generics.ListAPIView):
    permission_classes = [AllowAny]
    serializer_class = PlanSerializer

    def get_queryset(self):
        qs = purchasable_plans()
        category = self.request.query_params.get("category")
        if category:
            qs = qs.filter(category__slug=category)
        return qs.order_by("id")


class PlanDetailView(generics.RetrieveAPIView):
    permission_classes = [AllowAny]
    serializer_class = PlanSerializer

    def get_queryset(self):
        return purchasable_plans()
