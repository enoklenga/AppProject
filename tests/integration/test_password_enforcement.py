from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import User


@override_settings(WEB_REQUIRE_PASSWORD_CHANGED=True)
class PasswordEnforcementTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="password-required@example.com",
            password="Old-Password-123",
            deve_cambiare_password=True,
        )
        self.client.force_login(self.user)

    def test_utente_con_flag_viene_portato_al_cambio_password(self):
        response = self.client.get(reverse("home"))
        self.assertRedirects(
            response,
            reverse("password_change"),
            fetch_redirect_response=False,
        )

    def test_cambio_password_azzera_il_flag(self):
        response = self.client.post(
            reverse("password_change"),
            {
                "old_password": "Old-Password-123",
                "new_password1": "Nuova-Password-Sicura-456!",
                "new_password2": "Nuova-Password-Sicura-456!",
            },
        )

        self.assertRedirects(response, "/", fetch_redirect_response=False)
        self.user.refresh_from_db()
        self.assertFalse(self.user.deve_cambiare_password)
