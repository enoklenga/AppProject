from datetime import date
from decimal import Decimal

from django.contrib.staticfiles import finders
from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import User
from apps.operations.dashboard_visuals import dashboard_consulente
from apps.projects.models import Assegnazione, Cliente, Commessa, TariffaAssegnazione
from apps.timesheets.models import RigaOre, SpesaTrasferta


class DashboardVisualizationTests(TestCase):
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
        self.cliente = Cliente.objects.create(
            ragione_sociale="Cliente Test",
            partita_iva="19000000001",
        )
        self.commessa = Commessa.objects.create(
            cliente=self.cliente,
            codice="TEST",
            descrizione="Commessa dashboard test",
            ore_budget=160,
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
        TariffaAssegnazione.objects.create(
            assegnazione=self.assegnazione,
            tipo_attivita=TariffaAssegnazione.TipoAttivita.CONSULENZA,
            tariffa_oraria=Decimal("100.00"),
            valida_dal=date(2026, 1, 1),
            creata_da=self.admin,
        )
        RigaOre.objects.create(
            assegnazione=self.assegnazione,
            data=date(2026, 7, 10),
            tipo_attivita=TariffaAssegnazione.TipoAttivita.CONSULENZA,
            ore=4,
            inserita_da=self.consulente,
            ultima_modifica_da=self.consulente,
        )
        RigaOre.objects.create(
            assegnazione=self.assegnazione,
            data=date(2026, 7, 11),
            tipo_attivita=TariffaAssegnazione.TipoAttivita.CONSULENZA,
            ore=6,
            inserita_da=self.consulente,
            ultima_modifica_da=self.consulente,
        )
        SpesaTrasferta.objects.create(
            assegnazione=self.assegnazione,
            data=date(2026, 7, 10),
            categoria=SpesaTrasferta.Categoria.VIAGGIO,
            importo=Decimal("25.00"),
            inserita_da=self.consulente,
            ultima_modifica_da=self.consulente,
        )

    def test_dashboard_static_assets_are_discoverable(self):
        self.assertTrue(finders.find("css/dashboard.css"))
        self.assertTrue(finders.find("js/dashboard.js"))

    def test_personal_dashboard_service_contains_real_month_data(self):
        dati = dashboard_consulente(
            utente=self.consulente,
            anno=2026,
            mese=7,
        )
        self.assertEqual(dati["totale_ore_periodo"], 10)
        self.assertEqual(dati["totale_spese_periodo"], Decimal("25.00"))
        self.assertEqual(dati["giorni_compilati"], 2)
        self.assertEqual(len(dati["assegnazioni_attive"]), 1)
        self.assertEqual(
            sum(dati["chart_ore_giornaliere"]["series"][0]["values"]),
            10,
        )

    def test_consultant_home_renders_personal_visualizations(self):
        self.client.force_login(self.consulente)
        response = self.client.get(reverse("home"), {"mese": "2026-07"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "chart-consultant-daily-data")
        self.assertContains(response, "chart-consultant-project-data")
        self.assertContains(response, ">10<", html=False)
        self.assertNotContains(response, "Valore ore")

    def test_admin_dashboard_renders_economic_visualizations(self):
        self.client.force_login(self.admin)
        response = self.client.get(
            reverse("operations:dashboard-admin"),
            {"mese": "2026-07"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "chart-admin-daily-data")
        self.assertContains(response, "chart-admin-client-data")
        self.assertContains(response, "chart-admin-project-data")
        self.assertContains(response, "Valore ore")

    def test_pm_dashboard_renders_team_visuals_without_economics(self):
        self.client.force_login(self.pm)
        response = self.client.get(
            reverse("operations:dashboard-pm"),
            {"mese": "2026-07", "commessa": str(self.commessa.id)},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "chart-pm-daily-data")
        self.assertContains(response, "chart-pm-team-data")
        self.assertNotContains(response, "Valore ore")
        self.assertNotContains(response, "Totale valorizzato")

    def test_consultant_cannot_open_admin_dashboard(self):
        self.client.force_login(self.consulente)
        response = self.client.get(reverse("operations:dashboard-admin"))
        self.assertEqual(response.status_code, 403)
