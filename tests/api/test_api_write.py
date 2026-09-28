from datetime import date
from decimal import Decimal

from django.urls import reverse
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase

from apps.accounts.models import User
from apps.operations.models import AuditLog, PeriodoMensile
from apps.projects.models import (
    Assegnazione,
    Cliente,
    Commessa,
    TariffaAssegnazione,
)
from apps.timesheets.models import RigaOre, SpesaTrasferta


class ApiWriteTests(APITestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            email="admin-test@example.com",
            password="Password-test-123",
            ruolo=User.Ruolo.ADMIN,
            is_active=True,
        )
        self.consulente = User.objects.create_user(
            email="consulente-test@example.com",
            password="Password-test-123",
            ruolo=User.Ruolo.CONSULENTE,
            is_active=True,
        )
        self.pm = User.objects.create_user(
            email="pm-test@example.com",
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
            partita_iva="13000000001",
        )
        self.commessa = Commessa.objects.create(
            cliente=self.cliente,
            codice="TEST",
            descrizione="Commessa test API scrittura",
            ore_budget=200,
            data_inizio=date(2026, 1, 1),
        )
        self.altra_commessa = Commessa.objects.create(
            cliente=self.cliente,
            codice="TEST-ALT",
            descrizione="Altra commessa",
            ore_budget=200,
            data_inizio=date(2026, 1, 1),
        )

        self.assegnazione = Assegnazione.objects.create(
            consulente=self.consulente,
            commessa=self.commessa,
            ore_previste=80,
            data_inizio=date(2026, 1, 1),
        )
        self.assegnazione_pm = Assegnazione.objects.create(
            consulente=self.pm,
            commessa=self.commessa,
            ore_previste=20,
            ruolo_commessa=Assegnazione.Ruolo.PROJECT_MANAGER,
            data_inizio=date(2026, 1, 1),
        )
        self.assegnazione_altra = Assegnazione.objects.create(
            consulente=self.altro,
            commessa=self.altra_commessa,
            ore_previste=80,
            data_inizio=date(2026, 1, 1),
        )

    def authenticate(self, user):
        token, _ = Token.objects.get_or_create(user=user)
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Token {token.key}"
        )

    def ore_payload(self, assegnazione=None, **overrides):
        payload = {
            "assegnazione_id": str(
                (assegnazione or self.assegnazione).id
            ),
            "data": "2026-07-10",
            "tipo_attivita": (
                TariffaAssegnazione.TipoAttivita.CONSULENZA
            ),
            "ore": 4,
            "nota": "Attività tramite API",
        }
        payload.update(overrides)
        return payload

    def spesa_payload(self, assegnazione=None, **overrides):
        payload = {
            "assegnazione_id": str(
                (assegnazione or self.assegnazione).id
            ),
            "data": "2026-07-10",
            "categoria": SpesaTrasferta.Categoria.VIAGGIO,
            "importo": "25.50",
            "nota": "Spesa tramite API",
        }
        payload.update(overrides)
        return payload

    def test_consultant_can_create_own_hours(self):
        self.authenticate(self.consulente)

        response = self.client.post(
            reverse("api:ore-list"),
            self.ore_payload(),
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["riga"]["ore"], 4)
        self.assertFalse(
            response.data["avvisi"]["limite_giornaliero_superato"]
        )

        riga = RigaOre.objects.get(
            pk=response.data["riga"]["id"]
        )
        self.assertEqual(riga.inserita_da, self.consulente)
        self.assertFalse(riga.bloccata_per_consulente)

    def test_consultant_cannot_create_for_another_user(self):
        self.authenticate(self.consulente)

        response = self.client.post(
            reverse("api:ore-list"),
            self.ore_payload(self.assegnazione_altra),
            format="json",
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(RigaOre.objects.count(), 0)

    def test_consultant_cannot_exceed_eight_hours(self):
        RigaOre.objects.create(
            assegnazione=self.assegnazione,
            data=date(2026, 7, 10),
            tipo_attivita=(
                TariffaAssegnazione.TipoAttivita.CONSULENZA
            ),
            ore=6,
            inserita_da=self.consulente,
            ultima_modifica_da=self.consulente,
        )
        self.authenticate(self.consulente)

        response = self.client.post(
            reverse("api:ore-list"),
            self.ore_payload(ore=3),
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(RigaOre.objects.count(), 1)

    def test_admin_can_exceed_eight_hours_and_creates_audit(self):
        RigaOre.objects.create(
            assegnazione=self.assegnazione,
            data=date(2026, 7, 10),
            tipo_attivita=(
                TariffaAssegnazione.TipoAttivita.CONSULENZA
            ),
            ore=8,
            inserita_da=self.consulente,
            ultima_modifica_da=self.consulente,
        )
        self.authenticate(self.admin)

        response = self.client.post(
            reverse("api:ore-list"),
            self.ore_payload(
                ore=2,
                motivazione="Eccezione amministrativa oltre 8 ore.",
            ),
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertTrue(
            response.data["avvisi"]["limite_giornaliero_superato"]
        )

        riga = RigaOre.objects.get(pk=response.data["riga"]["id"])
        self.assertTrue(riga.bloccata_per_consulente)
        self.assertTrue(
            AuditLog.objects.filter(
                entita="RigaOre",
                entita_id=riga.id,
                azione="INSERIMENTO_ADMIN",
                motivazione="Eccezione amministrativa oltre 8 ore.",
            ).exists()
        )

    def test_patch_increments_version_and_stale_version_returns_409(self):
        riga = RigaOre.objects.create(
            assegnazione=self.assegnazione,
            data=date(2026, 7, 10),
            tipo_attivita=(
                TariffaAssegnazione.TipoAttivita.CONSULENZA
            ),
            ore=4,
            inserita_da=self.consulente,
            ultima_modifica_da=self.consulente,
        )
        self.authenticate(self.consulente)
        url = reverse("api:ore-detail", args=[riga.id])

        first = self.client.patch(
            url,
            {"ore": 5, "versione": 1},
            format="json",
        )
        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.data["riga"]["versione"], 2)

        stale = self.client.patch(
            url,
            {"ore": 6, "versione": 1},
            format="json",
        )
        self.assertEqual(stale.status_code, 409)

        riga.refresh_from_db()
        self.assertEqual(riga.ore, 5)
        self.assertEqual(riga.versione, 2)

    def test_pm_cannot_modify_team_member_hours(self):
        riga = RigaOre.objects.create(
            assegnazione=self.assegnazione,
            data=date(2026, 7, 10),
            tipo_attivita=(
                TariffaAssegnazione.TipoAttivita.CONSULENZA
            ),
            ore=4,
            inserita_da=self.consulente,
            ultima_modifica_da=self.consulente,
        )
        self.authenticate(self.pm)

        response = self.client.patch(
            reverse("api:ore-detail", args=[riga.id]),
            {"ore": 5, "versione": 1},
            format="json",
        )

        self.assertEqual(response.status_code, 403)
        riga.refresh_from_db()
        self.assertEqual(riga.ore, 4)

    def test_closed_period_returns_423(self):
        PeriodoMensile.objects.create(
            anno=2026,
            mese=7,
            stato=PeriodoMensile.Stato.CHIUSO,
            chiuso_da=self.admin,
        )
        self.authenticate(self.consulente)

        response = self.client.post(
            reverse("api:ore-list"),
            self.ore_payload(),
            format="json",
        )

        self.assertEqual(response.status_code, 423)

    def test_delete_requires_current_version(self):
        riga = RigaOre.objects.create(
            assegnazione=self.assegnazione,
            data=date(2026, 7, 10),
            tipo_attivita=(
                TariffaAssegnazione.TipoAttivita.CONSULENZA
            ),
            ore=4,
            inserita_da=self.consulente,
            ultima_modifica_da=self.consulente,
        )
        self.authenticate(self.consulente)
        url = reverse("api:ore-detail", args=[riga.id])

        missing = self.client.delete(url)
        self.assertEqual(missing.status_code, 400)

        deleted = self.client.delete(f"{url}?versione=1")
        self.assertEqual(deleted.status_code, 204)
        self.assertFalse(RigaOre.objects.filter(pk=riga.id).exists())

    def test_expense_create_patch_and_delete(self):
        self.authenticate(self.consulente)

        created = self.client.post(
            reverse("api:spesa-list"),
            self.spesa_payload(),
            format="json",
        )
        self.assertEqual(created.status_code, 201)

        spesa_id = created.data["spesa"]["id"]
        url = reverse("api:spesa-detail", args=[spesa_id])

        updated = self.client.patch(
            url,
            {"importo": "31.75", "versione": 1},
            format="json",
        )
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(
            Decimal(updated.data["spesa"]["importo"]),
            Decimal("31.75"),
        )
        self.assertEqual(updated.data["spesa"]["versione"], 2)

        deleted = self.client.delete(
            url,
            HTTP_IF_MATCH='"2"',
        )
        self.assertEqual(deleted.status_code, 204)
        self.assertFalse(
            SpesaTrasferta.objects.filter(pk=spesa_id).exists()
        )
