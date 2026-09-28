from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from apps.accounts.models import User
from apps.notifications.models import Notification
from apps.notifications.selectors import (
    notification_for_user,
    notification_summary,
    notifications_for_user,
    recent_notifications_for_user,
    tasks_due_soon_for_notifications,
    tasks_overdue_for_notifications,
    unread_notification_count,
    unread_notifications_for_user,
)
from apps.phases.models import FaseCommessa
from apps.projects.models import (
    Assegnazione,
    Cliente,
    Commessa,
)
from apps.tasks.models import Task

class NotificationSelectorsTests(TestCase):

    def setUp(self):
        self.oggi = timezone.localdate()

        self.utente = User.objects.create_user(
            email="utente@test.it",
            password="test12345",
            first_name="Anna",
            last_name="Rossi",
        )

        self.altro_utente = User.objects.create_user(
            email="altro@test.it",
            password="test12345",
            first_name="Mario",
            last_name="Verdi",
        )

        self.admin = User.objects.create_user(
            email="admin@test.it",
            password="test12345",
            first_name="Admin",
            last_name="LEF",
            ruolo=User.Ruolo.ADMIN,
        )

        self.cliente = Cliente.objects.create(
            ragione_sociale="Cliente Selector",
            partita_iva="98765432109",
        )

        self.commessa = Commessa.objects.create(
            cliente=self.cliente,
            codice="SEL-001",
            descrizione="Commessa selector",
            data_inizio=(
                self.oggi
                - timedelta(days=20)
            ),
        )

        self.fase = FaseCommessa.objects.get(
            commessa=self.commessa,
            sistema=True,
        )

        self.assegnazione = Assegnazione.objects.create(
            consulente=self.utente,
            commessa=self.commessa,
            fase=self.fase,
            ore_previste=80,
            data_inizio=self.commessa.data_inizio,
        )

        self.task = Task.objects.create(
            commessa=self.commessa,
            fase=self.fase,
            titolo="Task selector",
            assegnato_a=self.utente,
            creato_da=self.admin,
            stato=Task.Stato.DA_FARE,
            data_scadenza=(
                self.oggi
                + timedelta(days=5)
            ),
        )

        self.notification_1 = (
            Notification.objects.create(
                destinatario=self.utente,
                attore=self.admin,
                task=self.task,
                tipo=(
                    Notification
                    .Tipo
                    .TASK_ASSIGNED
                ),
                titolo="Nuova attività",
            )
        )

        self.notification_2 = (
            Notification.objects.create(
                destinatario=self.utente,
                task=self.task,
                tipo=(
                    Notification
                    .Tipo
                    .TASK_DUE_SOON
                ),
                titolo="In scadenza",
                letta_il=timezone.now(),
            )
        )

        self.notification_other = (
            Notification.objects.create(
                destinatario=self.altro_utente,
                task=self.task,
                tipo=(
                    Notification
                    .Tipo
                    .TASK_ASSIGNED
                ),
                titolo="Notifica altro utente",
            )
        )

    # =====================================================
    # QUERY UTENTE
    # =====================================================

    def test_notifications_for_user_solo_proprie(self):
        queryset = notifications_for_user(
            user=self.utente
        )

        self.assertEqual(
            queryset.count(),
            2,
        )

        self.assertNotIn(
            self.notification_other,
            queryset,
        )

    def test_unread_notifications(self):
        queryset = (
            unread_notifications_for_user(
                user=self.utente
            )
        )

        self.assertEqual(
            queryset.count(),
            1,
        )

        self.assertEqual(
            queryset.first(),
            self.notification_1,
        )

    def test_unread_notification_count(self):
        count = unread_notification_count(
            user=self.utente
        )

        self.assertEqual(
            count,
            1,
        )

    def test_recent_notifications_limit(self):
        queryset = (
            recent_notifications_for_user(
                user=self.utente,
                limit=1,
            )
        )

        self.assertEqual(
            len(queryset),
            1,
        )

    def test_notification_for_user(self):
        queryset = notification_for_user(
            user=self.utente,
            pk=self.notification_1.pk,
        )

        self.assertTrue(
            queryset.exists()
        )

    def test_notification_for_user_non_restituisce_altrui(self):
        queryset = notification_for_user(
            user=self.utente,
            pk=self.notification_other.pk,
        )

        self.assertFalse(
            queryset.exists()
        )

    # =====================================================
    # SUMMARY
    # =====================================================

    def test_notification_summary(self):
        summary = notification_summary(
            user=self.utente
        )

        self.assertEqual(
            summary["totale"],
            2,
        )

        self.assertEqual(
            summary["non_lette"],
            1,
        )

        self.assertEqual(
            summary["task_assegnati"],
            1,
        )

        self.assertEqual(
            summary["in_scadenza"],
            1,
        )

    # =====================================================
    # TASK IN SCADENZA
    # =====================================================

    def test_task_in_scadenza_selezionato(self):
        queryset = (
            tasks_due_soon_for_notifications(
                giorni=7,
                oggi=self.oggi,
            )
        )

        self.assertIn(
            self.task,
            queryset,
        )

    def test_task_fuori_finestra_non_selezionato(self):
        task_lontano = Task.objects.create(
            commessa=self.commessa,
            fase=self.fase,
            titolo="Task lontano",
            assegnato_a=self.utente,
            creato_da=self.admin,
            stato=Task.Stato.DA_FARE,
            data_scadenza=(
                self.oggi
                + timedelta(days=20)
            ),
        )

        queryset = (
            tasks_due_soon_for_notifications(
                giorni=7,
                oggi=self.oggi,
            )
        )

        self.assertNotIn(
            task_lontano,
            queryset,
        )

    def test_task_completato_non_selezionato_in_scadenza(self):
        self.task.stato = (
            Task.Stato.COMPLETATA
        )

        self.task.save(
            update_fields=[
                "stato"
            ]
        )

        queryset = (
            tasks_due_soon_for_notifications(
                giorni=7,
                oggi=self.oggi,
            )
        )

        self.assertNotIn(
            self.task,
            queryset,
        )

    # =====================================================
    # TASK SCADUTI
    # =====================================================

    def test_task_scaduto_selezionato(self):
        self.task.data_scadenza = (
            self.oggi
            - timedelta(days=1)
        )

        self.task.save(
            update_fields=[
                "data_scadenza"
            ]
        )

        queryset = (
            tasks_overdue_for_notifications(
                oggi=self.oggi
            )
        )

        self.assertIn(
            self.task,
            queryset,
        )

    def test_task_non_ancora_scaduto_non_selezionato(self):
        queryset = (
            tasks_overdue_for_notifications(
                oggi=self.oggi
            )
        )

        self.assertNotIn(
            self.task,
            queryset,
        )

    def test_task_completato_non_selezionato_tra_scaduti(self):
        self.task.data_scadenza = (
            self.oggi
            - timedelta(days=2)
        )

        self.task.stato = (
            Task.Stato.COMPLETATA
        )

        self.task.save(
            update_fields=[
                "data_scadenza",
                "stato",
            ]
        )

        queryset = (
            tasks_overdue_for_notifications(
                oggi=self.oggi
            )
        )

        self.assertNotIn(
            self.task,
            queryset,
        )

    def test_task_in_scadenza_non_selezionato_se_assegnazione_conclusa(self):
        self.assegnazione.stato = Assegnazione.Stato.CONCLUSA
        self.assegnazione.save(update_fields=["stato"])

        queryset = tasks_due_soon_for_notifications(
            giorni=7,
            oggi=self.oggi,
        )

        self.assertNotIn(self.task, queryset)

    def test_task_scaduto_non_selezionato_se_assegnazione_conclusa(self):
        self.task.data_scadenza = self.oggi - timedelta(days=1)
        self.task.save(update_fields=["data_scadenza"])

        self.assegnazione.stato = Assegnazione.Stato.CONCLUSA
        self.assegnazione.save(update_fields=["stato"])

        queryset = tasks_overdue_for_notifications(
            oggi=self.oggi,
        )

        self.assertNotIn(self.task, queryset)

    def test_task_admin_senza_assegnazione_resta_notificabile(self):
        task_admin = Task.objects.create(
            commessa=self.commessa,
            fase=self.fase,
            titolo="Task Admin",
            assegnato_a=self.admin,
            creato_da=self.admin,
            stato=Task.Stato.DA_FARE,
            data_scadenza=self.oggi + timedelta(days=2),
        )

        queryset = tasks_due_soon_for_notifications(
            giorni=7,
            oggi=self.oggi,
        )

        self.assertIn(task_admin, queryset)

