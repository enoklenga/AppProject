from datetime import date

from django.test import TestCase

from apps.accounts.models import BusinessUnit, User, UserBusinessUnit
from apps.phases.models import FaseCommessa
from apps.projects.forms import AssegnazioneForm
from apps.projects.models import Assegnazione, Cliente, Commessa


class BusinessUnitDomainTests(TestCase):
    def setUp(self):
        self.bu_consulenza = BusinessUnit.objects.create(nome="Consulenza", codice="CONS")
        self.bu_ai = BusinessUnit.objects.create(nome="AI", codice="AI")
        self.utente = User.objects.create_user(
            email="multi-bu@example.com",
            password="Password-123!",
            ruolo=User.Ruolo.CONSULENTE,
            is_active=True,
            deve_cambiare_password=False,
        )

    def test_utente_puo_appartenere_a_piu_business_unit(self):
        UserBusinessUnit.objects.create(
            utente=self.utente,
            business_unit=self.bu_consulenza,
            puo_essere_pm=True,
        )
        UserBusinessUnit.objects.create(
            utente=self.utente,
            business_unit=self.bu_ai,
            responsabile=True,
        )

        self.assertEqual(self.utente.business_unit_attive().count(), 2)
        self.assertTrue(self.utente.puo_essere_pm_in_business_unit(self.bu_consulenza))
        self.assertFalse(self.utente.puo_essere_pm_in_business_unit(self.bu_ai))
        self.assertEqual(list(self.utente.business_unit_gestite()), [self.bu_ai])

    def test_pm_eligibility_e_specifica_per_business_unit(self):
        UserBusinessUnit.objects.create(
            utente=self.utente,
            business_unit=self.bu_consulenza,
            puo_essere_pm=True,
        )
        UserBusinessUnit.objects.create(
            utente=self.utente,
            business_unit=self.bu_ai,
            puo_essere_pm=False,
        )
        self.assertTrue(self.utente.puo_essere_pm_in_business_unit(self.bu_consulenza))
        self.assertFalse(self.utente.puo_essere_pm_in_business_unit(self.bu_ai))


class BusinessUnitAssignmentFormTests(TestCase):
    def setUp(self):
        self.bu = BusinessUnit.objects.create(nome="Formazione", codice="FORM")
        self.cliente = Cliente.objects.create(ragione_sociale="Cliente BU", partita_iva="IT00000000001")
        self.commessa = Commessa.objects.create(
            cliente=self.cliente,
            business_unit=self.bu,
            codice="BU-001",
            descrizione="Commessa Formazione",
            data_inizio=date(2026, 10, 1),
            data_fine_prevista=date(2026, 12, 31),
        )
        # La fase di sistema viene creata automaticamente con la commessa.
        self.fase = FaseCommessa.objects.get(commessa=self.commessa, sistema=True)
        self.membro = User.objects.create_user(
            email="membro@example.com",
            password="Password-123!",
            ruolo=User.Ruolo.CONSULENTE,
            is_active=True,
            deve_cambiare_password=False,
        )
        self.esterno = User.objects.create_user(
            email="esterno@example.com",
            password="Password-123!",
            ruolo=User.Ruolo.CONSULENTE,
            is_active=True,
            deve_cambiare_password=False,
        )
        UserBusinessUnit.objects.create(
            utente=self.membro,
            business_unit=self.bu,
            puo_essere_pm=False,
        )

    def _payload(self, user, role=Assegnazione.Ruolo.CONSULENTE):
        return {
            "consulente": str(user.pk),
            "commessa": str(self.commessa.pk),
            "fase": str(self.fase.pk),
            "ore_previste": 16,
            "ruolo_commessa": role,
            "stato": Assegnazione.Stato.ATTIVA,
            "data_inizio": "2026-10-01",
            "data_fine": "",
        }

    def test_team_operativo_puo_essere_cross_business_unit(self):
        form = AssegnazioneForm(data=self._payload(self.esterno))
        self.assertIn(self.esterno, form.fields["consulente"].queryset)
        self.assertTrue(form.is_valid(), form.errors)

    def test_pm_cross_bu_richiede_abilitazione_nella_bu_owner(self):
        form = AssegnazioneForm(
            data=self._payload(self.esterno, Assegnazione.Ruolo.PROJECT_MANAGER)
        )
        self.assertFalse(form.is_valid())
        self.assertIn("ruolo_commessa", form.errors)

        UserBusinessUnit.objects.create(
            utente=self.esterno,
            business_unit=self.bu,
            puo_essere_pm=True,
        )
        form = AssegnazioneForm(
            data=self._payload(self.esterno, Assegnazione.Ruolo.PROJECT_MANAGER)
        )
        self.assertTrue(form.is_valid(), form.errors)

    def test_pm_richiede_abilitazione_nella_business_unit(self):
        form = AssegnazioneForm(
            data=self._payload(self.membro, Assegnazione.Ruolo.PROJECT_MANAGER)
        )
        self.assertFalse(form.is_valid())
        self.assertIn("ruolo_commessa", form.errors)

        membership = UserBusinessUnit.objects.get(utente=self.membro, business_unit=self.bu)
        membership.puo_essere_pm = True
        membership.save()
        form = AssegnazioneForm(
            data=self._payload(self.membro, Assegnazione.Ruolo.PROJECT_MANAGER)
        )
        self.assertTrue(form.is_valid(), form.errors)
