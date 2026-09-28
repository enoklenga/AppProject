from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.projects.models import Cliente, Commessa

User = get_user_model()


class AdminInterfaceTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            email="admin-ui@example.com",
            password="password-test-123",
            ruolo=User.Ruolo.ADMIN,
        )
        self.consulente = User.objects.create_user(
            email="consulente-ui@example.com",
            password="password-test-123",
            ruolo=User.Ruolo.CONSULENTE,
        )

    def test_admin_accede_alla_lista_clienti(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse("projects:cliente-list"))
        self.assertEqual(response.status_code, 200)

    def test_consulente_non_accede_alla_gestione(self):
        self.client.force_login(self.consulente)
        response = self.client.get(reverse("projects:cliente-list"))
        self.assertEqual(response.status_code, 403)

    def test_creazione_cliente(self):
        self.client.force_login(self.admin)
        response = self.client.post(
            reverse("projects:cliente-create"),
            {
                "ragione_sociale": "Cliente UI",
                "partita_iva": "IT98765432109",
                "referente": "Mario Rossi",
                "note": "",
                "attivo": "on",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Cliente.objects.filter(partita_iva="IT98765432109").exists())

    def test_chiusura_commessa(self):
        cliente = Cliente.objects.create(
            ragione_sociale="Cliente Commessa",
            partita_iva="IT11111111111",
        )
        commessa = Commessa.objects.create(
            cliente=cliente,
            codice="UI-001",
            descrizione="Test UI",
            data_inizio=date(2026, 7, 1),
        )
        self.client.force_login(self.admin)
        self.client.post(
            reverse("projects:commessa-toggle-state", args=[commessa.pk])
        )
        commessa.refresh_from_db()
        self.assertEqual(commessa.stato, Commessa.Stato.CHIUSA)
