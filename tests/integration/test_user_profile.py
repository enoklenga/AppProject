from io import BytesIO

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from PIL import Image

from apps.accounts.models import User


@override_settings(MEDIA_ROOT="/tmp/leftrack-test-media")
class UserProfileTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="profilo@example.com",
            password="Password-Profilo-123!",
            first_name="Mario",
            last_name="Rossi",
            ruolo=User.Ruolo.CONSULENTE,
            deve_cambiare_password=False,
        )
        self.client.force_login(self.user)

    @staticmethod
    def _image_file(name="avatar.png", size=(64, 64)):
        buffer = BytesIO()
        Image.new("RGB", size, "white").save(buffer, format="PNG")
        return SimpleUploadedFile(
            name,
            buffer.getvalue(),
            content_type="image/png",
        )

    def test_profile_requires_login(self):
        self.client.logout()
        response = self.client.get(reverse("accounts:profile"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response.url)

    def test_user_can_update_own_profile_and_photo(self):
        response = self.client.post(
            reverse("accounts:profile"),
            {
                "first_name": "Mario",
                "last_name": "Bianchi",
                "telefono": "+39 040 1234567",
                "foto_profilo": self._image_file(),
            },
        )
        self.assertRedirects(
            response,
            reverse("accounts:profile"),
            fetch_redirect_response=False,
        )
        self.user.refresh_from_db()
        self.assertEqual(self.user.last_name, "Bianchi")
        self.assertEqual(self.user.telefono, "+39 040 1234567")
        self.assertTrue(self.user.foto_profilo.name.startswith("avatars/"))

    def test_profile_form_does_not_allow_role_or_email_change(self):
        response = self.client.post(
            reverse("accounts:profile"),
            {
                "first_name": "Mario",
                "last_name": "Rossi",
                "telefono": "",
                "email": "altro@example.com",
                "ruolo": User.Ruolo.ADMIN,
            },
        )
        self.assertEqual(response.status_code, 302)
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, "profilo@example.com")
        self.assertEqual(self.user.ruolo, User.Ruolo.CONSULENTE)

    def test_profile_rejects_file_over_three_mb(self):
        buffer = BytesIO()
        Image.new("RGB", (1400, 1400), "white").save(
            buffer,
            format="PNG",
            compress_level=0,
        )
        self.assertGreater(len(buffer.getvalue()), 3 * 1024 * 1024)
        oversized = SimpleUploadedFile(
            "avatar.png",
            buffer.getvalue(),
            content_type="image/png",
        )
        response = self.client.post(
            reverse("accounts:profile"),
            {
                "first_name": "Mario",
                "last_name": "Rossi",
                "telefono": "",
                "foto_profilo": oversized,
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "non può superare 3 MB")
