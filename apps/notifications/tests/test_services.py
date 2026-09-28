from datetime import timedelta

from django.core.exceptions import PermissionDenied
from django.test import TestCase
from django.utils import timezone

from apps.accounts.models import User
from apps.documents.models import DocumentoCommessa
from apps.notifications.models import Notification
from apps.notifications.services import (
    generate_due_soon_notifications,
    generate_overdue_notifications,
    mark_all_notifications_read,
    mark_notification_read,
    mark_notification_unread,
    notify_documento_caricato,
    notify_documento_eliminato,
    notify_task_assigned,
    notify_task_commented,
    notify_task_due_soon,
    notify_task_overdue,
)
from apps.phases.models import FaseCommessa
from apps.projects.models import (
    Assegnazione,
    Cliente,
    Commessa,
)
from apps.tasks.models import (
    Task,
    TaskComment,
)
from apps.tasks.services import (
    add_task_comment,
    create_task,
    update_task,
)


class NotificationServicesTests(TestCase):

    def setUp(self):
        self.oggi = timezone.localdate()

        # =================================================
        # UTENTI
        # =================================================

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

        # Questo utente NON viene assegnato alla fase.
        # Serve per verificare che un utente esterno
        # non riceva notifiche relative ai commenti.
        self.consulente_non_coinvolto = User.objects.create_user(
            email="noncoinvolto@test.it",
            password="test12345",
            first_name="Paolo",
            last_name="Esterno",
        )

        # =================================================
        # CLIENTE / COMMESSA
        # =================================================

        self.cliente = Cliente.objects.create(
            ragione_sociale="Cliente Test",
            partita_iva="12345678901",
        )

        self.commessa = Commessa.objects.create(
            cliente=self.cliente,
            codice="COMM-001",
            descrizione="Commessa test notifiche",
            ore_budget=200,
            data_inizio=(
                self.oggi
                - timedelta(days=30)
            ),
        )

        # La fase tecnica di sistema viene creata
        # automaticamente insieme alla commessa.
        self.fase = FaseCommessa.objects.get(
            commessa=self.commessa,
            sistema=True,
        )

        # =================================================
        # ASSEGNAZIONI
        # =================================================

        self.assegnazione_pm = (
            Assegnazione.objects.create(
                consulente=self.pm,
                commessa=self.commessa,
                fase=self.fase,
                ore_previste=100,
                ruolo_commessa=(
                    Assegnazione
                    .Ruolo
                    .PROJECT_MANAGER
                ),
                stato=(
                    Assegnazione
                    .Stato
                    .ATTIVA
                ),
                data_inizio=(
                    self.oggi
                    - timedelta(days=30)
                ),
            )
        )

        self.assegnazione_consulente = (
            Assegnazione.objects.create(
                consulente=self.consulente,
                commessa=self.commessa,
                fase=self.fase,
                ore_previste=100,
                ruolo_commessa=(
                    Assegnazione
                    .Ruolo
                    .CONSULENTE
                ),
                stato=(
                    Assegnazione
                    .Stato
                    .ATTIVA
                ),
                data_inizio=(
                    self.oggi
                    - timedelta(days=30)
                ),
            )
        )

        self.assegnazione_altro = (
            Assegnazione.objects.create(
                consulente=self.altro_consulente,
                commessa=self.commessa,
                fase=self.fase,
                ore_previste=80,
                ruolo_commessa=(
                    Assegnazione
                    .Ruolo
                    .CONSULENTE
                ),
                stato=(
                    Assegnazione
                    .Stato
                    .ATTIVA
                ),
                data_inizio=(
                    self.oggi
                    - timedelta(days=30)
                ),
            )
        )

        # =================================================
        # TASK
        # =================================================

        self.task = Task.objects.create(
            commessa=self.commessa,
            fase=self.fase,
            titolo="Preparare report",
            descrizione="Task di prova",
            assegnato_a=self.consulente,
            creato_da=self.pm,
            stato=Task.Stato.DA_FARE,
            priorita=Task.Priorita.NORMALE,
            data_inizio=(
                self.oggi
                - timedelta(days=10)
            ),
            data_scadenza=(
                self.oggi
                + timedelta(days=5)
            ),
        )

    # =====================================================
    # TASK ASSEGNATO
    # =====================================================

    def test_notifica_nuovo_task_assegnato(self):
        notification = notify_task_assigned(
            task=self.task,
            actor=self.pm,
        )

        self.assertIsNotNone(
            notification
        )

        self.assertEqual(
            Notification.objects.count(),
            1,
        )

        self.assertEqual(
            notification.destinatario,
            self.consulente,
        )

        self.assertEqual(
            notification.attore,
            self.pm,
        )

        self.assertEqual(
            notification.task,
            self.task,
        )

        self.assertEqual(
            notification.tipo,
            Notification.Tipo.TASK_ASSIGNED,
        )

        self.assertIsNone(
            notification.letta_il
        )

    def test_assegnazione_a_se_stesso_non_genera_notifica(self):
        task_pm = Task.objects.create(
            commessa=self.commessa,
            fase=self.fase,
            titolo="Task PM",
            assegnato_a=self.pm,
            creato_da=self.pm,
        )

        notification = notify_task_assigned(
            task=task_pm,
            actor=self.pm,
        )

        self.assertIsNone(
            notification
        )

        self.assertEqual(
            Notification.objects.count(),
            0,
        )

    def test_utente_disattivato_non_riceve_notifica(self):
        self.consulente.is_active = False

        self.consulente.save(
            update_fields=[
                "is_active"
            ]
        )

        notification = notify_task_assigned(
            task=self.task,
            actor=self.pm,
        )

        self.assertIsNone(
            notification
        )

        self.assertEqual(
            Notification.objects.count(),
            0,
        )

    # =====================================================
    # COMMENTI
    # =====================================================

    def test_commento_notifica_assegnatario(self):
        commento = TaskComment.objects.create(
            task=self.task,
            autore=self.pm,
            testo="Procedere con il report.",
        )

        notifications = notify_task_commented(
            comment=commento,
        )

        destinatari = {
            notification.destinatario_id
            for notification in notifications
        }

        self.assertIn(
            self.consulente.pk,
            destinatari,
        )

    def test_autore_commento_non_riceve_notifica(self):
        commento = TaskComment.objects.create(
            task=self.task,
            autore=self.pm,
            testo="Aggiornamento PM",
        )

        notify_task_commented(
            comment=commento,
        )

        self.assertFalse(
            Notification.objects.filter(
                destinatario=self.pm,
                tipo=(
                    Notification
                    .Tipo
                    .TASK_COMMENTED
                ),
            ).exists()
        )

    def test_commento_del_consulente_notifica_pm(self):
        commento = TaskComment.objects.create(
            task=self.task,
            autore=self.consulente,
            testo="Attività iniziata.",
        )

        notify_task_commented(
            comment=commento,
        )

        self.assertTrue(
            Notification.objects.filter(
                destinatario=self.pm,
                tipo=(
                    Notification
                    .Tipo
                    .TASK_COMMENTED
                ),
            ).exists()
        )

    def test_commento_non_notifica_consulente_non_coinvolto(self):
        commento = TaskComment.objects.create(
            task=self.task,
            autore=self.pm,
            testo="Aggiornamento.",
        )

        notify_task_commented(
            comment=commento,
        )

        self.assertFalse(
            Notification.objects.filter(
                destinatario=(
                    self.consulente_non_coinvolto
                ),
                tipo=(
                    Notification
                    .Tipo
                    .TASK_COMMENTED
                ),
            ).exists()
        )

    def test_stesso_commento_non_genera_duplicati(self):
        commento = TaskComment.objects.create(
            task=self.task,
            autore=self.pm,
            testo="Commento test",
        )

        notify_task_commented(
            comment=commento,
        )

        numero_prima = (
            Notification.objects.count()
        )

        notify_task_commented(
            comment=commento,
        )

        numero_dopo = (
            Notification.objects.count()
        )

        self.assertEqual(
            numero_prima,
            numero_dopo,
        )

    # =====================================================
    # IN SCADENZA
    # =====================================================

    def test_notifica_task_in_scadenza(self):
        notification = notify_task_due_soon(
            task=self.task,
        )

        self.assertIsNotNone(
            notification
        )

        self.assertEqual(
            notification.destinatario,
            self.consulente,
        )

        self.assertEqual(
            notification.tipo,
            Notification.Tipo.TASK_DUE_SOON,
        )

        self.assertEqual(
            notification.data_riferimento,
            self.task.data_scadenza,
        )

    def test_task_completato_non_genera_notifica_scadenza(self):
        self.task.stato = (
            Task.Stato.COMPLETATA
        )

        self.task.save(
            update_fields=[
                "stato"
            ]
        )

        notification = notify_task_due_soon(
            task=self.task,
        )

        self.assertIsNone(
            notification
        )

    def test_notifica_scadenza_non_si_duplica(self):
        notify_task_due_soon(
            task=self.task,
        )

        notify_task_due_soon(
            task=self.task,
        )

        self.assertEqual(
            Notification.objects.filter(
                tipo=(
                    Notification
                    .Tipo
                    .TASK_DUE_SOON
                )
            ).count(),
            1,
        )

    # =====================================================
    # SCADUTO
    # =====================================================

    def test_notifica_task_scaduto(self):
        self.task.data_scadenza = (
            self.oggi
            - timedelta(days=1)
        )

        self.task.save(
            update_fields=[
                "data_scadenza"
            ]
        )

        notification = notify_task_overdue(
            task=self.task,
        )

        self.assertIsNotNone(
            notification
        )

        self.assertEqual(
            notification.tipo,
            Notification.Tipo.TASK_OVERDUE,
        )

        self.assertEqual(
            notification.destinatario,
            self.consulente,
        )

    def test_notifica_scaduta_non_si_duplica(self):
        self.task.data_scadenza = (
            self.oggi
            - timedelta(days=2)
        )

        self.task.save(
            update_fields=[
                "data_scadenza"
            ]
        )

        notify_task_overdue(
            task=self.task,
        )

        notify_task_overdue(
            task=self.task,
        )

        self.assertEqual(
            Notification.objects.filter(
                tipo=(
                    Notification
                    .Tipo
                    .TASK_OVERDUE
                )
            ).count(),
            1,
        )

    # =====================================================
    # LETTA / NON LETTA
    # =====================================================

    def test_segna_notifica_come_letta(self):
        notification = notify_task_assigned(
            task=self.task,
            actor=self.pm,
        )

        notification = (
            mark_notification_read(
                user=self.consulente,
                notification=notification,
            )
        )

        self.assertIsNotNone(
            notification.letta_il
        )

    def test_segna_notifica_come_non_letta(self):
        notification = notify_task_assigned(
            task=self.task,
            actor=self.pm,
        )

        notification = (
            mark_notification_read(
                user=self.consulente,
                notification=notification,
            )
        )

        self.assertIsNotNone(
            notification.letta_il
        )

        notification = (
            mark_notification_unread(
                user=self.consulente,
                notification=notification,
            )
        )

        self.assertIsNone(
            notification.letta_il
        )

    def test_utente_non_puo_leggere_notifica_altrui(self):
        notification = notify_task_assigned(
            task=self.task,
            actor=self.pm,
        )

        with self.assertRaises(
            PermissionDenied
        ):
            mark_notification_read(
                user=self.altro_consulente,
                notification=notification,
            )

    def test_segna_tutte_come_lette(self):
        notify_task_assigned(
            task=self.task,
            actor=self.pm,
        )

        commento = TaskComment.objects.create(
            task=self.task,
            autore=self.pm,
            testo="Nuovo commento",
        )

        notify_task_commented(
            comment=commento,
        )

        aggiornate = (
            mark_all_notifications_read(
                user=self.consulente,
            )
        )

        self.assertGreaterEqual(
            aggiornate,
            1,
        )

        self.assertFalse(
            Notification.objects.filter(
                destinatario=self.consulente,
                letta_il__isnull=True,
            ).exists()
        )

    # =====================================================
    # GENERAZIONE BATCH
    # =====================================================

    def test_generazione_batch_scadenze(self):
        notifications = (
            generate_due_soon_notifications(
                tasks=[
                    self.task
                ]
            )
        )

        self.assertEqual(
            len(notifications),
            1,
        )

        self.assertEqual(
            Notification.objects.count(),
            1,
        )

    def test_generazione_batch_scaduti(self):
        self.task.data_scadenza = (
            self.oggi
            - timedelta(days=1)
        )

        self.task.save(
            update_fields=[
                "data_scadenza"
            ]
        )

        notifications = (
            generate_overdue_notifications(
                tasks=[
                    self.task
                ]
            )
        )

        self.assertEqual(
            len(notifications),
            1,
        )

    # =====================================================
    # INTEGRAZIONE CON TASK SERVICES
    # =====================================================

    def test_create_task_genera_automaticamente_notifica(self):
        task = create_task(
            user=self.pm,
            commessa=self.commessa,
            fase=self.fase,
            assegnato_a=self.consulente,
            titolo="Nuovo task automatico",
            descrizione="",
            priorita=Task.Priorita.NORMALE,
            data_inizio=self.oggi,
            data_scadenza=(
                self.oggi
                + timedelta(days=5)
            ),
        )

        self.assertTrue(
            Notification.objects.filter(
                destinatario=self.consulente,
                task=task,
                tipo=(
                    Notification
                    .Tipo
                    .TASK_ASSIGNED
                ),
            ).exists()
        )

    def test_cambio_assegnatario_genera_notifica_al_nuovo_utente(self):
        task = self.task

        update_task(
            user=self.pm,
            task=task,
            fase=self.fase,
            titolo=task.titolo,
            descrizione=task.descrizione,
            assegnato_a=self.altro_consulente,
            priorita=task.priorita,
            data_inizio=task.data_inizio,
            data_scadenza=task.data_scadenza,
        )

        self.assertTrue(
            Notification.objects.filter(
                destinatario=self.altro_consulente,
                task=task,
                tipo=(
                    Notification
                    .Tipo
                    .TASK_ASSIGNED
                ),
            ).exists()
        )

    def test_add_task_comment_genera_automaticamente_notifica(self):
        commento = add_task_comment(
            user=self.consulente,
            task=self.task,
            testo="Ho iniziato l'attività.",
        )

        self.assertTrue(
            Notification.objects.filter(
                task=commento.task,
                destinatario=self.pm,
                tipo=(
                    Notification
                    .Tipo
                    .TASK_COMMENTED
                ),
            ).exists()
        )

    # =====================================================
    # PRIVACY DOCUMENTI
    # =====================================================

    def test_documento_privato_non_genera_notifiche_teamwork(self):
        documento = DocumentoCommessa.objects.create(
            commessa=self.commessa,
            fase=self.fase,
            file="documenti_commesse/test/riservato.pdf",
            nome_originale="riservato.pdf",
            categoria=DocumentoCommessa.Categoria.CONTRATTO,
            dimensione_byte=128,
            caricato_da=self.admin,
            privato=True,
        )

        notifications = notify_documento_caricato(
            documento=documento,
            actor=self.admin,
        )

        self.assertEqual(notifications, [])
        self.assertFalse(
            Notification.objects.filter(
                documento=documento,
                tipo=Notification.Tipo.DOCUMENTO_CARICATO,
            ).exists()
        )

    def test_eliminazione_documento_privato_non_genera_notifiche_teamwork(self):
        documento = DocumentoCommessa.objects.create(
            commessa=self.commessa,
            fase=self.fase,
            file="documenti_commesse/test/riservato.pdf",
            nome_originale="riservato.pdf",
            categoria=DocumentoCommessa.Categoria.CONTRATTO,
            dimensione_byte=128,
            caricato_da=self.admin,
            privato=True,
        )

        notifications = notify_documento_eliminato(
            documento=documento,
            actor=self.admin,
        )

        self.assertEqual(notifications, [])
        self.assertFalse(
            Notification.objects.filter(
                documento=documento,
                tipo=Notification.Tipo.DOCUMENTO_ELIMINATO,
            ).exists()
        )

    def test_documento_non_privato_continua_a_notificare_il_teamwork(self):
        documento = DocumentoCommessa.objects.create(
            commessa=self.commessa,
            fase=self.fase,
            file="documenti_commesse/test/condiviso.pdf",
            nome_originale="condiviso.pdf",
            categoria=DocumentoCommessa.Categoria.ALTRO,
            dimensione_byte=128,
            caricato_da=self.admin,
            privato=False,
        )

        notifications = notify_documento_caricato(
            documento=documento,
            actor=self.admin,
        )

        destinatari = {
            notification.destinatario_id
            for notification in notifications
            if notification is not None
        }

        self.assertEqual(
            destinatari,
            {
                self.pm.pk,
                self.consulente.pk,
                self.altro_consulente.pk,
            },
        )

    # =====================================================
    # ACCESSO CORRENTE TASK / NOTIFICHE TEMPORALI
    # =====================================================

    def test_scadenza_non_notifica_utente_rimosso_dalla_fase(self):
        self.assegnazione_consulente.stato = Assegnazione.Stato.CONCLUSA
        self.assegnazione_consulente.save(update_fields=["stato"])

        notification = notify_task_due_soon(task=self.task)

        self.assertIsNone(notification)
        self.assertFalse(
            Notification.objects.filter(
                task=self.task,
                destinatario=self.consulente,
                tipo=Notification.Tipo.TASK_DUE_SOON,
            ).exists()
        )

    def test_scaduto_non_notifica_utente_rimosso_dalla_fase(self):
        self.task.data_scadenza = self.oggi - timedelta(days=1)
        self.task.save(update_fields=["data_scadenza"])

        self.assegnazione_consulente.stato = Assegnazione.Stato.CONCLUSA
        self.assegnazione_consulente.save(update_fields=["stato"])

        notification = notify_task_overdue(task=self.task)

        self.assertIsNone(notification)
        self.assertFalse(
            Notification.objects.filter(
                task=self.task,
                destinatario=self.consulente,
                tipo=Notification.Tipo.TASK_OVERDUE,
            ).exists()
        )

