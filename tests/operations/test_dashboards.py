from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.test import TestCase
from django.urls import reverse

from apps.operations.services import (
    commesse_gestite_da_pm,
    dashboard_admin,
    dashboard_pm,
)
from apps.projects.models import (
    Assegnazione,
    Cliente,
    Commessa,
    TariffaAssegnazione,
)
from apps.timesheets.models import RigaOre, SpesaTrasferta

User = get_user_model()


class DashboardTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            email="admin-test@example.com",
            password="Password-test-123",
            ruolo=User.Ruolo.ADMIN,
            is_staff=True,
        )
        self.pm = User.objects.create_user(
            email="pm-test@example.com",
            password="Password-test-123",
        )
        self.consulente = User.objects.create_user(
            email="consulente-test@example.com",
            password="Password-test-123",
        )
        self.cliente = Cliente.objects.create(
            ragione_sociale="Cliente Dashboard",
            partita_iva="IT00000000051",
        )
        self.commessa = Commessa.objects.create(
            cliente=self.cliente,
            codice="DASH-001",
            descrizione="Commessa dashboard",
            data_inizio=date(2026, 1, 1),
        )
        self.altra_commessa = Commessa.objects.create(
            cliente=self.cliente,
            codice="DASH-002",
            descrizione="Commessa non gestita",
            data_inizio=date(2026, 1, 1),
        )
        self.assegnazione_pm = Assegnazione.objects.create(
            consulente=self.pm,
            commessa=self.commessa,
            ore_previste=20,
            ruolo_commessa=Assegnazione.Ruolo.PROJECT_MANAGER,
            data_inizio=date(2026, 1, 1),
        )
        self.assegnazione_consulente = Assegnazione.objects.create(
            consulente=self.consulente,
            commessa=self.commessa,
            ore_previste=40,
            data_inizio=date(2026, 1, 1),
        )
        self.assegnazione_altra = Assegnazione.objects.create(
            consulente=self.consulente,
            commessa=self.altra_commessa,
            ore_previste=30,
            data_inizio=date(2026, 1, 1),
        )
        TariffaAssegnazione.objects.create(
            assegnazione=self.assegnazione_consulente,
            tipo_attivita=(
                TariffaAssegnazione.TipoAttivita.CONSULENZA
            ),
            tariffa_oraria=Decimal("100.00"),
            valida_dal=date(2026, 1, 1),
            creata_da=self.admin,
        )
        RigaOre.objects.create(
            assegnazione=self.assegnazione_consulente,
            data=date(2026, 7, 15),
            tipo_attivita=(
                TariffaAssegnazione.TipoAttivita.CONSULENZA
            ),
            ore=4,
            nota="Analisi processo cliente",
            inserita_da=self.consulente,
            ultima_modifica_da=self.consulente,
        )
        SpesaTrasferta.objects.create(
            assegnazione=self.assegnazione_consulente,
            data=date(2026, 7, 15),
            categoria=SpesaTrasferta.Categoria.VIAGGIO,
            importo=Decimal("35.00"),
            nota="Pedaggio",
            inserita_da=self.consulente,
            ultima_modifica_da=self.consulente,
        )

    def test_dashboard_admin_calcola_valori_e_spese(self):
        dati = dashboard_admin(anno=2026, mese=7)

        self.assertEqual(dati.totale_ore, 4)
        self.assertEqual(
            dati.totale_valore_ore,
            Decimal("400.00"),
        )
        self.assertEqual(dati.totale_spese, Decimal("35.00"))
        self.assertEqual(
            dati.totale_fatturabile,
            Decimal("435.00"),
        )

    def test_pm_vede_solo_commesse_gestite(self):
        gestite = list(commesse_gestite_da_pm(self.pm))

        self.assertEqual(gestite, [self.commessa])

    def test_dashboard_pm_contiene_ore_e_note(self):
        dati = dashboard_pm(
            utente=self.pm,
            commessa_id=self.commessa.id,
            anno=2026,
            mese=7,
        )

        self.assertEqual(dati.totale_ore_periodo, 4)
        self.assertEqual(
            dati.righe_ore[0].nota,
            "Analisi processo cliente",
        )
        self.assertFalse(hasattr(dati, "totale_fatturabile"))
        self.assertFalse(hasattr(dati, "totale_spese"))

    def test_pm_non_accede_a_commessa_non_gestita(self):
        with self.assertRaises(PermissionDenied):
            dashboard_pm(
                utente=self.pm,
                commessa_id=self.altra_commessa.id,
                anno=2026,
                mese=7,
            )

    def test_rimozione_ruolo_pm_revoca_accesso(self):
        self.assegnazione_pm.ruolo_commessa = (
            Assegnazione.Ruolo.CONSULENTE
        )
        self.assegnazione_pm.save()

        with self.assertRaises(PermissionDenied):
            dashboard_pm(
                utente=self.pm,
                commessa_id=self.commessa.id,
                anno=2026,
                mese=7,
            )

    def test_pagina_pm_non_mostra_importi_o_spese(self):
        self.client.force_login(self.pm)
        response = self.client.get(
            reverse("operations:dashboard-pm"),
            {
                "mese": "2026-07",
                "commessa": str(self.commessa.id),
            },
        )

        self.assertEqual(response.status_code, 200)
        contenuto = response.content.decode("utf-8")
        self.assertIn("Analisi processo cliente", contenuto)
        self.assertNotIn("€ 400", contenuto)
        self.assertNotIn("Pedaggio", contenuto)

    def test_pagina_admin_richiede_ruolo_admin(self):
        self.client.force_login(self.consulente)
        response = self.client.get(
            reverse("operations:dashboard-admin")
        )

        self.assertEqual(response.status_code, 403)
