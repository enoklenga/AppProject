from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from apps.accounts.models import User
from apps.projects.models import (
    Assegnazione,
    Cliente,
    Commessa,
)
from apps.timesheets.models import RigaOre
from apps.projects.models import TariffaAssegnazione

from apps.planning.models import GiornoPianificato
from apps.planning.selectors import (
    planned_vs_actual,
)


class PlannedVsActualTests(TestCase):

    def setUp(self):
        self.today = timezone.localdate()

        self.user = User.objects.create_user(
            email="consulente@test.it",
            password="test12345",
            first_name="Mario",
            last_name="Rossi",
        )

        self.cliente = Cliente.objects.create(
            ragione_sociale="Cliente Test",
            partita_iva="12345678901",
        )

        self.commessa = Commessa.objects.create(
            cliente=self.cliente,
            codice="TEST-001",
            descrizione="Commessa test",
            ore_budget=100,
            data_inizio=self.today - timedelta(days=30),
        )

        self.assegnazione = Assegnazione.objects.create(
            consulente=self.user,
            commessa=self.commessa,
            ore_previste=100,
            ruolo_commessa=Assegnazione.Ruolo.CONSULENTE,
            stato=Assegnazione.Stato.ATTIVA,
            data_inizio=self.today - timedelta(days=30),
        )

        GiornoPianificato.objects.create(
            assegnazione=self.assegnazione,
            data=self.today,
            ore_pianificate=8,
            inserita_da=self.user,
        )

        RigaOre.objects.create(
            assegnazione=self.assegnazione,
            data=self.today,
            tipo_attivita=(
                TariffaAssegnazione
                .TipoAttivita
                .CONSULENZA
            ),
            ore=6,
            inserita_da=self.user,
        )

    def test_confronto_pianificato_consuntivato(self):
        risultato = planned_vs_actual(
            user=self.user,
            data_inizio=self.today,
            data_fine=self.today,
        )

        self.assertEqual(
            risultato["ore_pianificate"],
            8,
        )

        self.assertEqual(
            risultato["ore_consuntivate"],
            6,
        )

        self.assertEqual(
            risultato["scostamento"],
            -2,
        )

        self.assertEqual(
            risultato["percentuale_consuntivata"],
            75.0,
        )

        self.assertEqual(
            risultato["percentuale_scostamento"],
            -25.0,
        )

    def test_giornate_future_non_entrano_nel_confronto(self):
        domani = self.today + timedelta(days=1)

        GiornoPianificato.objects.create(
            assegnazione=self.assegnazione,
            data=domani,
            ore_pianificate=8,
            inserita_da=self.user,
        )

        risultato = planned_vs_actual(
            user=self.user,
            data_inizio=self.today,
            data_fine=domani,
        )

        self.assertEqual(
            risultato["ore_pianificate"],
            8,
        )

        self.assertEqual(
            risultato["ore_consuntivate"],
            6,
        )