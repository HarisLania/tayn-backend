from django.urls import path

from .views import PlanDetailView, PlanListView

urlpatterns = [
    path("plans/", PlanListView.as_view(), name="plan-list"),
    path("plans/<int:pk>/", PlanDetailView.as_view(), name="plan-detail"),
]
