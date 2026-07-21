"""Root URL configuration for the Tayn backend."""
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularRedocView,
    SpectacularSwaggerView,
)

from config.views import health

urlpatterns = [
    path("admin/", admin.site.urls),

    # Uptime monitoring (UptimeRobot) — unauthenticated, returns 200 "OK"
    path("health/", health, name="health"),
    path("healthz", health),

    # API
    path("api/auth/", include("accounts.urls")),
    path("api/", include("menu.urls")),
    path("api/", include("plans.urls")),
    path("api/", include("subscriptions.urls")),

    # OpenAPI schema + Swagger / Redoc docs
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path(
        "api/docs/",
        SpectacularSwaggerView.as_view(url_name="schema"),
        name="swagger-ui",
    ),
    path(
        "api/redoc/",
        SpectacularRedocView.as_view(url_name="schema"),
        name="redoc",
    ),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
