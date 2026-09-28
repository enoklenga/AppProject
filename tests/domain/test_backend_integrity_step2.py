from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.accounts.models import User
from apps.operations.models import PeriodoMensile
from apps.phases.models import FaseCommessa
from apps.phases.services import delete_fase, update_fase
from apps.planning.models import GiornoPianificato
from apps.projects.forms import (
    AssegnazioneForm,
    CommessaForm,
    TariffaAssegnazioneForm,
)
from apps.projects.models import Assegnazione, Cliente, Commessa, TariffaAssegnazione
from apps.projects.services import set_assegnazione_stato, sync_general_phase_dates
from apps.tasks.services import create_task
from apps.timesheets.models import RigaOre, StatoApprovazione
from apps.timesheets.services import inserisci_ore


class BackendIntegrityStep2Tests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            email="admin-step2@example.com",
            password="Password-test-123",
            ruolo=User.Ruolo.ADMIN,
            is_staff=True,
        )
        self.consulente = User.objects.create_user(
            email="consulente-step2@example.com",
            password="Password-test-123",
        )
        self.altro = User.objects.create_user(
            email="altro-step2@example.com",
            password="Password-test-123",
        )
        self.cliente = Cliente.objects.create(
            ragione_sociale="Cliente Step2",
            partita_iva="IT00000000991",
        )
        self.commessa = Commessa.objects.create(
            cliente=self.cliente,
            codice="STEP2-001",
            descrizione="Test integrità backend step 2",
            ore_budget=200,
            data_inizio=date(2026, 1, 1),
            data_fine_prevista=date(2026, 12, 31),
        )
        self.fase = FaseCommessa.objects.get(
            commessa=self.commessa,
            sistema=True,
        )
        self.assegnazione = Assegnazione.objects.create(
            consulente=self.consulente,
            commessa=self.commessa,
            fase=self.fase,
            ore_previste=100,
            data_inizio=date(2026, 1, 1),
        )

    def _assegnazione_data(self, **overrides):
        data = {
            "consulente": str(self.consulente.pk),
            "commessa": str(self.commessa.pk),
            "fase": str(self.fase.pk),
            "ore_previste": "100",
            "ruolo_commessa": Assegnazione.Ruolo.CONSULENTE,
            "stato": Assegnazione.Stato.ATTIVA,
            "data_inizio": "2026-01-01",
            "data_fine": "",
        }
        data.update(overrides)
        return data

    def test_assegnazione_con_storia_non_puo_cambiare_consulente(self):
        RigaOre.objects.create(
            assegnazione=self.assegnazione,
            data=date(2026, 7, 10),
            tipo_attivita=TariffaAssegnazione.TipoAttivita.CONSULENZA,
            ore=4,
            inserita_da=self.consulente,
            ultima_modifica_da=self.consulente,
        )

        form = AssegnazioneForm(
            data=self._assegnazione_data(consulente=str(self.altro.pk)),
            instance=self.assegnazione,
        )

        self.assertFalse(form.is_valid())
        self.assertIn("consulente", form.errors)

    def test_assegnazione_non_puo_restringere_date_sui_dati_storici(self):
        RigaOre.objects.create(
            assegnazione=self.assegnazione,
            data=date(2026, 7, 10),
            tipo_attivita=TariffaAssegnazione.TipoAttivita.CONSULENZA,
            ore=4,
            inserita_da=self.consulente,
            ultima_modifica_da=self.consulente,
        )

        form = AssegnazioneForm(
            data=self._assegnazione_data(data_inizio="2026-08-01"),
            instance=self.assegnazione,
        )

        self.assertFalse(form.is_valid())
        self.assertIn("data_inizio", form.errors)

    def test_riattivazione_bloccata_se_commessa_chiusa(self):
        self.assegnazione.stato = Assegnazione.Stato.CONCLUSA
        self.assegnazione.save(update_fields=["stato", "updated_at"])
        self.commessa.stato = Commessa.Stato.CHIUSA
        self.commessa.save(update_fields=["stato", "updated_at"])

        with self.assertRaises(ValidationError):
            set_assegnazione_stato(
                attore=self.admin,
                assegnazione=self.assegnazione,
                nuovo_stato=Assegnazione.Stato.ATTIVA,
            )

    def test_commessa_non_puo_escludere_assegnazioni_esistenti(self):
        form = CommessaForm(
            data={
                "cliente": str(self.cliente.pk),
                "codice": self.commessa.codice,
                "descrizione": self.commessa.descrizione,
                "ore_budget": "200",
                "data_inizio": "2026-02-01",
                "data_fine_prevista": "2026-12-31",
                "stato": Commessa.Stato.APERTA,
                "note": "",
            },
            instance=self.commessa,
        )

        self.assertFalse(form.is_valid())
        self.assertIn("data_inizio", form.errors)

    def test_fase_non_puo_escludere_pianificazione_esistente(self):
        GiornoPianificato.objects.create(
            assegnazione=self.assegnazione,
            data=date(2026, 10, 10),
            ore_pianificate=4,
            inserita_da=self.admin,
            ultima_modifica_da=self.admin,
        )

        with self.assertRaises(ValidationError):
            update_fase(
                user=self.admin,
                fase=self.fase,
                nome=self.fase.nome,
                descrizione=self.fase.descrizione,
                ordine=self.fase.ordine,
                stato=self.fase.stato,
                data_inizio=self.fase.data_inizio,
                data_fine_prevista=date(2026, 10, 1),
            )

    def test_delete_fase_con_assegnazione_restituisce_validation_error(self):
        fase_secondaria = FaseCommessa.objects.create(
            commessa=self.commessa,
            nome="Secondaria",
            data_inizio=date(2026, 1, 1),
            data_fine_prevista=date(2026, 12, 31),
            creata_da=self.admin,
        )
        Assegnazione.objects.create(
            consulente=self.altro,
            commessa=self.commessa,
            fase=fase_secondaria,
            ore_previste=40,
            data_inizio=date(2026, 1, 1),
        )

        with self.assertRaises(ValidationError):
            delete_fase(user=self.admin, fase=fase_secondaria)

    def test_tariffa_retroattiva_non_puo_modificare_periodo_chiuso(self):
        RigaOre.objects.create(
            assegnazione=self.assegnazione,
            data=date(2026, 7, 10),
            tipo_attivita=TariffaAssegnazione.TipoAttivita.CONSULENZA,
            ore=4,
            inserita_da=self.consulente,
            ultima_modifica_da=self.consulente,
            stato_approvazione=StatoApprovazione.APPROVATA,
        )
        PeriodoMensile.objects.create(
            anno=2026,
            mese=7,
            stato=PeriodoMensile.Stato.CHIUSO,
            chiuso_da=self.admin,
        )

        form = TariffaAssegnazioneForm(
            data={
                "assegnazione": str(self.assegnazione.pk),
                "tipo_attivita": TariffaAssegnazione.TipoAttivita.CONSULENZA,
                "tariffa_oraria": "95.00",
                "valida_dal": "2026-07-01",
            }
        )

        self.assertFalse(form.is_valid())
        self.assertIn("valida_dal", form.errors)

    def test_scrittura_timesheet_crea_e_blocca_il_periodo_aperto(self):
        inserisci_ore(
            attore=self.consulente,
            assegnazione_id=self.assegnazione.pk,
            giorno=date(2026, 8, 5),
            tipo_attivita=TariffaAssegnazione.TipoAttivita.CONSULENZA,
            ore=4,
        )

        periodo = PeriodoMensile.objects.get(anno=2026, mese=8)
        self.assertEqual(periodo.stato, PeriodoMensile.Stato.APERTO)

    def test_task_non_puo_avere_scadenza_fuori_dalla_fase(self):
        with self.assertRaises(ValidationError):
            create_task(
                user=self.admin,
                commessa=self.commessa,
                fase=self.fase,
                assegnato_a=self.consulente,
                titolo="Task fuori fase",
                data_scadenza=date(2027, 1, 10),
            )
    def test_model_blocca_modifica_identita_storica_anche_fuori_dal_form(self):
        RigaOre.objects.create(
            assegnazione=self.assegnazione,
            data=date(2026, 7, 10),
            tipo_attivita=TariffaAssegnazione.TipoAttivita.CONSULENZA,
            ore=4,
            inserita_da=self.consulente,
            ultima_modifica_da=self.consulente,
        )

        self.assegnazione.consulente = self.altro
        with self.assertRaises(ValidationError):
            self.assegnazione.save()

    def test_stato_assegnazione_in_update_si_cambia_solo_col_workflow(self):
        form = AssegnazioneForm(
            data=self._assegnazione_data(stato=Assegnazione.Stato.CONCLUSA),
            instance=self.assegnazione,
        )

        self.assertTrue(form.is_valid(), form.errors)
        self.assertTrue(form.fields["stato"].disabled)
        self.assertEqual(
            form.cleaned_data["stato"],
            Assegnazione.Stato.ATTIVA,
        )

    def test_riattivazione_bloccata_se_fase_completata(self):
        self.assegnazione.stato = Assegnazione.Stato.CONCLUSA
        self.assegnazione.save(update_fields=["stato", "updated_at"])
        self.fase.stato = FaseCommessa.Stato.COMPLETATA
        self.fase.save(update_fields=["stato", "updated_at"])

        with self.assertRaises(ValidationError):
            set_assegnazione_stato(
                attore=self.admin,
                assegnazione=self.assegnazione,
                nuovo_stato=Assegnazione.Stato.ATTIVA,
            )

    def test_fase_generale_si_allinea_alle_date_della_commessa(self):
        self.commessa.data_fine_prevista = date(2026, 11, 30)
        self.commessa.save(update_fields=["data_fine_prevista", "updated_at"])

        sync_general_phase_dates(self.commessa)
        self.fase.refresh_from_db()

        self.assertEqual(
            self.fase.data_fine_prevista,
            date(2026, 11, 30),
        )

