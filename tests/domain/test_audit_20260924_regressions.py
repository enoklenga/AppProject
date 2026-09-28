from datetime import timedelta

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models.deletion import ProtectedError
from django.test import TestCase
from django.contrib import admin
from django.utils import timezone

from apps.accounts.models import Skill, User, UserSkill
from apps.accounts.services import set_user_active
from apps.operations.models import PeriodoMensile
from apps.operations.services.periodi import chiudi_periodo
from apps.phases.models import FaseCommessa
from apps.planning.admin import GiornoPianificatoAdmin
from apps.planning.models import GiornoPianificato
from apps.planning.permissions import can_create_planning
from apps.planning.services import confirm_planning, create_planning
from apps.projects.models import Assegnazione, Cliente, Commessa
from apps.projects.services import set_assegnazione_stato, set_commessa_workflow
from apps.tasks.models import Task
from apps.tasks.permissions import can_create_task
from apps.tasks.services import create_task
from apps.timesheets.admin import RigaOreAdmin, SpesaTrasfertaAdmin
from apps.timesheets.models import RigaOre, SpesaTrasferta
from apps.timesheets.services import inserisci_ore


class Audit20260924RegressionTests(TestCase):
    def setUp(self):
        self.today = timezone.localdate()
        self.tomorrow = self.today + timedelta(days=1)
        self.admin = User.objects.create_user(
            email="audit-admin@example.com",
            password="Password123!",
            ruolo=User.Ruolo.ADMIN,
        )
        self.pm = User.objects.create_user(
            email="audit-pm@example.com",
            password="Password123!",
            ruolo=User.Ruolo.CONSULENTE,
        )
        self.consulente = User.objects.create_user(
            email="audit-consulente@example.com",
            password="Password123!",
            ruolo=User.Ruolo.CONSULENTE,
        )
        self.cliente = Cliente.objects.create(
            ragione_sociale="Cliente Audit",
            partita_iva="99999999991",
        )
        self.commessa = Commessa.objects.create(
            cliente=self.cliente,
            codice="AUDIT-20260924",
            descrizione="Regression audit",
            ore_budget=100,
            data_inizio=self.today,
            data_fine_prevista=self.today + timedelta(days=60),
        )
        self.fase_generale = FaseCommessa.objects.get(
            commessa=self.commessa,
            sistema=True,
        )
        self.fase_due = FaseCommessa.objects.create(
            commessa=self.commessa,
            nome="Fase 2",
            data_inizio=self.today,
            data_fine_prevista=self.today + timedelta(days=60),
            ordine=2,
        )
        self.ass_pm = Assegnazione.objects.create(
            consulente=self.pm,
            commessa=self.commessa,
            fase=self.fase_generale,
            ore_previste=40,
            ruolo_commessa=Assegnazione.Ruolo.PROJECT_MANAGER,
            data_inizio=self.today,
        )
        self.ass_consulente = Assegnazione.objects.create(
            consulente=self.consulente,
            commessa=self.commessa,
            fase=self.fase_due,
            ore_previste=40,
            data_inizio=self.today,
        )

    def _sessione(self, giorno=None, ore=4):
        return create_planning(
            user=self.pm,
            assegnazione=self.ass_consulente,
            data=giorno or self.today,
            ore_pianificate=ore,
            tipo_attivita="CONSULENZA",
        )

    def test_chiusura_mese_blocca_sessione_non_confermata(self):
        self._sessione()
        with self.assertRaises(ValidationError):
            chiudi_periodo(
                attore=self.admin,
                anno=self.today.year,
                mese=self.today.month,
            )

    def test_conclusione_assegnazione_blocca_sessione_non_confermata(self):
        self._sessione()
        with self.assertRaises(ValidationError):
            set_assegnazione_stato(
                attore=self.admin,
                assegnazione=self.ass_consulente,
                nuovo_stato=Assegnazione.Stato.CONCLUSA,
            )

    def test_disattivazione_blocca_lavoro_operativo_aperto(self):
        with self.assertRaises(ValidationError):
            set_user_active(
                attore=self.admin,
                user=self.consulente,
                active=False,
            )

    def test_pm_supervisiona_planning_e_task_cross_phase(self):
        self.assertTrue(can_create_planning(self.pm, self.ass_consulente))
        self.assertTrue(can_create_task(self.pm, self.commessa, self.fase_due))
        task = create_task(
            user=self.pm,
            commessa=self.commessa,
            fase=self.fase_due,
            assegnato_a=self.consulente,
            titolo="Task cross phase",
        )
        self.assertEqual(task.fase, self.fase_due)
        self.assertEqual(task.stato, Task.Stato.DA_FARE)

    def test_conferma_sessione_e_idempotente(self):
        sessione = self._sessione()
        prima = confirm_planning(user=self.consulente, pianificazione=sessione)
        seconda = confirm_planning(user=self.consulente, pianificazione=sessione)
        self.assertEqual(prima.pk, seconda.pk)
        self.assertEqual(
            RigaOre.objects.filter(assegnazione=self.ass_consulente, data=self.today).count(),
            1,
        )

    def test_riga_generata_da_agenda_e_protetta_anche_da_delete_orm(self):
        sessione = confirm_planning(
            user=self.consulente,
            pianificazione=self._sessione(),
        )
        riga = RigaOre.objects.get(pk=sessione.riga_ore_generata_id)
        with self.assertRaises(ProtectedError):
            riga.delete()

    def test_workflow_sospeso_blocca_nuovo_lavoro(self):
        set_commessa_workflow(
            attore=self.admin,
            commessa=self.commessa,
            nuovo_stato=Commessa.WorkflowStato.SOSPESA,
            motivazione="Test sospensione.",
        )
        self.commessa.refresh_from_db()
        self.ass_consulente.refresh_from_db()
        self.assertFalse(can_create_planning(self.pm, self.ass_consulente))
        self.assertFalse(can_create_task(self.pm, self.commessa, self.fase_due))
        with self.assertRaises(ValidationError):
            inserisci_ore(
                attore=self.consulente,
                assegnazione_id=self.ass_consulente.id,
                giorno=self.today,
                tipo_attivita="CONSULENZA",
                ore=1,
            )


    def test_conferma_sessione_bloccata_se_periodo_chiuso(self):
        sessione = self._sessione()
        periodo, _ = PeriodoMensile.objects.get_or_create(
            anno=self.today.year,
            mese=self.today.month,
        )
        periodo.stato = PeriodoMensile.Stato.CHIUSO
        periodo.chiuso_da = self.admin
        periodo.save(update_fields=("stato", "chiuso_da"))
        with self.assertRaises(ValidationError):
            confirm_planning(user=self.consulente, pianificazione=sessione)

    def test_ingaggiabilita_giornaliera_deriva_dall_agenda(self):
        self._sessione(ore=8)
        self.assertFalse(
            self.consulente.is_risorsa_ingaggiabile_in_data(self.today)
        )
        self.assertTrue(
            self.consulente.is_risorsa_ingaggiabile_in_data(self.tomorrow)
        )

    def test_django_admin_operativo_e_solo_lettura(self):
        planning_admin = GiornoPianificatoAdmin(GiornoPianificato, admin.site)
        ore_admin = RigaOreAdmin(RigaOre, admin.site)
        spese_admin = SpesaTrasfertaAdmin(SpesaTrasferta, admin.site)
        for model_admin in (planning_admin, ore_admin, spese_admin):
            self.assertFalse(model_admin.has_add_permission(None))
            self.assertFalse(model_admin.has_change_permission(None))
            self.assertFalse(model_admin.has_delete_permission(None))

    def test_skill_matrix_livello_fuori_range_bloccato_dal_db(self):
        skill = Skill.objects.create(nome="Audit skill")
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                UserSkill.objects.create(
                    utente=self.consulente,
                    skill=skill,
                    livello=4,
                )

    def test_admin_oltre_otto_ore_richiede_motivazione(self):
        inserisci_ore(
            attore=self.admin,
            assegnazione_id=self.ass_consulente.id,
            giorno=self.today,
            tipo_attivita="CONSULENZA",
            ore=8,
            motivazione="Inserimento amministrativo iniziale.",
        )
        with self.assertRaises(ValidationError):
            inserisci_ore(
                attore=self.admin,
                assegnazione_id=self.ass_consulente.id,
                giorno=self.today,
                tipo_attivita="FORMAZIONE",
                ore=1,
            )
