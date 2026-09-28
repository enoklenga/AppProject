from datetime import timedelta

from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase
from django.utils import timezone

from apps.accounts.models import User
from apps.planning.models import GiornoPianificato
from apps.planning.services import (
    create_planning,
    delete_planning,
    update_planning,
)
from apps.projects.models import Assegnazione, Cliente, Commessa


class PlanningServiceTests(TestCase):
    def setUp(self):
        self.today = timezone.localdate()
        self.tomorrow = self.today + timedelta(days=1)
        self.day_after = self.today + timedelta(days=2)

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

        self.admin = User.objects.create_user(
            email="admin@example.com",
            password="TestPassword123!",
            first_name="Admin",
            last_name="LEF",
            ruolo=User.Ruolo.ADMIN,
        )

        self.cliente = Cliente.objects.create(
            ragione_sociale="Cliente Test",
            partita_iva="12345678901",
        )

        self.commessa_1 = Commessa.objects.create(
            cliente=self.cliente,
            codice="COMM-001",
            descrizione="Prima commessa di test",
            ore_budget=100,
            data_inizio=self.today,
            data_fine_prevista=self.today + timedelta(days=90),
            stato=Commessa.Stato.APERTA,
        )

        self.commessa_2 = Commessa.objects.create(
            cliente=self.cliente,
            codice="COMM-002",
            descrizione="Seconda commessa di test",
            ore_budget=100,
            data_inizio=self.today,
            data_fine_prevista=self.today + timedelta(days=90),
            stato=Commessa.Stato.APERTA,
        )

        self.assegnazione_1 = Assegnazione.objects.create(
            consulente=self.consulente,
            commessa=self.commessa_1,
            ore_previste=20,
            ruolo_commessa=Assegnazione.Ruolo.CONSULENTE,
            stato=Assegnazione.Stato.ATTIVA,
            data_inizio=self.today,
        )

        self.assegnazione_2 = Assegnazione.objects.create(
            consulente=self.consulente,
            commessa=self.commessa_2,
            ore_previste=20,
            ruolo_commessa=Assegnazione.Ruolo.CONSULENTE,
            stato=Assegnazione.Stato.ATTIVA,
            data_inizio=self.today,
        )

    def test_consulente_puo_creare_propria_pianificazione(self):
        pianificazione = create_planning(
            user=self.consulente,
            assegnazione=self.assegnazione_1,
            data=self.tomorrow,
            ore_pianificate=4,
        )

        self.assertEqual(
            pianificazione.assegnazione,
            self.assegnazione_1,
        )
        self.assertEqual(
            pianificazione.ore_pianificate,
            4,
        )
        self.assertEqual(
            pianificazione.inserita_da,
            self.consulente,
        )

    def test_non_si_puo_pianificare_per_un_altro_consulente(self):
        with self.assertRaises(PermissionDenied):
            create_planning(
                user=self.altro_consulente,
                assegnazione=self.assegnazione_1,
                data=self.tomorrow,
                ore_pianificate=4,
            )

    def test_admin_puo_creare_pianificazione_per_un_altro(self):
        pianificazione = create_planning(
            user=self.admin,
            assegnazione=self.assegnazione_1,
            data=self.tomorrow,
            ore_pianificate=4,
        )

        self.assertEqual(
            pianificazione.assegnazione,
            self.assegnazione_1,
        )

        self.assertEqual(
            pianificazione.assegnazione.consulente,
            self.consulente,
        )

        self.assertEqual(
            pianificazione.ore_pianificate,
            4,
        )

        self.assertEqual(
            pianificazione.inserita_da,
            self.admin,
        )

    def test_non_si_puo_creare_pianificazione_su_data_passata(self):
        ieri = self.today - timedelta(days=1)

        with self.assertRaises(ValidationError):
            create_planning(
                user=self.consulente,
                assegnazione=self.assegnazione_1,
                data=ieri,
                ore_pianificate=4,
            )

    def test_massimo_8_ore_pianificate_nello_stesso_giorno(self):
        create_planning(
            user=self.consulente,
            assegnazione=self.assegnazione_1,
            data=self.tomorrow,
            ore_pianificate=6,
        )

        with self.assertRaises(ValidationError):
            create_planning(
                user=self.consulente,
                assegnazione=self.assegnazione_2,
                data=self.tomorrow,
                ore_pianificate=3,
            )

    def test_esattamente_8_ore_nello_stesso_giorno_sono_ammesse(self):
        create_planning(
            user=self.consulente,
            assegnazione=self.assegnazione_1,
            data=self.tomorrow,
            ore_pianificate=4,
        )

        seconda = create_planning(
            user=self.consulente,
            assegnazione=self.assegnazione_2,
            data=self.tomorrow,
            ore_pianificate=4,
        )

        self.assertEqual(
            seconda.ore_pianificate,
            4,
        )

    def test_non_si_possono_superare_le_ore_previste_assegnazione(self):
        self.assegnazione_1.ore_previste = 6
        self.assegnazione_1.save(
            update_fields=["ore_previste", "updated_at"]
        )

        create_planning(
            user=self.consulente,
            assegnazione=self.assegnazione_1,
            data=self.tomorrow,
            ore_pianificate=4,
        )

        with self.assertRaises(ValidationError):
            create_planning(
                user=self.consulente,
                assegnazione=self.assegnazione_1,
                data=self.day_after,
                ore_pianificate=3,
            )

    def test_non_si_puo_creare_due_volte_stessa_assegnazione_stesso_giorno(self):
        create_planning(
            user=self.consulente,
            assegnazione=self.assegnazione_1,
            data=self.tomorrow,
            ore_pianificate=2,
        )

        with self.assertRaises(ValidationError):
            create_planning(
                user=self.consulente,
                assegnazione=self.assegnazione_1,
                data=self.tomorrow,
                ore_pianificate=3,
            )

    def test_non_si_puo_pianificare_su_assegnazione_conclusa(self):
        self.assegnazione_1.stato = Assegnazione.Stato.CONCLUSA
        self.assegnazione_1.save(
            update_fields=["stato", "updated_at"]
        )

        with self.assertRaises(PermissionDenied):
            create_planning(
                user=self.consulente,
                assegnazione=self.assegnazione_1,
                data=self.tomorrow,
                ore_pianificate=4,
            )

    def test_non_si_puo_pianificare_su_commessa_chiusa(self):
        self.commessa_1.stato = Commessa.Stato.CHIUSA
        self.commessa_1.save(
            update_fields=["stato", "updated_at"]
        )

        with self.assertRaises(PermissionDenied):
            create_planning(
                user=self.consulente,
                assegnazione=self.assegnazione_1,
                data=self.tomorrow,
                ore_pianificate=4,
            )

    def test_data_deve_rientrare_nel_periodo_assegnazione(self):
        self.assegnazione_1.data_inizio = self.today + timedelta(days=10)
        self.assegnazione_1.save(
            update_fields=["data_inizio", "updated_at"]
        )

        with self.assertRaises(ValidationError):
            create_planning(
                user=self.consulente,
                assegnazione=self.assegnazione_1,
                data=self.tomorrow,
                ore_pianificate=4,
            )

    def test_consulente_puo_modificare_pianificazione_futura(self):
        pianificazione = create_planning(
            user=self.consulente,
            assegnazione=self.assegnazione_1,
            data=self.tomorrow,
            ore_pianificate=4,
        )

        aggiornata = update_planning(
            user=self.consulente,
            pianificazione=pianificazione,
            data=self.tomorrow,
            ore_pianificate=6,
        )

        self.assertEqual(
            aggiornata.ore_pianificate,
            6,
        )

    def test_consulente_puo_eliminare_pianificazione_futura(self):
        pianificazione = create_planning(
            user=self.consulente,
            assegnazione=self.assegnazione_1,
            data=self.tomorrow,
            ore_pianificate=4,
        )

        planning_id = pianificazione.pk

        delete_planning(
            user=self.consulente,
            pianificazione=pianificazione,
        )

        self.assertFalse(
            GiornoPianificato.objects.filter(
                pk=planning_id
            ).exists()
        )

    def test_altro_consulente_non_puo_modificare(self):
        pianificazione = create_planning(
            user=self.consulente,
            assegnazione=self.assegnazione_1,
            data=self.tomorrow,
            ore_pianificate=4,
        )

        with self.assertRaises(PermissionDenied):
            update_planning(
                user=self.altro_consulente,
                pianificazione=pianificazione,
                data=self.tomorrow,
                ore_pianificate=5,
            )