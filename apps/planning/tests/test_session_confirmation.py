from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase
from django.utils import timezone

from apps.accounts.models import User
from apps.phases.models import FaseCommessa
from apps.planning.models import GiornoPianificato
from apps.planning.permissions import can_confirm_planning, can_delete_planning, can_edit_planning
from apps.planning.services import confirm_planning, create_planning
from apps.projects.models import Assegnazione, Cliente, Commessa
from apps.projects.services import agenda_progress, chiudi_commessa
from apps.timesheets.models import RigaOre
from apps.timesheets.services import elimina_ore, modifica_ore


class AgendaConfirmationTests(TestCase):
    def setUp(self):
        self.today = timezone.localdate()
        self.risorsa = User.objects.create_user(
            email="risorsa@example.com",
            password="Password123!",
            first_name="Mario",
            last_name="Rossi",
            ruolo=User.Ruolo.CONSULENTE,
        )
        self.admin = User.objects.create_user(
            email="admin@example.com",
            password="Password123!",
            first_name="Admin",
            last_name="LEF",
            ruolo=User.Ruolo.ADMIN,
        )
        self.cliente = Cliente.objects.create(
            ragione_sociale="Cliente Agenda",
            partita_iva="12345678901",
        )
        self.commessa = Commessa.objects.create(
            cliente=self.cliente,
            codice="AGENDA-001",
            descrizione="Test conferma agenda",
            ore_budget=40,
            data_inizio=self.today,
            data_fine_prevista=self.today,
        )
        self.fase = FaseCommessa.objects.get(commessa=self.commessa, sistema=True)
        self.assegnazione = Assegnazione.objects.create(
            consulente=self.risorsa,
            commessa=self.commessa,
            fase=self.fase,
            ore_previste=8,
            data_inizio=self.today,
        )
        self.sessione = create_planning(
            user=self.risorsa,
            assegnazione=self.assegnazione,
            data=self.today,
            ore_pianificate=8,
            tipo_attivita="CONSULENZA",
        )

    def test_solo_la_risorsa_puo_confermare(self):
        self.assertTrue(can_confirm_planning(self.risorsa, self.sessione))
        self.assertFalse(can_confirm_planning(self.admin, self.sessione))
        with self.assertRaises(PermissionDenied):
            confirm_planning(user=self.admin, pianificazione=self.sessione)

    def test_conferma_agenda_alimenta_timesheet(self):
        confermata = confirm_planning(user=self.risorsa, pianificazione=self.sessione)
        self.assertEqual(confermata.stato_sessione, GiornoPianificato.StatoSessione.CONFERMATA)
        self.assertIsNotNone(confermata.confermata_il)
        self.assertEqual(confermata.confermata_da, self.risorsa)
        self.assertIsNotNone(confermata.riga_ore_generata_id)

        riga = RigaOre.objects.get(pk=confermata.riga_ore_generata_id)
        self.assertEqual(riga.assegnazione, self.assegnazione)
        self.assertEqual(riga.data, self.today)
        self.assertEqual(riga.ore, 8)
        self.assertEqual(riga.tipo_attivita, "CONSULENZA")

        confermata.refresh_from_db()
        self.assertFalse(can_edit_planning(self.risorsa, confermata))
        self.assertFalse(can_delete_planning(self.risorsa, confermata))

    def test_progress_commessa_deriva_dalle_sessioni_confermate(self):
        iniziale = agenda_progress(self.commessa)
        self.assertEqual(iniziale["percentuale_ore"], 0)
        self.assertEqual(iniziale["sessioni_da_confermare"], 1)

        confirm_planning(user=self.risorsa, pianificazione=self.sessione)
        finale = agenda_progress(self.commessa)
        self.assertEqual(finale["percentuale_ore"], 100.0)
        self.assertEqual(finale["sessioni_confermate"], 1)
        self.assertTrue(finale["completa"])

    def test_chiusura_commessa_bloccata_finche_agenda_non_e_confermata(self):
        with self.assertRaises(ValidationError):
            chiudi_commessa(attore=self.admin, commessa=self.commessa)

        confirm_planning(user=self.risorsa, pianificazione=self.sessione)
        chiudi_commessa(attore=self.admin, commessa=self.commessa)
        self.commessa.refresh_from_db()
        self.assertEqual(self.commessa.stato, Commessa.Stato.CHIUSA)
        self.assertEqual(self.commessa.workflow_stato, Commessa.WorkflowStato.CHIUSA)

    def test_riga_timesheet_generata_da_agenda_non_e_modificabile_o_eliminabile(self):
        confermata = confirm_planning(user=self.risorsa, pianificazione=self.sessione)
        riga = RigaOre.objects.get(pk=confermata.riga_ore_generata_id)

        with self.assertRaises(ValidationError):
            modifica_ore(
                attore=self.risorsa,
                riga_id=riga.id,
                versione=riga.versione,
                assegnazione_id=self.assegnazione.id,
                giorno=self.today,
                tipo_attivita="CONSULENZA",
                ore=7,
            )

        with self.assertRaises(ValidationError):
            elimina_ore(
                attore=self.risorsa,
                riga_id=riga.id,
                versione=riga.versione,
            )
