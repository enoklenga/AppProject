import io
from datetime import date, time

from django.core import mail
from django.test import override_settings
from django.urls import reverse
from openpyxl import Workbook
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase

from apps.accounts.models import User
from apps.api.models import ApiImportazioneAnteprima
from apps.operations.models import (
    AuditLog,
    ConfigurazionePromemoria,
    Importazione,
    InvioPromemoria,
)
from apps.phases.models import FaseCommessa
from apps.projects.models import Assegnazione, Cliente, Commessa
from apps.timesheets.models import RigaOre



@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    DEFAULT_FROM_EMAIL="timesheet-test@example.com",
    SITE_URL="http://testserver",
)
class OperationsApiTests(APITestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            email="admin-test@example.com",
            password="Password-test-123",
            ruolo=User.Ruolo.ADMIN,
            is_active=True,
            is_staff=True,
        )
        self.consulente = User.objects.create_user(
            email="consulente-test@example.com",
            password="Password-test-123",
            ruolo=User.Ruolo.CONSULENTE,
            is_active=True,
        )
        self.altro = User.objects.create_user(
            email="altro-test@example.com",
            password="Password-test-123",
            ruolo=User.Ruolo.CONSULENTE,
            is_active=True,
        )

        self.cliente = Cliente.objects.create(
            ragione_sociale="Cliente Test",
            partita_iva="15000000001",
        )
        self.commessa = Commessa.objects.create(
            cliente=self.cliente,
            codice="TEST",
            descrizione="Commessa test",
            ore_budget=100,
            data_inizio=date(2026, 1, 1),
        )

        self.fase = FaseCommessa.objects.get(
            commessa=self.commessa,
            sistema=True,
        )

        self.assegnazione = Assegnazione.objects.create(
            consulente=self.consulente,
            commessa=self.commessa,
            fase=self.fase,
            ore_previste=50,
            data_inizio=date(2026, 1, 1),
        )

        self.assegnazione_altro = Assegnazione.objects.create(
            consulente=self.altro,
            commessa=self.commessa,
            fase=self.fase,
            ore_previste=50,
            data_inizio=date(2026, 1, 1),
        )
        
        RigaOre.objects.create(
            assegnazione=self.assegnazione_altro,
            data=date(2026, 7, 10),
            tipo_attivita="CONSULENZA",
            ore=4,
            inserita_da=self.altro,
            ultima_modifica_da=self.altro,
        )
        self.configurazione = ConfigurazionePromemoria.objects.create(
            giorno_invio=25,
            ora_invio=time(9, 0),
            attiva=True,
            solo_assenza_totale_ore=True,
            aggiornata_da=self.admin,
        )

    def authenticate(self, user):
        token, _ = Token.objects.get_or_create(user=user)
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Token {token.key}"
        )

    def crea_xlsx_ore(self):
        workbook = Workbook()
        worksheet = workbook.active

        worksheet.append(
            [
                "consulente_email",
                "codice_commessa",
                "fase",
                "data",
                "tipo_attivita",
                "ore",
                "nota",
            ]
        )

        worksheet.append(
            [
                self.consulente.email,
                self.commessa.codice,
                self.fase.nome,
                "2026-07-15",
                "CONSULENZA",
                6,
                "Inserimento API",
            ]
        )

        output = io.BytesIO()
        workbook.save(output)
        output.seek(0)
        output.name = "ore_test.xlsx"

        return output

    def test_non_admin_cannot_access_operations_api(self):
        self.authenticate(self.consulente)

        urls = [
            reverse("api:promemoria-configurazione-api"),
            reverse("api:importazioni-api"),
            reverse("api:audit-api"),
        ]
        for url in urls:
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 403)

    def test_admin_gets_and_updates_reminder_configuration(self):
        self.authenticate(self.admin)

        response = self.client.get(
            reverse("api:promemoria-configurazione-api")
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["giorno_invio"], 25)

        update = self.client.patch(
            reverse("api:promemoria-configurazione-api"),
            {"giorno_invio": 24, "attiva": False},
        )
        self.assertEqual(update.status_code, 200)
        self.assertEqual(update.data["giorno_invio"], 24)
        self.assertFalse(update.data["attiva"])

        self.configurazione.refresh_from_db()
        self.assertEqual(self.configurazione.aggiornata_da, self.admin)

    def test_preview_and_manual_reminder_send(self):
        self.authenticate(self.admin)

        preview = self.client.get(
            reverse("api:promemoria-anteprima-api"),
            {"anno": 2026, "mese": 7},
        )
        self.assertEqual(preview.status_code, 200)
        self.assertEqual(preview.data["totale_destinatari"], 1)
        self.assertEqual(
            preview.data["destinatari"][0]["consulente"]["email"],
            self.consulente.email,
        )

        send = self.client.post(
            reverse("api:promemoria-invia-api"),
            {"anno": 2026, "mese": 7, "conferma": True},
        )
        self.assertEqual(send.status_code, 200)
        self.assertEqual(send.data["inviati"], 1)
        self.assertEqual(len(mail.outbox), 1)
        self.assertTrue(
            InvioPromemoria.objects.filter(
                consulente=self.consulente,
                anno=2026,
                mese=7,
                stato=InvioPromemoria.Stato.INVIATO,
            ).exists()
        )

        registry = self.client.get(
            reverse("api:promemoria-invii-api"),
            {"anno": 2026, "mese": 7},
        )
        self.assertEqual(registry.status_code, 200)
        self.assertEqual(registry.data["count"], 1)

    def test_import_upload_and_commit_are_persistent(self):
        self.authenticate(self.admin)
        file = self.crea_xlsx_ore()

        upload = self.client.post(
            reverse("api:importazioni-upload-api"),
            {
                "tipo_importazione": "ORE",
                "file": file,
            },
            format="multipart",
        )
        self.assertEqual(upload.status_code, 201)
        self.assertEqual(
            upload.data["importazione"]["stato"],
            Importazione.Stato.PRONTA,
        )

        importazione_id = upload.data["importazione"]["id"]
        self.assertTrue(
            ApiImportazioneAnteprima.objects.filter(
                importazione_id=importazione_id
            ).exists()
        )

        commit = self.client.post(
            reverse(
                "api:importazioni-conferma-api",
                kwargs={"pk": importazione_id},
            ),
            {"conferma": True},
        )
        self.assertEqual(commit.status_code, 200)
        self.assertEqual(
            commit.data["stato"],
            Importazione.Stato.COMPLETATA,
        )
        self.assertFalse(
            ApiImportazioneAnteprima.objects.filter(
                importazione_id=importazione_id
            ).exists()
        )
        self.assertTrue(
            RigaOre.objects.filter(
                assegnazione=self.assegnazione,
                data=date(2026, 7, 15),
                ore=6,
                bloccata_per_consulente=True,
            ).exists()
        )

    def test_audit_is_read_only_and_csv_is_available(self):
        AuditLog.objects.create(
            utente=self.admin,
            entita="RigaOre",
            entita_id=self.assegnazione.id,
            azione="TEST_AUDIT",
            valore_precedente=None,
            valore_nuovo={"ok": True},
            motivazione="Test API",
        )
        self.authenticate(self.admin)

        listing = self.client.get(
            reverse("api:audit-api"),
            {"azione": "TEST"},
        )
        self.assertEqual(listing.status_code, 200)
        self.assertEqual(listing.data["count"], 1)

        forbidden_write = self.client.post(
            reverse("api:audit-api"),
            {"azione": "NON_CONSENTITA"},
        )
        self.assertEqual(forbidden_write.status_code, 405)

        csv_response = self.client.get(
            reverse("api:audit-csv-api"),
            {"azione": "TEST"},
        )
        self.assertEqual(csv_response.status_code, 200)
        self.assertIn(
            "text/csv",
            csv_response["Content-Type"],
        )
        self.assertIn(
            "TEST_AUDIT",
            csv_response.content.decode("utf-8-sig"),
        )
