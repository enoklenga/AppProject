from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

User = get_user_model()


class HealthTests(TestCase):
    def test_liveness_endpoint(self):
        response = self.client.get(reverse("health"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")
        self.assertEqual(response.json()["check"], "liveness")

    def test_readiness_endpoint(self):
        response = self.client.get(reverse("health_ready"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["database"], "available")


class EnvironmentValidationTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            email="admin-test@example.com",
            password="Password-test-123",
            ruolo=User.Ruolo.ADMIN,
            is_staff=True,
        )

    def test_collaudo_ambiente_con_admin_attivo(self):
        output = StringIO()

        call_command("collauda_ambiente", stdout=output)

        contenuto = output.getvalue()
        self.assertIn("[OK] database", contenuto)
        self.assertIn("[OK] migrazioni", contenuto)
        self.assertIn("[OK] admin_attivi", contenuto)
        self.assertIn("Risultato: OK", contenuto)

    def test_collaudo_json(self):
        output = StringIO()

        call_command(
            "collauda_ambiente",
            "--json",
            stdout=output,
        )

        contenuto = output.getvalue()
        self.assertIn('"esito": "OK"', contenuto)
        self.assertIn('"conteggi_database"', contenuto)
