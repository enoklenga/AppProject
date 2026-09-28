from datetime import timedelta

from django.core.cache import cache
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase

from apps.accounts.models import User
from apps.api.models import ApiTokenMetadata
from apps.api.token_services import ensure_token_metadata


class SecurityApiTests(APITestCase):
    password = "Password-test-Security-123"

    def setUp(self):
        cache.clear()
        self.admin = User.objects.create_user(
            email="admin-test@example.com",
            password=self.password,
            ruolo=User.Ruolo.ADMIN,
            is_active=True,
        )
        self.consulente = User.objects.create_user(
            email="consulente-test@example.com",
            password=self.password,
            ruolo=User.Ruolo.CONSULENTE,
            is_active=True,
        )

    def authenticate(self, user):
        token = Token.objects.create(user=user)
        ensure_token_metadata(token)
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Token {token.key}"
        )
        return token

    def test_response_contains_request_id_and_security_headers(self):
        response = self.client.get(reverse("api:health"))

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response["X-Request-ID"])
        self.assertEqual(
            response["X-Content-Type-Options"],
            "nosniff",
        )
        self.assertEqual(response["Referrer-Policy"], "no-referrer")
        self.assertEqual(response["Cache-Control"], "no-store")

    def test_login_returns_expiry_metadata(self):
        response = self.client.post(
            reverse("api:token-login"),
            {
                "email": self.consulente.email,
                "password": self.password,
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["token"])
        self.assertEqual(response.data["token_type"], "Token")
        self.assertIn("expires_at", response.data["security"])
        self.assertFalse(response.data["security"]["expired"])

    def test_expired_token_is_rejected_and_revoked(self):
        token = Token.objects.create(user=self.consulente)
        ApiTokenMetadata.objects.create(
            token=token,
            expires_at=timezone.now() - timedelta(minutes=1),
        )
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Token {token.key}"
        )

        response = self.client.get(reverse("api:me"))

        self.assertEqual(response.status_code, 401)
        self.assertIn(
            "Token scaduto",
            str(response.data["error"]["detail"]),
        )
        self.assertFalse(Token.objects.filter(key=token.key).exists())

    def test_status_masks_token(self):
        token = self.authenticate(self.consulente)

        response = self.client.get(reverse("api:token-status"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.data["masked_token"],
            f"{token.key[:4]}...{token.key[-4:]}",
        )
        self.assertNotIn("token", response.data)

    def test_rotation_invalidates_previous_token(self):
        old_token = self.authenticate(self.consulente)

        response = self.client.post(reverse("api:token-rotate"))

        self.assertEqual(response.status_code, 200)
        new_token = response.data["token"]
        self.assertNotEqual(old_token.key, new_token)
        self.assertFalse(
            Token.objects.filter(key=old_token.key).exists()
        )

        self.client.credentials(
            HTTP_AUTHORIZATION=f"Token {old_token.key}"
        )
        old_response = self.client.get(reverse("api:me"))
        self.assertEqual(old_response.status_code, 401)

        self.client.credentials(
            HTTP_AUTHORIZATION=f"Token {new_token}"
        )
        new_response = self.client.get(reverse("api:me"))
        self.assertEqual(new_response.status_code, 200)

    def test_admin_can_list_and_revoke_without_seeing_keys(self):
        admin_token = self.authenticate(self.admin)
        consultant_token = Token.objects.create(user=self.consulente)
        ensure_token_metadata(consultant_token)

        listing = self.client.get(reverse("api:security-token-list"))

        self.assertEqual(listing.status_code, 200)
        self.assertEqual(listing.data["count"], 2)
        raw = str(listing.data)
        self.assertNotIn(admin_token.key, raw)
        self.assertNotIn(consultant_token.key, raw)

        revoke = self.client.post(
            reverse(
                "api:security-token-revoke",
                kwargs={"user_id": self.consulente.id},
            )
        )
        self.assertEqual(revoke.status_code, 200)
        self.assertTrue(revoke.data["revoked"])
        self.assertFalse(
            Token.objects.filter(user=self.consulente).exists()
        )

    def test_non_admin_cannot_use_security_admin_endpoints(self):
        self.authenticate(self.consulente)

        response = self.client.get(reverse("api:security-token-list"))

        self.assertEqual(response.status_code, 403)

    @override_settings(
        REST_FRAMEWORK={
            "DEFAULT_AUTHENTICATION_CLASSES": [
                "apps.api.authentication.ExpiringTokenAuthentication",
            ],
            "DEFAULT_PERMISSION_CLASSES": [
                "rest_framework.permissions.IsAuthenticated",
            ],
            "DEFAULT_THROTTLE_CLASSES": [
                "rest_framework.throttling.AnonRateThrottle",
            ],
            "DEFAULT_THROTTLE_RATES": {
                "anon": "100/min",
                "api_login": "2/min",
            },
            "EXCEPTION_HANDLER": (
                "apps.api.exceptions.api_exception_handler"
            ),
            "TEST_REQUEST_DEFAULT_FORMAT": "json",
        }
    )
    def test_login_is_throttled(self):
        cache.clear()
        payload = {
            "email": self.consulente.email,
            "password": "password-errata",
        }

        first = self.client.post(reverse("api:token-login"), payload)
        second = self.client.post(reverse("api:token-login"), payload)
        third = self.client.post(reverse("api:token-login"), payload)

        self.assertEqual(first.status_code, 400)
        self.assertEqual(second.status_code, 400)
        self.assertEqual(third.status_code, 429)
        self.assertIn(
            "request_id",
            third.data["error"],
        )
