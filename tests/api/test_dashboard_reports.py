from datetime import date
from decimal import Decimal

from django.urls import reverse
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase

from apps.accounts.models import User
from apps.operations.models import PeriodoMensile
from apps.projects.models import (
    Assegnazione,
    Cliente,
    Commessa,
    TariffaAssegnazione,
)
from apps.timesheets.models import RigaOre, SpesaTrasferta


class DashboardReportApiTests(APITestCase):
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
            partita_iva="14000000001",
        )
        self.altro_cliente = Cliente.objects.create(
            ragione_sociale="Altro cliente Test",
            partita_iva="14000000002",
        )

        self.commessa = Commessa.objects.create(
            cliente=self.cliente,
            codice="TEST",
            descrizione="Commessa dashboard",
            ore_budget=200,
            data_inizio=date(2026, 1, 1),
        )
        self.commessa_non_gestita = Commessa.objects.create(
            cliente=self.altro_cliente,
            codice="TEST-ALT",
            descrizione="Commessa non gestita",
            ore_budget=100,
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
            commessa=self.commessa_non_gestita,
            ore_previste=50,
            data_inizio=date(2026, 1, 1),
        )

        TariffaAssegnazione.objects.create(
            assegnazione=self.assegnazione,
            tipo_attivita=(
                TariffaAssegnazione.TipoAttivita.CONSULENZA
            ),
            tariffa_oraria=Decimal("100.00"),
            valida_dal=date(2026, 1, 1),
            creata_da=self.admin,
        )
        TariffaAssegnazione.objects.create(
            assegnazione=self.assegnazione_altra,
            tipo_attivita=(
                TariffaAssegnazione.TipoAttivita.CONSULENZA
            ),
            tariffa_oraria=Decimal("80.00"),
            valida_dal=date(2026, 1, 1),
            creata_da=self.admin,
        )

        self.riga = RigaOre.objects.create(
            assegnazione=self.assegnazione,
            data=date(2026, 7, 10),
            tipo_attivita=(
                TariffaAssegnazione.TipoAttivita.CONSULENZA
            ),
            ore=4,
            inserita_da=self.consulente,
            ultima_modifica_da=self.consulente,
        )
        self.riga_altra = RigaOre.objects.create(
            assegnazione=self.assegnazione_altra,
            data=date(2026, 7, 10),
            tipo_attivita=(
                TariffaAssegnazione.TipoAttivita.CONSULENZA
            ),
            ore=5,
            inserita_da=self.altro,
            ultima_modifica_da=self.altro,
        )
        self.spesa = SpesaTrasferta.objects.create(
            assegnazione=self.assegnazione,
            data=date(2026, 7, 10),
            categoria=SpesaTrasferta.Categoria.VIAGGIO,
            importo=Decimal("25.00"),
            inserita_da=self.consulente,
            ultima_modifica_da=self.consulente,
        )

        PeriodoMensile.objects.create(
            anno=2026,
            mese=7,
            stato=PeriodoMensile.Stato.APERTO,
        )

    def authenticate(self, user):
        token, _ = Token.objects.get_or_create(user=user)
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Token {token.key}"
        )

    def test_personal_dashboard_contains_only_personal_data(self):
        self.authenticate(self.consulente)

        response = self.client.get(
            reverse("api:dashboard-me"),
            {"anno": 2026, "mese": 7},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["totale_ore_periodo"], 4)
        self.assertEqual(
            Decimal(response.data["totale_spese_periodo"]),
            Decimal("25.00"),
        )
        self.assertEqual(len(response.data["commesse"]), 1)
        self.assertEqual(
            response.data["commesse"][0]["codice"],
            "TEST",
        )
        self.assertNotIn("totale_fatturabile", response.data)

    def test_admin_dashboard_exposes_economic_values_to_admin(self):
        self.authenticate(self.admin)

        response = self.client.get(
            reverse("api:dashboard-admin-api"),
            {"anno": 2026, "mese": 7},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["totale_ore"], 9)
        self.assertEqual(
            Decimal(response.data["totale_valore_ore"]),
            Decimal("800.00"),
        )
        self.assertEqual(
            Decimal(response.data["totale_spese"]),
            Decimal("25.00"),
        )
        self.assertEqual(
            Decimal(response.data["totale_fatturabile"]),
            Decimal("825.00"),
        )

    def test_admin_dashboard_is_forbidden_to_consultant(self):
        self.authenticate(self.consulente)

        response = self.client.get(
            reverse("api:dashboard-admin-api"),
            {"anno": 2026, "mese": 7},
        )

        self.assertEqual(response.status_code, 403)

    def test_pm_dashboard_contains_team_hours_without_economics(self):
        self.authenticate(self.pm)

        response = self.client.get(
            reverse("api:dashboard-pm-api"),
            {
                "anno": 2026,
                "mese": 7,
                "commessa_id": str(self.commessa.id),
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["totale_ore_periodo"], 4)
        self.assertEqual(len(response.data["team"]), 2)
        self.assertNotIn("totale_valore_ore", response.data)
        self.assertNotIn("totale_fatturabile", response.data)
        self.assertNotIn("tariffa_oraria", response.data)

    def test_pm_cannot_open_unmanaged_project_dashboard(self):
        self.authenticate(self.pm)

        response = self.client.get(
            reverse("api:dashboard-pm-api"),
            {
                "anno": 2026,
                "mese": 7,
                "commessa_id": str(self.commessa_non_gestita.id),
            },
        )

        self.assertEqual(response.status_code, 403)

    def test_non_pm_cannot_open_pm_dashboard(self):
        self.authenticate(self.consulente)

        response = self.client.get(
            reverse("api:dashboard-pm-api"),
            {
                "anno": 2026,
                "mese": 7,
                "commessa_id": str(self.commessa.id),
            },
        )

        self.assertEqual(response.status_code, 403)

    def test_admin_json_report_contains_detail_and_values(self):
        self.authenticate(self.admin)

        response = self.client.get(
            reverse("api:report-mensile-api"),
            {"anno": 2026, "mese": 7},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["periodo"]["testo"], "07/2026")
        self.assertEqual(len(response.data["ore"]), 2)
        self.assertEqual(len(response.data["spese"]), 1)

        riga = next(
            elemento
            for elemento in response.data["ore"]
            if elemento["id"] == str(self.riga.id)
        )
        self.assertEqual(
            Decimal(riga["tariffa_oraria"]),
            Decimal("100.00"),
        )
        self.assertEqual(
            Decimal(riga["importo_valorizzato"]),
            Decimal("400.00"),
        )

    def test_excel_report_is_downloadable_only_by_admin(self):
        self.authenticate(self.admin)

        response = self.client.get(
            reverse("api:report-mensile-excel-api"),
            {"anno": 2026, "mese": 7},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response["Content-Type"],
            (
                "application/vnd.openxmlformats-officedocument."
                "spreadsheetml.sheet"
            ),
        )
        self.assertTrue(response.content.startswith(b"PK"))
        self.assertIn(
            "LEF_Timesheet_Report_2026_07.xlsx",
            response["Content-Disposition"],
        )

        self.authenticate(self.consulente)
        forbidden = self.client.get(
            reverse("api:report-mensile-excel-api"),
            {"anno": 2026, "mese": 7},
        )
        self.assertEqual(forbidden.status_code, 403)

    def test_invalid_month_returns_400(self):
        self.authenticate(self.admin)

        response = self.client.get(
            reverse("api:dashboard-admin-api"),
            {"anno": 2026, "mese": 13},
        )

        self.assertEqual(response.status_code, 400)
