from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from apps.accounts.models import User
from apps.projects.models import (
    Assegnazione,
    Cliente,
    Commessa,
)
from apps.tasks.models import Task
from apps.tasks.permissions import (
    can_comment_task,
    can_create_task,
    can_delete_task,
    can_edit_task,
    can_update_task_status,
    can_view_task,
)
from apps.phases.models import FaseCommessa


class TaskPermissionsTests(TestCase):

    def setUp(self):
        oggi = timezone.localdate()

        self.admin = User.objects.create_user(
            email="admin@test.it",
            password="test12345",
            first_name="Admin",
            last_name="LEF",
            ruolo=User.Ruolo.ADMIN,
        )

        self.pm = User.objects.create_user(
            email="pm@test.it",
            password="test12345",
            first_name="Mario",
            last_name="PM",
        )

        self.consulente = User.objects.create_user(
            email="consulente@test.it",
            password="test12345",
            first_name="Anna",
            last_name="Consulente",
        )

        self.altro_consulente = User.objects.create_user(
            email="altro@test.it",
            password="test12345",
            first_name="Luca",
            last_name="Altro",
        )

        self.cliente = Cliente.objects.create(
            ragione_sociale="Cliente Test",
            partita_iva="12345678901",
        )

        self.commessa_pm = Commessa.objects.create(
            cliente=self.cliente,
            codice="COMM-PM",
            descrizione="Commessa gestita dal PM",
            ore_budget=200,
            data_inizio=oggi - timedelta(days=30),
        )

        self.commessa_altra = Commessa.objects.create(
            cliente=self.cliente,
            codice="COMM-ALTRA",
            descrizione="Altra commessa",
            ore_budget=200,
            data_inizio=oggi - timedelta(days=30),
        )

        # Le fasi di sistema vengono create automaticamente
        # insieme alle commesse.
        self.fase_pm = FaseCommessa.objects.get(
            commessa=self.commessa_pm,
            sistema=True,
        )

        self.fase_altra = FaseCommessa.objects.get(
            commessa=self.commessa_altra,
            sistema=True,
        )

        self.assegnazione_pm = Assegnazione.objects.create(
            consulente=self.pm,
            commessa=self.commessa_pm,
            fase=self.fase_pm,
            ore_previste=100,
            ruolo_commessa=Assegnazione.Ruolo.PROJECT_MANAGER,
            stato=Assegnazione.Stato.ATTIVA,
            data_inizio=oggi - timedelta(days=30),
        )

        self.assegnazione_consulente = Assegnazione.objects.create(
            consulente=self.consulente,
            commessa=self.commessa_pm,
            fase=self.fase_pm,
            ore_previste=100,
            ruolo_commessa=Assegnazione.Ruolo.CONSULENTE,
            stato=Assegnazione.Stato.ATTIVA,
            data_inizio=oggi - timedelta(days=30),
        )

        self.assegnazione_altro = Assegnazione.objects.create(
            consulente=self.altro_consulente,
            commessa=self.commessa_altra,
            fase=self.fase_altra,
            ore_previste=100,
            ruolo_commessa=Assegnazione.Ruolo.CONSULENTE,
            stato=Assegnazione.Stato.ATTIVA,
            data_inizio=oggi - timedelta(days=30),
        )

        self.task = Task.objects.create(
            commessa=self.commessa_pm,
            fase=self.fase_pm,
            titolo="Preparare analisi",
            descrizione="Task di prova",
            assegnato_a=self.consulente,
            creato_da=self.pm,
        )

    def test_admin_puo_creare_task(self):
        self.assertTrue(
            can_create_task(
                self.admin,
                self.commessa_pm,
            )
        )

    def test_pm_puo_creare_task_sulla_propria_commessa(self):
        self.assertTrue(
            can_create_task(
                self.pm,
                self.commessa_pm,
            )
        )

    def test_pm_non_puo_creare_su_altra_commessa(self):
        self.assertFalse(
            can_create_task(
                self.pm,
                self.commessa_altra,
            )
        )

    def test_consulente_puo_creare_task_nel_teamwork(self):
        self.assertTrue(
            can_create_task(
                self.consulente,
                self.commessa_pm,
            )
        )

    def test_assegnatario_puo_vedere_task(self):
        self.assertTrue(
            can_view_task(
                self.consulente,
                self.task,
            )
        )

    def test_altro_consulente_non_puo_vedere_task(self):
        self.assertFalse(
            can_view_task(
                self.altro_consulente,
                self.task,
            )
        )

    def test_pm_puo_vedere_task_della_propria_commessa(self):
        self.assertTrue(
            can_view_task(
                self.pm,
                self.task,
            )
        )

    def test_admin_puo_vedere_task(self):
        self.assertTrue(
            can_view_task(
                self.admin,
                self.task,
            )
        )

    def test_consulente_puo_modificare_task_del_team(self):
        self.assertTrue(
            can_edit_task(
                self.consulente,
                self.task,
            )
        )

    def test_pm_puo_modificare_task(self):
        self.assertTrue(
            can_edit_task(
                self.pm,
                self.task,
            )
        )

    def test_assegnatario_puo_modificare_stato(self):
        self.assertTrue(
            can_update_task_status(
                self.consulente,
                self.task,
            )
        )

    def test_utente_fuori_team_non_puo_modificare_stato(self):
        self.assertFalse(
            can_update_task_status(
                self.altro_consulente,
                self.task,
            )
        )

    def test_assegnatario_puo_commentare(self):
        self.assertTrue(
            can_comment_task(
                self.consulente,
                self.task,
            )
        )

    def test_pm_puo_commentare(self):
        self.assertTrue(
            can_comment_task(
                self.pm,
                self.task,
            )
        )

    def test_utente_fuori_team_non_puo_commentare(self):
        self.assertFalse(
            can_comment_task(
                self.altro_consulente,
                self.task,
            )
        )

    def test_pm_puo_eliminare_task_della_propria_commessa(self):
        self.assertTrue(
            can_delete_task(
                self.pm,
                self.task,
            )
        )

    def test_consulente_puo_eliminare_task_del_team(self):
        self.assertTrue(
            can_delete_task(
                self.consulente,
                self.task,
            )
        )

    def test_commessa_chiusa_blocca_creazione_pm(self):
        self.commessa_pm.stato = Commessa.Stato.CHIUSA
        self.commessa_pm.save(
            update_fields=["stato"]
        )

        self.assertFalse(
            can_create_task(
                self.pm,
                self.commessa_pm,
            )
        )