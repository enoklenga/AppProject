from datetime import timedelta
from io import StringIO

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from apps.accounts.models import User
from apps.notifications.models import Notification
from apps.phases.models import FaseCommessa
from apps.projects.models import (
    Assegnazione,
    Cliente,
    Commessa,
)
from apps.tasks.models import Task

class GenerateTaskNotificationsCommandTests(
    TestCase
):

    def setUp(self):

        self.oggi = (
            timezone.localdate()
        )

        # =================================================
        # UTENTI
        # =================================================

        self.admin = (
            User.objects.create_user(
                email="admin-command@test.it",
                password="test12345",
                first_name="Admin",
                last_name="LEF",
                ruolo=User.Ruolo.ADMIN,
            )
        )

        self.consulente = (
            User.objects.create_user(
                email="consulente-command@test.it",
                password="test12345",
                first_name="Anna",
                last_name="Rossi",
            )
        )

        # =================================================
        # CLIENTE / COMMESSA
        # =================================================

        self.cliente = (
            Cliente.objects.create(
                ragione_sociale=(
                    "Cliente Command"
                ),
                partita_iva=(
                    "12345678901"
                ),
            )
        )

        self.commessa = Commessa.objects.create(
            cliente=self.cliente,
            codice="CMD-001",
            descrizione="Test comando notifiche",
            ore_budget=100,
            data_inizio=self.oggi - timedelta(days=30),
        )

        # La fase di sistema "Generale" viene creata automaticamente
        # insieme alla commessa.
        self.fase = FaseCommessa.objects.get(
            commessa=self.commessa,
            sistema=True,
        )

        self.assegnazione = Assegnazione.objects.create(
            consulente=self.consulente,
            commessa=self.commessa,
            fase=self.fase,
            ore_previste=80,
            data_inizio=self.commessa.data_inizio,
        )


        # =================================================
        # TASK IN SCADENZA
        # =================================================

        self.task_due_soon = (
            Task.objects.create(
                commessa=self.commessa,
                fase=self.fase,
                titolo="Task in scadenza",
                descrizione="",
                assegnato_a=(
                    self.consulente
                ),
                creato_da=self.admin,
                stato=(
                    Task.Stato.DA_FARE
                ),
                priorita=(
                    Task.Priorita.NORMALE
                ),
                data_inizio=(
                    self.oggi
                    - timedelta(days=10)
                ),
                data_scadenza=(
                    self.oggi
                    + timedelta(days=3)
                ),
            )
        )

        # =================================================
        # TASK SCADUTO
        # =================================================

        self.task_overdue = (
            Task.objects.create(
                commessa=self.commessa,
                fase=self.fase,
                titolo="Task scaduto",
                descrizione="",
                assegnato_a=(
                    self.consulente
                ),
                creato_da=self.admin,
                stato=(
                    Task.Stato.IN_CORSO
                ),
                priorita=(
                    Task.Priorita.ALTA
                ),
                data_inizio=(
                    self.oggi
                    - timedelta(days=10)
                ),
                data_scadenza=(
                    self.oggi
                    - timedelta(days=1)
                ),
            )
        )

        # =================================================
        # TASK COMPLETATO
        # Non deve generare notifiche temporali
        # =================================================

        self.task_completed = (
            Task.objects.create(
                commessa=self.commessa,
                fase=self.fase,
                titolo="Task completato",
                descrizione="",
                assegnato_a=(
                    self.consulente
                ),
                creato_da=self.admin,
                stato=(
                    Task.Stato.COMPLETATA
                ),
                priorita=(
                    Task.Priorita.NORMALE
                ),
                data_inizio=(
                    self.oggi
                    - timedelta(days=10)
                ),
                data_scadenza=(
                    self.oggi
                    + timedelta(days=2)
                ),
                completato_il=(
                    timezone.now()
                ),
            )
        )

    # =====================================================
    # GENERAZIONE
    # =====================================================

    def test_comando_genera_notifiche_temporali(
        self
    ):

        output = StringIO()

        call_command(
            "generate_task_notifications",
            giorni=7,
            data=self.oggi.isoformat(),
            stdout=output,
        )

        self.assertTrue(
            Notification.objects.filter(
                task=self.task_due_soon,
                destinatario=(
                    self.consulente
                ),
                tipo=(
                    Notification
                    .Tipo
                    .TASK_DUE_SOON
                ),
            ).exists()
        )

        self.assertTrue(
            Notification.objects.filter(
                task=self.task_overdue,
                destinatario=(
                    self.consulente
                ),
                tipo=(
                    Notification
                    .Tipo
                    .TASK_OVERDUE
                ),
            ).exists()
        )

        self.assertFalse(
            Notification.objects.filter(
                task=self.task_completed,
            ).exists()
        )

    # =====================================================
    # IDEMPOTENZA
    # =====================================================

    def test_comando_non_duplica_notifiche(
        self
    ):

        call_command(
            "generate_task_notifications",
            giorni=7,
            data=self.oggi.isoformat(),
            stdout=StringIO(),
        )

        count_prima = (
            Notification.objects.count()
        )

        call_command(
            "generate_task_notifications",
            giorni=7,
            data=self.oggi.isoformat(),
            stdout=StringIO(),
        )

        count_dopo = (
            Notification.objects.count()
        )

        self.assertEqual(
            count_prima,
            count_dopo,
        )

        self.assertEqual(
            count_dopo,
            2,
        )

    # =====================================================
    # FINESTRA
    # =====================================================

    def test_comando_rispetta_finestra_giorni(
        self
    ):

        call_command(
            "generate_task_notifications",
            giorni=2,
            data=self.oggi.isoformat(),
            stdout=StringIO(),
        )

        self.assertFalse(
            Notification.objects.filter(
                task=self.task_due_soon,
                tipo=(
                    Notification
                    .Tipo
                    .TASK_DUE_SOON
                ),
            ).exists()
        )

        # Lo scaduto deve invece essere
        # comunque rilevato.
        self.assertTrue(
            Notification.objects.filter(
                task=self.task_overdue,
                tipo=(
                    Notification
                    .Tipo
                    .TASK_OVERDUE
                ),
            ).exists()
        )

    # =====================================================
    # DRY RUN
    # =====================================================

    def test_dry_run_non_crea_notifiche(
        self
    ):

        output = StringIO()

        call_command(
            "generate_task_notifications",
            giorni=7,
            data=self.oggi.isoformat(),
            dry_run=True,
            stdout=output,
        )

        self.assertEqual(
            Notification.objects.count(),
            0,
        )

        self.assertIn(
            "DRY RUN",
            output.getvalue(),
        )