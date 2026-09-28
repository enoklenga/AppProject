from datetime import date

from django.contrib.messages import get_messages
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import User
from apps.phases.models import FaseCommessa
from apps.phases.services import delete_fase
from apps.projects.models import Cliente, Commessa


class FaseDeleteTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            email="admin-fasi@test.it",
            password="Password123!",
            ruolo=User.Ruolo.ADMIN,
            deve_cambiare_password=False,
        )
        self.cliente = Cliente.objects.create(
            ragione_sociale="Cliente Fasi",
            partita_iva="12345678901",
        )
        self.commessa = Commessa.objects.create(
            cliente=self.cliente,
            codice="FASE-DELETE-001",
            descrizione="Test eliminazione fase",
            data_inizio=date(2026, 1, 1),
        )
        self.generale = FaseCommessa.objects.get(
            commessa=self.commessa,
            sistema=True,
        )
        self.fase = FaseCommessa.objects.create(
            commessa=self.commessa,
            nome="Fase eliminabile",
            data_inizio=self.commessa.data_inizio,
            creata_da=self.admin,
        )
        self.client.force_login(self.admin)

    def test_fase_di_sistema_non_restituisce_403(self):
        response = self.client.get(
            reverse("phases:fase-delete", args=[self.generale.pk])
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response.url,
            f"{reverse('phases:fase-list')}?commessa={self.commessa.pk}",
        )
        messaggi = [str(message) for message in get_messages(response.wsgi_request)]
        self.assertTrue(any("fase predefinita" in message.lower() for message in messaggi))
        self.assertTrue(FaseCommessa.objects.filter(pk=self.generale.pk).exists())

    def test_service_tratta_fase_di_sistema_come_validation_error(self):
        with self.assertRaises(ValidationError):
            delete_fase(user=self.admin, fase=self.generale)

    def test_admin_puo_aprire_conferma_per_fase_normale(self):
        response = self.client.get(
            reverse("phases:fase-delete", args=[self.fase.pk])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Elimina fase")

    def test_admin_puo_eliminare_fase_normale_senza_dipendenze(self):
        response = self.client.post(
            reverse("phases:fase-delete", args=[self.fase.pk])
        )

        self.assertEqual(response.status_code, 302)
        self.assertFalse(FaseCommessa.objects.filter(pk=self.fase.pk).exists())

    def test_lista_non_mostra_elimina_per_fase_di_sistema(self):
        response = self.client.get(
            reverse("phases:fase-list"),
            {"commessa": self.commessa.pk},
        )

        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn("Predefinita", content)
        self.assertNotIn(
            reverse("phases:fase-delete", args=[self.generale.pk]),
            content,
        )
        self.assertIn(
            reverse("phases:fase-delete", args=[self.fase.pk]),
            content,
        )
