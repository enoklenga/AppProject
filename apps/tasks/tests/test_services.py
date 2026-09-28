from datetime import timedelta

from django.core.exceptions import (
    PermissionDenied,
    ValidationError,
)
from django.test import TestCase
from django.utils import timezone

from apps.accounts.models import User
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
    delete_task,
    update_task,
    update_task_status,
)


class TaskServicesTests(TestCase):

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

        # =================================================
        # CLIENTE / COMMESSE
        # =================================================

        self.cliente = Cliente.objects.create(
            ragione_sociale="Cliente Test",
            partita_iva="12345678901",
        )

        self.commessa = Commessa.objects.create(
            cliente=self.cliente,
            codice="COMM-001",
            descrizione="Commessa test",
            ore_budget=200,
            data_inizio=(
                self.oggi
                - timedelta(days=30)
            ),
        )

        self.altra_commessa = Commessa.objects.create(
            cliente=self.cliente,
            codice="COMM-002",
            descrizione="Altra commessa",
            ore_budget=200,
            data_inizio=(
                self.oggi
                - timedelta(days=30)
            ),
        )

        # Le fasi di sistema vengono create
        # automaticamente insieme alle commesse.
        self.fase = FaseCommessa.objects.get(
            commessa=self.commessa,
            sistema=True,
        )

        self.fase_altra = FaseCommessa.objects.get(
            commessa=self.altra_commessa,
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
                commessa=self.altra_commessa,
                fase=self.fase_altra,
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

    # =====================================================
    # HELPER
    # =====================================================

    def _create_task(self):
        return create_task(
            user=self.pm,
            commessa=self.commessa,
            fase=self.fase,
            assegnato_a=self.consulente,
            titolo="Preparare report",
            descrizione="Preparare il report finale.",
            priorita=Task.Priorita.ALTA,
            data_inizio=self.oggi,
            data_scadenza=(
                self.oggi
                + timedelta(days=7)
            ),
        )

    # =====================================================
    # CREAZIONE
    # =====================================================

    def test_pm_puo_creare_task(self):
        task = self._create_task()

        self.assertEqual(
            task.commessa,
            self.commessa,
        )

        self.assertEqual(
            task.fase,
            self.fase,
        )

        self.assertEqual(
            task.assegnato_a,
            self.consulente,
        )

        self.assertEqual(
            task.creato_da,
            self.pm,
        )

        self.assertEqual(
            task.stato,
            Task.Stato.DA_FARE,
        )

        self.assertEqual(
            task.priorita,
            Task.Priorita.ALTA,
        )

    def test_consulente_puo_creare_task_nel_teamwork(self):
        task = create_task(
            user=self.consulente,
            commessa=self.commessa,
            fase=self.fase,
            assegnato_a=self.consulente,
            titolo="Task consulente",
        )

        self.assertEqual(
            task.creato_da,
            self.consulente,
        )

        self.assertEqual(
            task.fase,
            self.fase,
        )

    def test_pm_non_puo_creare_task_su_altra_commessa(self):
        with self.assertRaises(
            PermissionDenied
        ):
            create_task(
                user=self.pm,
                commessa=self.altra_commessa,
                fase=self.fase_altra,
                assegnato_a=self.altro_consulente,
                titolo="Task non consentito",
            )

    def test_admin_puo_creare_task(self):
        task = create_task(
            user=self.admin,
            commessa=self.commessa,
            fase=self.fase,
            assegnato_a=self.consulente,
            titolo="Task Admin",
        )

        self.assertEqual(
            task.creato_da,
            self.admin,
        )

        self.assertEqual(
            task.fase,
            self.fase,
        )

    def test_fase_obbligatoria(self):
        with self.assertRaises(
            ValidationError
        ):
            create_task(
                user=self.admin,
                commessa=self.commessa,
                assegnato_a=self.consulente,
                titolo="Task senza fase",
            )

    def test_non_si_puo_usare_fase_di_altra_commessa(self):
        with self.assertRaises(
            ValidationError
        ):
            create_task(
                user=self.admin,
                commessa=self.commessa,
                fase=self.fase_altra,
                assegnato_a=self.consulente,
                titolo="Task fase errata",
            )

    def test_non_si_puo_assegnare_a_utente_non_assegnato(self):
        with self.assertRaises(
            ValidationError
        ):
            create_task(
                user=self.pm,
                commessa=self.commessa,
                fase=self.fase,
                assegnato_a=self.altro_consulente,
                titolo="Task non valido",
            )

    def test_non_si_puo_assegnare_a_assegnazione_conclusa(self):
        self.assegnazione_consulente.stato = (
            Assegnazione.Stato.CONCLUSA
        )

        self.assegnazione_consulente.save(
            update_fields=[
                "stato"
            ]
        )

        with self.assertRaises(
            ValidationError
        ):
            create_task(
                user=self.pm,
                commessa=self.commessa,
                fase=self.fase,
                assegnato_a=self.consulente,
                titolo="Task non valido",
            )

    def test_non_si_puo_creare_task_su_commessa_chiusa(self):
        self.commessa.stato = (
            Commessa.Stato.CHIUSA
        )

        self.commessa.save(
            update_fields=[
                "stato"
            ]
        )

        with self.assertRaises(
            PermissionDenied
        ):
            create_task(
                user=self.pm,
                commessa=self.commessa,
                fase=self.fase,
                assegnato_a=self.consulente,
                titolo="Task non valido",
            )

    def test_titolo_obbligatorio(self):
        with self.assertRaises(
            ValidationError
        ):
            create_task(
                user=self.pm,
                commessa=self.commessa,
                fase=self.fase,
                assegnato_a=self.consulente,
                titolo="   ",
            )

    def test_scadenza_non_puo_precedere_inizio(self):
        with self.assertRaises(
            ValidationError
        ):
            create_task(
                user=self.pm,
                commessa=self.commessa,
                fase=self.fase,
                assegnato_a=self.consulente,
                titolo="Task date",
                data_inizio=self.oggi,
                data_scadenza=(
                    self.oggi
                    - timedelta(days=1)
                ),
            )

    # =====================================================
    # MODIFICA
    # =====================================================

    def test_pm_puo_modificare_task(self):
        task = self._create_task()

        aggiornato = update_task(
            user=self.pm,
            task=task,
            fase=self.fase,
            titolo="Report aggiornato",
            descrizione="Nuova descrizione",
            assegnato_a=self.consulente,
            priorita=Task.Priorita.NORMALE,
            data_inizio=self.oggi,
            data_scadenza=(
                self.oggi
                + timedelta(days=10)
            ),
        )

        self.assertEqual(
            aggiornato.titolo,
            "Report aggiornato",
        )

        self.assertEqual(
            aggiornato.priorita,
            Task.Priorita.NORMALE,
        )

        self.assertEqual(
            aggiornato.fase,
            self.fase,
        )

    def test_consulente_puo_modificare_task_del_team(self):
        task = self._create_task()

        aggiornato = update_task(
            user=self.consulente,
            task=task,
            fase=self.fase,
            titolo="Modifica consulente",
            descrizione="Aggiornamento effettuato dal team.",
            assegnato_a=self.consulente,
            priorita=Task.Priorita.ALTA,
            data_inizio=task.data_inizio,
            data_scadenza=task.data_scadenza,
        )

        self.assertEqual(
            aggiornato.titolo,
            "Modifica consulente",
        )

    def test_utente_fuori_fase_non_puo_modificare_task(self):
        task = self._create_task()

        with self.assertRaises(
            PermissionDenied
        ):
            update_task(
                user=self.altro_consulente,
                task=task,
                fase=self.fase,
                titolo="Modifica non autorizzata",
                descrizione="",
                assegnato_a=self.consulente,
                priorita=Task.Priorita.ALTA,
                data_inizio=task.data_inizio,
                data_scadenza=task.data_scadenza,
            )

    def test_non_si_puo_spostare_task_su_fase_di_altra_commessa(self):
        task = self._create_task()

        with self.assertRaises(
            ValidationError
        ):
            update_task(
                user=self.admin,
                task=task,
                fase=self.fase_altra,
                titolo=task.titolo,
                descrizione=task.descrizione,
                assegnato_a=self.consulente,
                priorita=task.priorita,
                data_inizio=task.data_inizio,
                data_scadenza=task.data_scadenza,
            )

    # =====================================================
    # STATO
    # =====================================================

    def test_consulente_puo_portare_task_in_corso(self):
        task = self._create_task()

        aggiornato = update_task_status(
            user=self.consulente,
            task=task,
            stato=Task.Stato.IN_CORSO,
        )

        self.assertEqual(
            aggiornato.stato,
            Task.Stato.IN_CORSO,
        )

        self.assertIsNone(
            aggiornato.completato_il
        )

    def test_completamento_imposta_data_automatica(self):
        task = self._create_task()

        aggiornato = update_task_status(
            user=self.consulente,
            task=task,
            stato=Task.Stato.COMPLETATA,
        )

        self.assertEqual(
            aggiornato.stato,
            Task.Stato.COMPLETATA,
        )

        self.assertIsNotNone(
            aggiornato.completato_il
        )

    def test_riapertura_azzera_data_completamento(self):
        task = self._create_task()

        task = update_task_status(
            user=self.consulente,
            task=task,
            stato=Task.Stato.COMPLETATA,
        )

        self.assertIsNotNone(
            task.completato_il
        )

        task = update_task_status(
            user=self.consulente,
            task=task,
            stato=Task.Stato.IN_CORSO,
        )

        self.assertIsNone(
            task.completato_il
        )

    def test_altro_consulente_non_puo_modificare_stato(self):
        task = self._create_task()

        with self.assertRaises(
            PermissionDenied
        ):
            update_task_status(
                user=self.altro_consulente,
                task=task,
                stato=Task.Stato.IN_CORSO,
            )

    # =====================================================
    # COMMENTI
    # =====================================================

    def test_assegnatario_puo_commentare(self):
        task = self._create_task()

        commento = add_task_comment(
            user=self.consulente,
            task=task,
            testo="Ho iniziato l'attività.",
        )

        self.assertEqual(
            commento.task,
            task,
        )

        self.assertEqual(
            commento.autore,
            self.consulente,
        )

        self.assertEqual(
            TaskComment.objects.count(),
            1,
        )

    def test_pm_puo_commentare(self):
        task = self._create_task()

        add_task_comment(
            user=self.pm,
            task=task,
            testo="Procedere con priorità.",
        )

        self.assertEqual(
            TaskComment.objects.count(),
            1,
        )

    def test_commento_vuoto_non_consentito(self):
        task = self._create_task()

        with self.assertRaises(
            ValidationError
        ):
            add_task_comment(
                user=self.consulente,
                task=task,
                testo="   ",
            )

    def test_altro_consulente_non_puo_commentare(self):
        task = self._create_task()

        with self.assertRaises(
            PermissionDenied
        ):
            add_task_comment(
                user=self.altro_consulente,
                task=task,
                testo="Non dovrei poter commentare.",
            )

    # =====================================================
    # ELIMINAZIONE
    # =====================================================

    def test_pm_puo_eliminare_task(self):
        task = self._create_task()

        task_id = task.pk

        delete_task(
            user=self.pm,
            task=task,
        )

        self.assertFalse(
            Task.objects.filter(
                pk=task_id
            ).exists()
        )

    def test_consulente_puo_eliminare_task_del_team(self):
        task = self._create_task()

        task_id = task.pk

        delete_task(
            user=self.consulente,
            task=task,
        )

        self.assertFalse(
            Task.objects.filter(
                pk=task_id
            ).exists()
        )

    def test_utente_fuori_fase_non_puo_eliminare_task(self):
        task = self._create_task()

        with self.assertRaises(
            PermissionDenied
        ):
            delete_task(
                user=self.altro_consulente,
                task=task,
            )

    # =====================================================
    # ADMIN COME ASSEGNATARIO
    # =====================================================

    def test_task_puo_essere_assegnato_ad_admin_senza_assegnazione(self):
        task = create_task(
            user=self.pm,
            commessa=self.commessa,
            fase=self.fase,
            assegnato_a=self.admin,
            titolo="Task assegnato ad Admin",
            descrizione="",
            priorita=Task.Priorita.NORMALE,
            data_inizio=self.oggi,
            data_scadenza=(
                self.oggi
                + timedelta(days=5)
            ),
        )

        self.assertEqual(
            task.assegnato_a,
            self.admin,
        )

        self.assertEqual(
            task.commessa,
            self.commessa,
        )

        self.assertEqual(
            task.fase,
            self.fase,
        )