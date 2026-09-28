from datetime import date, timedelta

from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.accounts.models import User
from apps.phases.models import FaseCommessa
from apps.projects.models import Assegnazione, Cliente, Commessa
from apps.tasks.models import Task


class CommessaFaseModelTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="consulente@example.com",
            password="password",
            first_name="Mario",
            last_name="Rossi",
        )
        self.cliente = Cliente.objects.create(
            ragione_sociale="Cliente Test",
            partita_iva="IT00000000000",
        )
        self.commessa = Commessa.objects.create(
            cliente=self.cliente,
            codice="C-001",
            descrizione="Test",
            data_inizio=date.today(),
            data_fine_prevista=date.today() + timedelta(days=90),
        )

    def test_commessa_creates_general_phase(self):
        fase = FaseCommessa.objects.get(commessa=self.commessa, sistema=True)
        self.assertEqual(fase.nome, "Generale")
        self.assertEqual(fase.data_inizio, self.commessa.data_inizio)

    def test_assignment_is_phase_specific(self):
        fase = FaseCommessa.objects.create(
            commessa=self.commessa,
            nome="Analisi",
            data_inizio=self.commessa.data_inizio,
        )
        assignment = Assegnazione.objects.create(
            consulente=self.user,
            commessa=self.commessa,
            fase=fase,
            ore_previste=20,
            data_inizio=fase.data_inizio,
        )
        self.assertEqual(assignment.fase_id, fase.id)

    def test_task_must_belong_to_commessa_phase(self):
        fase = FaseCommessa.objects.create(
            commessa=self.commessa,
            nome="Analisi",
            data_inizio=self.commessa.data_inizio,
        )
        Assegnazione.objects.create(
            consulente=self.user,
            commessa=self.commessa,
            fase=fase,
            ore_previste=20,
            data_inizio=fase.data_inizio,
        )
        task = Task(
            commessa=self.commessa,
            fase=fase,
            titolo="Task di fase",
            assegnato_a=self.user,
            creato_da=self.user,
        )
        task.full_clean()
        task.save()
        self.assertEqual(task.fase_id, fase.id)

    def test_phase_date_cannot_precede_commessa(self):
        fase = FaseCommessa(
            commessa=self.commessa,
            nome="Errata",
            data_inizio=self.commessa.data_inizio - timedelta(days=1),
        )
        with self.assertRaises(ValidationError):
            fase.full_clean()
