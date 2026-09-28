from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase

from apps.operations.models import PeriodoMensile
from apps.projects.models import (
    Assegnazione,
    Cliente,
    Commessa,
    TariffaAssegnazione,
)
from apps.timesheets.models import RigaOre
from apps.timesheets.services import (
    inserisci_ore,
    inserisci_spesa,
    modifica_ore,
)

User = get_user_model()


class TimesheetServiceTests(TestCase):
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
        self.altro = User.objects.create_user(
            email="altro-test@example.com",
            password="Password-test-123",
        )
        self.cliente = Cliente.objects.create(
            ragione_sociale="Cliente Test",
            partita_iva="IT00000000031",
        )
        self.commessa = Commessa.objects.create(
            cliente=self.cliente,
            codice="TEST-001",
            descrizione="Test inserimento ore e spese",
            data_inizio=date(2026, 1, 1),
        )
        self.assegnazione = Assegnazione.objects.create(
            consulente=self.consulente,
            commessa=self.commessa,
            ore_previste=40,
            data_inizio=date(2026, 1, 1),
        )

    def test_consulente_non_puo_superare_otto_ore(self):
        inserisci_ore(
            attore=self.consulente,
            assegnazione_id=self.assegnazione.id,
            giorno=date(2026, 7, 20),
            tipo_attivita=TariffaAssegnazione.TipoAttivita.CONSULENZA,
            ore=6,
        )
        with self.assertRaises(ValidationError):
            inserisci_ore(
                attore=self.consulente,
                assegnazione_id=self.assegnazione.id,
                giorno=date(2026, 7, 20),
                tipo_attivita=TariffaAssegnazione.TipoAttivita.CONSULENZA,
                ore=3,
            )

    def test_admin_puo_superare_otto_ore_con_motivazione_e_riga_rimane_bloccata(self):
        esito = inserisci_ore(
            attore=self.admin,
            assegnazione_id=self.assegnazione.id,
            giorno=date(2026, 7, 21),
            tipo_attivita=TariffaAssegnazione.TipoAttivita.FORMAZIONE,
            ore=9,
            motivazione="Eccezione amministrativa motivata.",
        )
        self.assertTrue(esito.limite_giornaliero_superato)
        self.assertTrue(esito.riga.bloccata_per_consulente)

    def test_mese_chiuso_blocca_anche_admin(self):
        PeriodoMensile.objects.create(
            anno=2026,
            mese=7,
            stato=PeriodoMensile.Stato.CHIUSO,
            chiuso_da=self.admin,
        )
        with self.assertRaises(ValidationError):
            inserisci_spesa(
                attore=self.admin,
                assegnazione_id=self.assegnazione.id,
                giorno=date(2026, 7, 22),
                categoria="VIAGGIO",
                importo=Decimal("25.00"),
            )

    def test_consulente_non_puo_modificare_riga_admin(self):
        riga = inserisci_ore(
            attore=self.admin,
            assegnazione_id=self.assegnazione.id,
            giorno=date(2026, 7, 23),
            tipo_attivita=TariffaAssegnazione.TipoAttivita.CONSULENZA,
            ore=4,
        ).riga
        with self.assertRaises(PermissionDenied):
            modifica_ore(
                attore=self.consulente,
                riga_id=riga.id,
                versione=riga.versione,
                assegnazione_id=self.assegnazione.id,
                giorno=riga.data,
                tipo_attivita=riga.tipo_attivita,
                ore=5,
            )

    def test_optimistic_locking_blocca_versione_vecchia(self):
        riga = inserisci_ore(
            attore=self.consulente,
            assegnazione_id=self.assegnazione.id,
            giorno=date(2026, 7, 24),
            tipo_attivita=TariffaAssegnazione.TipoAttivita.CONSULENZA,
            ore=4,
        ).riga
        with self.assertRaises(ValidationError):
            modifica_ore(
                attore=self.consulente,
                riga_id=riga.id,
                versione=999,
                assegnazione_id=self.assegnazione.id,
                giorno=riga.data,
                tipo_attivita=riga.tipo_attivita,
                ore=5,
            )
