from django.contrib.auth.models import User
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import CustomerProfile


class AuthFlowTests(APITestCase):
    def _register_payload(self, **overrides):
        data = {
            "name": "Aisha Khan",
            "email": "aisha@example.com",
            "phone": "+971500000000",
            "delivery_address": "12 Marina Walk, Dubai",
            "dietary_notes": "No nuts",
            "password": "SuperSecret123",
            "confirm_password": "SuperSecret123",
        }
        data.update(overrides)
        return data

    def test_register_creates_user_and_profile(self):
        res = self.client.post(reverse("register"), self._register_payload(), format="json")
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertIn("access", res.data["tokens"])
        self.assertTrue(User.objects.filter(username="aisha@example.com").exists())
        self.assertTrue(CustomerProfile.objects.filter(user__email="aisha@example.com").exists())

    def test_register_password_mismatch(self):
        res = self.client.post(
            reverse("register"),
            self._register_payload(confirm_password="different"),
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_register_duplicate_email(self):
        self.client.post(reverse("register"), self._register_payload(), format="json")
        res = self.client.post(reverse("register"), self._register_payload(), format="json")
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_login_and_me(self):
        self.client.post(reverse("register"), self._register_payload(), format="json")
        res = self.client.post(
            reverse("login"),
            {"email": "aisha@example.com", "password": "SuperSecret123"},
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        access = res.data["tokens"]["access"]

        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
        me = self.client.get(reverse("me"))
        self.assertEqual(me.status_code, status.HTTP_200_OK)
        self.assertEqual(me.data["email"], "aisha@example.com")

    def test_login_wrong_password(self):
        self.client.post(reverse("register"), self._register_payload(), format="json")
        res = self.client.post(
            reverse("login"),
            {"email": "aisha@example.com", "password": "nope"},
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_logout_blacklists_refresh(self):
        reg = self.client.post(reverse("register"), self._register_payload(), format="json")
        tokens = reg.data["tokens"]
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")
        res = self.client.post(reverse("logout"), {"refresh": tokens["refresh"]}, format="json")
        self.assertEqual(res.status_code, status.HTTP_205_RESET_CONTENT)
        # refresh should no longer be usable
        again = self.client.post(reverse("token-refresh"), {"refresh": tokens["refresh"]}, format="json")
        self.assertEqual(again.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_me_requires_auth(self):
        res = self.client.get(reverse("me"))
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)
