from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase, override_settings

User = get_user_model()


@override_settings(
    DEBUG=False,
    SECRET_KEY="x" * 64,
    ALLOWED_HOSTS=["testserver"],
    SITE_URL="http://testserver",
    EMAIL_BACKEND="django.core.mail.backends.console.EmailBackend",
    STATIC_ROOT="/tmp/lef-timesheet-test-static",
)
class GoLiveTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            email="admin-test@example.com",
            password="Password-test-123",
            ruolo=User.Ruolo.ADMIN,
            is_staff=True,
        )

    def test_verifica_go_live_locale(self):
        output = StringIO()

        call_command(
            "verifica_go_live",
            "--allow-http",
            "--allow-console-email",
            stdout=output,
        )

        contenuto = output.getvalue()
        self.assertIn("[OK] DEBUG", contenuto)
        self.assertIn("[OK] Database", contenuto)
        self.assertIn("[OK] Migrazioni", contenuto)
        self.assertIn("Esito go-live: 0 errori", contenuto)
