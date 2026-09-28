from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from apps.accounts.models import User
from apps.planning.models import GiornoPianificato
from apps.planning.permissions import (
    can_edit_planning,
    can_view_planning,
)
from apps.projects.models import Assegnazione, Cliente, Commessa


class PlanningPermissionTests(TestCase):
    def setUp(self):
        self.today = timezone.localdate()
        self.tomorrow = self.today + timedelta(days=1)

        self.consulente = User.objects.create_user(
            email="consulente@example.com",
            password="TestPassword123!",
            first_name="Mario",
            last_name="Rossi",
            ruolo=User.Ruolo.CONSULENTE,
        )

        self.altro_consulente = User.objects.create_user(
            email="altro@example.com",
            password="TestPassword123!",
            first_name="Anna",
            last_name="Bianchi",
            ruolo=User.Ruolo.CONSULENTE,
        )

        self.pm = User.objects.create_user(
            email="pm@example.com",
            password="TestPassword123!",
            first_name="Paolo",
            last_name="Verdi",
            ruolo=User.Ruolo.CONSULENTE,
        )

        self.admin = User.objects.create_user(
            email="admin@example.com",
            password="TestPassword123!",
            first_name="Admin",
            last_name="LEF",
            ruolo=User.Ruolo.ADMIN,
        )

        self.cliente = Cliente.objects.create(
            ragione_sociale="Cliente Test",
            partita_iva="98765432101",
        )

        self.commessa = Commessa.objects.create(
            cliente=self.cliente,
            codice="PM-TEST",
            descrizione="Commessa per test permessi",
            ore_budget=100,
            data_inizio=self.today,
            data_fine_prevista=self.today + timedelta(days=90),
        )

        self.assegnazione_consulente = Assegnazione.objects.create(
            consulente=self.consulente,
            commessa=self.commessa,
            ore_previste=40,
            ruolo_commessa=Assegnazione.Ruolo.CONSULENTE,
            stato=Assegnazione.Stato.ATTIVA,
            data_inizio=self.today,
        )

        self.assegnazione_pm = Assegnazione.objects.create(
            consulente=self.pm,
            commessa=self.commessa,
            ore_previste=40,
            ruolo_commessa=Assegnazione.Ruolo.PROJECT_MANAGER,
            stato=Assegnazione.Stato.ATTIVA,
            data_inizio=self.today,
        )

        self.pianificazione = GiornoPianificato.objects.create(
            assegnazione=self.assegnazione_consulente,
            data=self.tomorrow,
            ore_pianificate=4,
            inserita_da=self.consulente,
            ultima_modifica_da=self.consulente,
        )

    def test_consulente_vede_la_propria_pianificazione(self):
        self.assertTrue(
            can_view_planning(
                self.consulente,
                self.pianificazione,
            )
        )

    def test_utente_fuori_team_non_vede_la_pianificazione(self):
        self.assertFalse(
            can_view_planning(
                self.altro_consulente,
                self.pianificazione,
            )
        )

    def test_pm_vede_pianificazione_della_propria_commessa(self):
        self.assertTrue(
            can_view_planning(
                self.pm,
                self.pianificazione,
            )
        )

    def test_pm_puo_modificare_pianificazione_del_team(self):
        self.assertTrue(
            can_edit_planning(
                self.pm,
                self.pianificazione,
            )
        )

    def test_admin_vede_tutto(self):
        self.assertTrue(
            can_view_planning(
                self.admin,
                self.pianificazione,
            )
        )

    def test_admin_puo_correggere_pianificazione(self):
        self.assertTrue(
            can_edit_planning(
                self.admin,
                self.pianificazione,
            )
        )

    def test_pm_resta_membro_se_il_ruolo_diventa_consulente(self):
        self.assegnazione_pm.ruolo_commessa = (
            Assegnazione.Ruolo.CONSULENTE
        )
        self.assegnazione_pm.save(
            update_fields=[
                "ruolo_commessa",
                "updated_at",
            ]
        )

        self.assertTrue(
            can_view_planning(
                self.pm,
                self.pianificazione,
            )
        )

    def test_membro_perde_visibilita_se_assegnazione_viene_conclusa(self):
        self.assegnazione_pm.stato = Assegnazione.Stato.CONCLUSA
        self.assegnazione_pm.save(
            update_fields=[
                "stato",
                "updated_at",
            ]
        )

        self.assertFalse(
            can_view_planning(
                self.pm,
                self.pianificazione,
            )
        )