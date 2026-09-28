from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.operations.models import AuditLog, PeriodoMensile
from apps.operations.services import (
    chiudi_periodo,
    riapri_periodo,
    valorizza_periodo,
)
from apps.projects.models import (
    Assegnazione,
    Cliente,
    Commessa,
    TariffaAssegnazione,
)
from apps.timesheets.models import RigaOre, SpesaTrasferta

User = get_user_model()


class TariffeEPeriodiTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            email="admin-test@example.com",
            password="Password-test-123",
            ruolo=User.Ruolo.ADMIN,
            is_staff=True,
        )
        self.consulente = User.objects.create_user(
            email="consulente-test@example.com",
            password="Password-test-123",
        )
        self.cliente = Cliente.objects.create(
            ragione_sociale="Cliente Test",
            partita_iva="IT00000000041",
        )
        self.commessa = Commessa.objects.create(
            cliente=self.cliente,
            codice="TEST-001",
            descrizione="Test tariffe e periodi",
            data_inizio=date(2026, 1, 1),
        )
        self.assegnazione = Assegnazione.objects.create(
            consulente=self.consulente,
            commessa=self.commessa,
            ore_previste=100,
            data_inizio=date(2026, 1, 1),
        )

    def crea_riga(self, giorno, ore=4):
        return RigaOre.objects.create(
            assegnazione=self.assegnazione,
            data=giorno,
            tipo_attivita=(
                TariffaAssegnazione.TipoAttivita.CONSULENZA
            ),
            ore=ore,
            inserita_da=self.consulente,
            ultima_modifica_da=self.consulente,
        )

    def test_tariffa_storica_applicata_in_base_alla_data(self):
        TariffaAssegnazione.objects.create(
            assegnazione=self.assegnazione,
            tipo_attivita=(
                TariffaAssegnazione.TipoAttivita.CONSULENZA
            ),
            tariffa_oraria=Decimal("80.00"),
            valida_dal=date(2026, 1, 1),
            creata_da=self.admin,
        )
        TariffaAssegnazione.objects.create(
            assegnazione=self.assegnazione,
            tipo_attivita=(
                TariffaAssegnazione.TipoAttivita.CONSULENZA
            ),
            tariffa_oraria=Decimal("95.00"),
            valida_dal=date(2026, 7, 15),
            creata_da=self.admin,
        )
        self.crea_riga(date(2026, 7, 10), ore=2)
        self.crea_riga(date(2026, 7, 20), ore=3)

        riepilogo = valorizza_periodo(2026, 7)

        self.assertEqual(
            riepilogo.totale_importo_ore,
            Decimal("445.00"),
        )
        self.assertEqual(len(riepilogo.righe_senza_tariffa), 0)

    def test_spese_sommate_senza_ricarico(self):
        TariffaAssegnazione.objects.create(
            assegnazione=self.assegnazione,
            tipo_attivita=(
                TariffaAssegnazione.TipoAttivita.CONSULENZA
            ),
            tariffa_oraria=Decimal("100.00"),
            valida_dal=date(2026, 1, 1),
            creata_da=self.admin,
        )
        self.crea_riga(date(2026, 7, 10), ore=2)
        SpesaTrasferta.objects.create(
            assegnazione=self.assegnazione,
            data=date(2026, 7, 10),
            categoria=SpesaTrasferta.Categoria.VIAGGIO,
            importo=Decimal("35.50"),
            inserita_da=self.consulente,
            ultima_modifica_da=self.consulente,
        )

        riepilogo = valorizza_periodo(2026, 7)

        self.assertEqual(riepilogo.totale_spese, Decimal("35.50"))
        self.assertEqual(
            riepilogo.totale_fatturabile,
            Decimal("235.50"),
        )

    def test_tariffa_mancante_blocca_chiusura(self):
        self.crea_riga(date(2026, 7, 10))

        with self.assertRaises(ValidationError):
            chiudi_periodo(
                attore=self.admin,
                anno=2026,
                mese=7,
            )

    def test_forzatura_richiede_motivazione(self):
        self.crea_riga(date(2026, 7, 10))

        with self.assertRaises(ValidationError):
            chiudi_periodo(
                attore=self.admin,
                anno=2026,
                mese=7,
                forza_tariffe_mancanti=True,
                motivazione="",
            )

    def test_chiusura_forzata_e_riapertura_sono_auditabili(self):
        self.crea_riga(date(2026, 7, 10))

        periodo = chiudi_periodo(
            attore=self.admin,
            anno=2026,
            mese=7,
            forza_tariffe_mancanti=True,
            forza_approvazioni_mancanti=True,
            motivazione="Chiusura autorizzata per verifica successiva.",
        )

        self.assertEqual(
            periodo.stato,
            PeriodoMensile.Stato.CHIUSO,
        )

        self.assertTrue(
            periodo.forzatura_tariffe_mancanti
        )

        self.assertTrue(
            periodo.forzatura_approvazioni_mancanti
        )

        periodo = riapri_periodo(
            attore=self.admin,
            anno=2026,
            mese=7,
            motivazione="Correzione tariffa richiesta.",
        )

        self.assertEqual(
            periodo.stato,
            PeriodoMensile.Stato.APERTO,
        )

        self.assertEqual(
            AuditLog.objects.filter(
                entita="PeriodoMensile",
            ).count(),
            2,
        )