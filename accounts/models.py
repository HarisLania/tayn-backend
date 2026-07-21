from django.contrib.auth.models import User
from django.db import models


class CustomerProfile(models.Model):
    """Extra customer data attached one-to-one to a Django auth User."""

    user = models.OneToOneField(
        User, on_delete=models.CASCADE, related_name="profile"
    )
    phone = models.CharField(max_length=20)
    delivery_address = models.TextField()
    dietary_notes = models.TextField(blank=True)
    stripe_customer_id = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Profile<{self.user.email or self.user.username}>"
