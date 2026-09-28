from uuid import uuid4

from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import User
from apps.operations.models import AuditLog


class ExportSecurityTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            email="admin-export@example.com",
            password="Password-test-Export-123",
            ruolo=User.Ruolo.ADMIN,
            is_staff=True,
        )
        self.client.force_login(self.admin)

    def test_csv_audit_neutralizza_formula_in_motivazione(self):
        AuditLog.objects.create(
            utente=self.admin,
            entita="Test",
            entita_id=uuid4(),
            azione="TEST",
            motivazione='=HYPERLINK("https://example.invalid","click")',
        )

        response = self.client.get(reverse("operations:audit-csv"))

        self.assertEqual(response.status_code, 200)
        text = response.content.decode("utf-8-sig")
        self.assertIn("'=HYPERLINK", text)
