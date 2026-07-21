"""Infrastructure endpoints that are not part of the public API surface."""
from django.http import HttpResponse


def health(request):
    """Liveness probe for uptime monitoring — plain `OK` with HTTP 200.

    Deliberately does no database or Stripe work: the monitor pings this every
    few minutes only to keep the dyno warm and to alert when the process dies.
    """
    return HttpResponse("OK", content_type="text/plain", status=200)
