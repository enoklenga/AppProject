from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from apps.accounts.models import User
from apps.planning.models import GiornoPianificato
from apps.planning.selectors import (
    planned_hours_for_assignment,
    remaining_plannable_hours,
    visible_planning_for_user,
    weekly_load,
)
from apps.projects.models import Assegnazione, Cliente, Commessa


class PlanningSelectorTests(TestCase):
    def setUp(self):
        self.today = timezone.localdate()

        self.consulente = User.objects.create_user(
            email="selector@example.com",
            password="TestPassword123!",
            first_name="Mario",
            last_name="Rossi",
            ruolo=User.Ruolo.CONSULENTE,
        )

        self.altro = User.objects.create_user(
            email="selector-altro@example.com",
            password="TestPassword123!",
            first_name="Anna",
            last_name="Bianchi",
            ruolo=User.Ruolo.CONSULENTE,
        )

        self.admin = User.objects.create_user(
            email="selector-admin@example.com",
            password="TestPassword123!",
            first_name="Admin",
            last_name="LEF",
            ruolo=User.Ruolo.ADMIN,
        )

        self.cliente = Cliente.objects.create(
            ragione_sociale="Cliente Selector",
            partita_iva="11122233344",
        )

        self.commessa = Commessa.objects.create(
            cliente=self.cliente,
            codice="SELECTOR-001",
            descrizione="Commessa selector",
            ore_budget=100,
            data_inizio=self.today,
            data_fine_prevista=self.today + timedelta(days=90),
        )

        self.assegnazione = Assegnazione.objects.create(
            consulente=self.consulente,
            commessa=self.commessa,
            ore_previste=20,
            stato=Assegnazione.Stato.ATTIVA,
            data_inizio=self.today,
        )

        self.pianificazione_1 = GiornoPianificato.objects.create(
            assegnazione=self.assegnazione,
            data=self.today,
            ore_pianificate=4,
            inserita_da=self.consulente,
            ultima_modifica_da=self.consulente,
        )

        self.pianificazione_2 = GiornoPianificato.objects.create(
            assegnazione=self.assegnazione,
            data=self.today + timedelta(days=1),
            ore_pianificate=6,
            inserita_da=self.consulente,
            ultima_modifica_da=self.consulente,
        )

    def test_totale_pianificato_assegnazione(self):
        self.assertEqual(
            planned_hours_for_assignment(
                self.assegnazione
            ),
            10,
        )

    def test_residuo_pianificabile(self):
        self.assertEqual(
            remaining_plannable_hours(
                self.assegnazione
            ),
            10,
        )

    def test_consulente_vede_solo_la_propria_pianificazione(self):
        queryset = visible_planning_for_user(
            self.consulente
        )

        self.assertEqual(
            queryset.count(),
            2,
        )

    def test_altro_consulente_non_vede_pianificazione(self):
        queryset = visible_planning_for_user(
            self.altro
        )

        self.assertEqual(
            queryset.count(),
            0,
        )

    def test_admin_vede_tutte_le_pianificazioni(self):
        queryset = visible_planning_for_user(
            self.admin
        )

        self.assertEqual(
            queryset.count(),
            2,
        )

    def test_carico_settimanale(self):
        risultato = weekly_load(
            user=self.consulente,
            consulente=self.consulente,
            giorno_settimana=self.today,
        )

        self.assertEqual(
            risultato["ore_pianificate"],
            10,
        )

        self.assertEqual(
            risultato["soglia_standard"],
            40,
        )

        self.assertFalse(
            risultato["sovraccarico"]
        )