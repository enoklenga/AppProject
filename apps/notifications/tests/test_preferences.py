"""Le preferenze personali disattivano davvero le notifiche.

Questo file conteneva una funzione di test isolata (fuori da una classe
TestCase, con nomi non importati) che il test runner non eseguiva mai.
È stata trasformata in un test reale.
"""
from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from apps.accounts.models import User
from apps.notifications.models import Notification, NotificationPreference
from apps.notifications.services import notify_task_commented
from apps.phases.models import FaseCommessa
from apps.projects.models import Assegnazione, Cliente, Commessa
from apps.tasks.models import Task, TaskComment


class NotificationPreferenceTests(TestCase):
    def setUp(self):
        oggi = timezone.localdate()
        self.pm = User.objects.create_user(email="pm-pref@test.it", password="test12345")
        self.user = User.objects.create_user(email="cons-pref@test.it", password="test12345")
        cliente = Cliente.objects.create(ragione_sociale="Cliente Pref", partita_iva="12345678902")
        commessa = Commessa.objects.create(
            cliente=cliente,
            codice="PREF-001",
            descrizione="Commessa preferenze",
            ore_budget=100,
            data_inizio=oggi - timedelta(days=10),
        )
        fase = FaseCommessa.objects.get(commessa=commessa, sistema=True)
        for utente, ruolo in (
            (self.pm, Assegnazione.Ruolo.PROJECT_MANAGER),
            (self.user, Assegnazione.Ruolo.CONSULENTE),
        ):
            Assegnazione.objects.create(
                consulente=utente,
                commessa=commessa,
                fase=fase,
                ore_previste=40,
                ruolo_commessa=ruolo,
                stato=Assegnazione.Stato.ATTIVA,
                data_inizio=oggi - timedelta(days=10),
            )
        task = Task.objects.create(
            commessa=commessa,
            fase=fase,
            titolo="Task preferenze",
            assegnato_a=self.user,
            creato_da=self.pm,
        )
        self.comment = TaskComment.objects.create(task=task, autore=self.pm, testo="Commento")

    def _preferences(self):
        preferences, _ = NotificationPreference.objects.get_or_create(user=self.user)
        self.user.refresh_from_db()
        return preferences

    def test_comment_notification_enabled_by_default(self):
        self._preferences()
        notify_task_commented(comment=self.comment)
        self.assertTrue(
            Notification.objects.filter(
                destinatario=self.user,
                tipo=Notification.Tipo.TASK_COMMENTED,
            ).exists()
        )

    def test_comment_notification_disabled(self):
        preferences = self._preferences()
        preferences.task_commented = False
        preferences.save()
        self.user.refresh_from_db()

        notify_task_commented(comment=self.comment)

        self.assertFalse(
            Notification.objects.filter(
                destinatario=self.user,
                tipo=Notification.Tipo.TASK_COMMENTED,
            ).exists()
        )
