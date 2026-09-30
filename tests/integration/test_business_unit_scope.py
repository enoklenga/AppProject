"""Gestione per Business Unit (revisione 29/09/2026, flusso TO-BE).

* Admin LEF: piattaforma + gestione di tutto.
* Amministrazione: gestione di tutto, senza la piattaforma.
* Responsabile BU: interfaccia di gestione limitata alla propria BU; fuori
  dal perimetro è una normale risorsa (consulente/PM).
"""
from datetime import timedelta

from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts import access
from apps.accounts.forms import ConsulenteUpdateForm, UserBusinessUnitForm
from apps.accounts.business_units import carichi_membri
from apps.accounts.models import BusinessUnit, User, UserBusinessUnit
from apps.operations.models import PeriodoMensile
from apps.phases.models import FaseCommessa
from apps.projects.forms import CommessaForm
from apps.projects.models import Assegnazione, Cliente, Commessa
from apps.timesheets.models import RigaOre, StatoApprovazione
from apps.timesheets.services import approva_riga_ore, inserisci_ore


def _utente(email, ruolo):
    return User.objects.create_user(
        email=email,
        password="Password-123!",
        ruolo=ruolo,
        is_active=True,
        deve_cambiare_password=False,
    )


class BusinessUnitScopeTests(TestCase):
    def setUp(self):
        oggi = timezone.localdate()
        self.oggi = oggi
        self.admin = _utente("admin-bu@example.com", User.Ruolo.ADMIN)
        self.amministrazione = _utente("amm-bu@example.com", User.Ruolo.AMMINISTRAZIONE)
        self.dg = _utente("dg-bu@example.com", User.Ruolo.DIREZIONE_GENERALE)
        self.rbu = _utente("rbu@example.com", User.Ruolo.RESPONSABILE_CONSULENZA)
        self.consulente = _utente("cons-bu@example.com", User.Ruolo.CONSULENTE)
        self.esterno = _utente("cons-form@example.com", User.Ruolo.CONSULENTE)

        self.consulenza = BusinessUnit.objects.create(nome="Consulenza", codice="CONS")
        self.formazione = BusinessUnit.objects.create(nome="Formazione", codice="FORM")

        UserBusinessUnit.objects.create(
            utente=self.rbu, business_unit=self.consulenza, responsabile=True, puo_essere_pm=True
        )
        UserBusinessUnit.objects.create(
            utente=self.consulente, business_unit=self.consulenza, puo_essere_pm=True
        )
        UserBusinessUnit.objects.create(utente=self.esterno, business_unit=self.formazione)

        cliente = Cliente.objects.create(ragione_sociale="Cliente BU", partita_iva="12312312312")
        self.commessa_cons = Commessa.objects.create(
            cliente=cliente,
            business_unit=self.consulenza,
            codice="CONS-001",
            descrizione="Commessa consulenza",
            data_inizio=oggi - timedelta(days=30),
            data_fine_prevista=oggi + timedelta(days=60),
            ore_budget=200,
        )
        self.commessa_form = Commessa.objects.create(
            cliente=cliente,
            business_unit=self.formazione,
            codice="FORM-001",
            descrizione="Commessa formazione",
            data_inizio=oggi - timedelta(days=30),
            data_fine_prevista=oggi + timedelta(days=60),
            ore_budget=100,
        )
        fase_cons = FaseCommessa.objects.get(commessa=self.commessa_cons, sistema=True)
        fase_form = FaseCommessa.objects.get(commessa=self.commessa_form, sistema=True)

        def assegna(utente, commessa, fase, ruolo=Assegnazione.Ruolo.CONSULENTE):
            return Assegnazione.objects.create(
                consulente=utente,
                commessa=commessa,
                fase=fase,
                ore_previste=80,
                ruolo_commessa=ruolo,
                stato=Assegnazione.Stato.ATTIVA,
                data_inizio=oggi - timedelta(days=30),
            )

        self.ass_cons = assegna(self.consulente, self.commessa_cons, fase_cons)
        self.ass_rbu = assegna(self.rbu, self.commessa_cons, fase_cons, Assegnazione.Ruolo.PROJECT_MANAGER)
        self.ass_form = assegna(self.esterno, self.commessa_form, fase_form)
        # Il Responsabile BU lavora anche come consulente in un'altra BU.
        UserBusinessUnit.objects.create(utente=self.rbu, business_unit=self.formazione)
        self.ass_rbu_form = assegna(self.rbu, self.commessa_form, fase_form)

    def _riga(self, assegnazione, attore=None):
        return inserisci_ore(
            attore=attore or assegnazione.consulente,
            assegnazione_id=assegnazione.id,
            giorno=self.oggi,
            tipo_attivita="CONSULENZA",
            ore=2,
        ).riga

    # -- Livelli ------------------------------------------------------------
    def test_livelli_di_gestione(self):
        self.assertTrue(access.is_platform_admin(self.admin))
        self.assertFalse(access.is_platform_admin(self.amministrazione))
        self.assertTrue(access.is_global_manager(self.amministrazione))
        self.assertTrue(access.is_bu_manager(self.rbu))
        self.assertEqual(access.managed_business_unit_ids(self.rbu), {self.consulenza.pk})
        self.assertFalse(access.is_manager(self.consulente))
        self.assertTrue(access.can_manage_commessa(self.rbu, self.commessa_cons))
        self.assertFalse(access.can_manage_commessa(self.rbu, self.commessa_form))

    def test_revoca_nomina_aggiorna_subito_il_perimetro(self):
        self.assertTrue(access.is_bu_manager(self.rbu))
        UserBusinessUnit.objects.filter(utente=self.rbu, business_unit=self.consulenza).update(
            responsabile=False
        )
        # update() non invia segnali: la revoca via form/admin usa save().
        membership = UserBusinessUnit.objects.get(utente=self.rbu, business_unit=self.consulenza)
        membership.save()
        self.assertFalse(access.is_bu_manager(self.rbu))

    # -- Commesse -----------------------------------------------------------
    def test_responsabile_vede_e_modifica_solo_commesse_della_bu(self):
        self.client.force_login(self.rbu)
        response = self.client.get(reverse("projects:commessa-list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "CONS-001")
        self.assertNotContains(response, "FORM-001")
        self.assertEqual(
            self.client.get(reverse("projects:commessa-update", args=[self.commessa_cons.pk])).status_code,
            200,
        )
        self.assertEqual(
            self.client.get(reverse("projects:commessa-update", args=[self.commessa_form.pk])).status_code,
            404,
        )

    def test_responsabile_crea_commesse_solo_nella_propria_bu(self):
        form = CommessaForm(user=self.rbu)
        self.assertEqual(list(form.fields["business_unit"].queryset), [self.consulenza])
        self.assertTrue(form.fields["business_unit"].required)

    def test_nuova_commessa_richiede_business_unit(self):
        form = CommessaForm(user=self.admin)
        self.assertTrue(form.fields["business_unit"].required)

    def test_teamwork_accessibile_al_responsabile_della_bu(self):
        self.client.force_login(self.rbu)
        response = self.client.get(reverse("projects:commessa-teamwork", args=[self.commessa_cons.pk]))
        self.assertEqual(response.status_code, 200)

    # -- Consuntivi e approvazioni -----------------------------------------
    def test_responsabile_approva_ore_della_bu_ma_non_di_altre_bu(self):
        riga_cons = self._riga(self.ass_cons)
        riga_form = self._riga(self.ass_form)
        approva_riga_ore(attore=self.rbu, riga_id=riga_cons.id)
        riga_cons.refresh_from_db()
        self.assertEqual(riga_cons.stato_approvazione, StatoApprovazione.APPROVATA)
        with self.assertRaises(PermissionDenied):
            approva_riga_ore(attore=self.rbu, riga_id=riga_form.id)

    def test_nessuno_approva_le_proprie_ore(self):
        riga = self._riga(self.ass_rbu)
        with self.assertRaises(PermissionDenied):
            approva_riga_ore(attore=self.rbu, riga_id=riga.id)

    def test_ore_proprie_del_responsabile_non_sono_correzioni_admin(self):
        riga = self._riga(self.ass_rbu)
        self.assertFalse(riga.bloccata_per_consulente)
        self.assertFalse(riga.modificata_da_admin)

    def test_amministrazione_approva_ovunque(self):
        riga = self._riga(self.ass_form)
        approva_riga_ore(attore=self.amministrazione, riga_id=riga.id)
        riga.refresh_from_db()
        self.assertEqual(riga.stato_approvazione, StatoApprovazione.APPROVATA)

    def test_elenco_ore_del_responsabile_limitato_alla_bu(self):
        self._riga(self.ass_cons)
        self._riga(self.ass_form)
        self.client.force_login(self.rbu)
        response = self.client.get(reverse("timesheets:ore-list"))
        self.assertEqual(response.status_code, 200)
        consulenti = {riga.assegnazione.consulente_id for riga in response.context["righe"]}
        self.assertIn(self.consulente.pk, consulenti)
        self.assertNotIn(self.esterno.pk, consulenti)

    def test_chiusura_mese_resta_aziendale(self):
        self.client.force_login(self.rbu)
        response = self.client.get(reverse("operations:periodo-detail"))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context["puo_chiudere"])
        self.client.post(
            reverse("operations:periodo-detail"),
            {
                "azione": "chiudi",
                "mese": f"{self.oggi:%Y-%m}",
                "forza_tariffe_mancanti": "on",
                "forza_approvazioni_mancanti": "on",
                "motivazione": "prova",
            },
        )
        self.assertFalse(
            PeriodoMensile.objects.filter(
                anno=self.oggi.year, mese=self.oggi.month, stato=PeriodoMensile.Stato.CHIUSO
            ).exists()
        )

    def test_consuntivi_del_mese_filtrati_per_bu(self):
        self._riga(self.ass_cons)
        self._riga(self.ass_form)
        self.client.force_login(self.rbu)
        response = self.client.get(reverse("operations:periodo-detail"))
        righe = response.context["riepilogo"].righe_valorizzate
        self.assertEqual({v.riga.assegnazione.commessa_id for v in righe}, {self.commessa_cons.pk})

    # -- Persone e appartenenze --------------------------------------------
    def test_responsabile_vede_solo_le_persone_della_bu(self):
        self.client.force_login(self.rbu)
        response = self.client.get(reverse("accounts:consulente-list"))
        self.assertEqual(response.status_code, 200)
        persone = set(response.context["consulenti"])
        self.assertIn(self.consulente, persone)
        self.assertNotIn(self.esterno, persone)
        self.assertEqual(self.client.get(reverse("accounts:consulente-create")).status_code, 403)

    def test_solo_admin_nomina_responsabili(self):
        form = UserBusinessUnitForm(user=self.rbu)
        self.assertTrue(form.fields["responsabile"].disabled)
        self.assertEqual(list(form.fields["business_unit"].queryset), [self.consulenza])
        form = UserBusinessUnitForm(user=self.amministrazione)
        self.assertTrue(form.fields["responsabile"].disabled)
        form = UserBusinessUnitForm(user=self.admin)
        self.assertFalse(form.fields["responsabile"].disabled)

    def test_responsabile_richiede_ruolo_dedicato(self):
        form = UserBusinessUnitForm(
            data={
                "utente": str(self.esterno.pk),
                "business_unit": str(self.consulenza.pk),
                "responsabile": "on",
                "attiva": "on",
            },
            user=self.admin,
        )
        self.assertFalse(form.is_valid())
        self.assertIn("responsabile", form.errors)

    def test_responsabile_aggiunge_membro_alla_propria_bu(self):
        self.client.force_login(self.rbu)
        response = self.client.post(
            reverse("accounts:user-business-unit-create"),
            {
                "utente": str(self.esterno.pk),
                "business_unit": str(self.consulenza.pk),
                "puo_essere_pm": "on",
                "attiva": "on",
                "responsabile": "on",  # ignorato: campo disabilitato
            },
        )
        self.assertEqual(response.status_code, 302)
        membership = UserBusinessUnit.objects.get(utente=self.esterno, business_unit=self.consulenza)
        self.assertTrue(membership.puo_essere_pm)
        self.assertFalse(membership.responsabile)

    # -- Pagine BU e menu ---------------------------------------------------
    def test_cruscotto_bu(self):
        self.client.force_login(self.rbu)
        response = self.client.get(reverse("accounts:business-unit-detail", args=[self.consulenza.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Aggiungi persona")
        self.assertEqual(
            self.client.get(reverse("accounts:business-unit-detail", args=[self.formazione.pk])).status_code,
            404,
        )
        self.client.force_login(self.dg)
        response = self.client.get(reverse("accounts:business-unit-detail", args=[self.formazione.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Aggiungi persona")

    def test_home_e_menu_del_responsabile(self):
        self.client.force_login(self.rbu)
        response = self.client.get(reverse("home"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "common/home_responsabile.html")
        self.assertContains(response, "La mia Business Unit")
        self.assertContains(response, "Approvazioni")
        self.assertNotContains(response, "Importazioni")

    def test_menu_consulente_senza_sezioni_di_gestione(self):
        self.client.force_login(self.consulente)
        response = self.client.get(reverse("home"))
        self.assertNotContains(response, "Organizzazione")
        self.assertNotContains(response, "Portafoglio")

    def test_home_amministrazione_usa_interfaccia_di_gestione(self):
        self.client.force_login(self.amministrazione)
        response = self.client.get(reverse("home"))
        self.assertTemplateUsed(response, "common/home_admin.html")
        self.assertContains(response, "Chiusura mese")
        self.assertNotContains(response, "Persone e ruoli")

    def test_dashboard_limitata_al_perimetro(self):
        self._riga(self.ass_cons)
        self._riga(self.ass_form)
        self.client.force_login(self.rbu)
        response = self.client.get(reverse("operations:dashboard-admin"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["dashboard"].totale_ore, 2)
        # anche chiedendo esplicitamente un'altra BU
        response = self.client.get(reverse("operations:dashboard-admin"), {"bu": str(self.formazione.pk)})
        self.assertEqual(response.context["dashboard"].totale_ore, 2)


    def test_home_responsabile_rispetta_mese_e_stato_periodo(self):
        PeriodoMensile.objects.create(
            anno=2026, mese=9, stato=PeriodoMensile.Stato.CHIUSO
        )
        self.client.force_login(self.rbu)
        settembre = self.client.get(reverse("home"), {"mese": "2026-09"})
        ottobre = self.client.get(reverse("home"), {"mese": "2026-10"})
        self.assertEqual(settembre.context["mese_selezionato"], "2026-09")
        self.assertEqual(settembre.context["periodo_stato"], "Chiuso")
        self.assertTrue(settembre.context["periodo_chiuso"])
        self.assertEqual(ottobre.context["mese_selezionato"], "2026-10")
        self.assertEqual(ottobre.context["periodo_stato"], "Aperto")
        self.assertFalse(ottobre.context["periodo_chiuso"])

    def test_return_to_preserva_cruscotto_bu_e_mese(self):
        self.client.force_login(self.rbu)
        return_to = reverse("accounts:business-unit-detail", args=[self.consulenza.pk]) + "?mese=2026-10"
        response = self.client.post(
            reverse("projects:assegnazione-create") + f"?return_to={return_to}",
            {
                "consulente": str(self.esterno.pk),
                "commessa": str(self.commessa_cons.pk),
                "fase": str(FaseCommessa.objects.get(commessa=self.commessa_cons, sistema=True).pk),
                "ore_previste": 8,
                "ruolo_commessa": Assegnazione.Ruolo.CONSULENTE,
                "stato": Assegnazione.Stato.ATTIVA,
                "data_inizio": str(self.oggi),
                "data_fine": "",
                "return_to": return_to,
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], return_to)

    def test_parametri_non_validi_non_generano_errori(self):
        self.client.force_login(self.admin)
        for url in (
            reverse("projects:commessa-list") + "?bu=abc",
            reverse("projects:commessa-create") + "?business_unit=abc",
            reverse("projects:assegnazione-create") + "?commessa=abc",
            reverse("accounts:user-business-unit-list") + "?business_unit=abc",
            reverse("operations:dashboard-admin") + "?bu=abc",
            reverse("documents:document-list") + "?commessa=abc",
        ):
            self.assertEqual(self.client.get(url).status_code, 200, url)
    def test_membership_scaduta_non_conferisce_poteri_bu(self):
        membership = UserBusinessUnit.objects.get(
            utente=self.rbu, business_unit=self.consulenza
        )
        membership.data_fine = self.oggi - timedelta(days=1)
        membership.save()
        self.assertFalse(access.is_bu_manager(self.rbu))
        self.assertNotIn(self.consulenza.pk, access.managed_business_unit_ids(self.rbu))

    def test_membership_futura_non_abilita_pm(self):
        membership = UserBusinessUnit.objects.get(
            utente=self.consulente, business_unit=self.consulenza
        )
        membership.data_inizio = self.oggi + timedelta(days=1)
        membership.save()
        self.assertFalse(access.can_be_project_manager(self.consulente, self.consulenza))

    def test_non_si_disattiva_bu_con_commesse_aperte(self):
        self.consulenza.attiva = False
        with self.assertRaises(ValidationError):
            self.consulenza.save()

    def test_cambio_bu_commessa_operativa_bloccato(self):
        form = CommessaForm(
            data={
                "cliente": str(self.commessa_cons.cliente_id),
                "business_unit": str(self.formazione.pk),
                "codice": self.commessa_cons.codice,
                "descrizione": self.commessa_cons.descrizione,
                "ore_budget": self.commessa_cons.ore_budget,
                "data_inizio": self.commessa_cons.data_inizio.isoformat(),
                "data_fine_prevista": self.commessa_cons.data_fine_prevista.isoformat(),
                "note": self.commessa_cons.note,
            },
            instance=self.commessa_cons,
            user=self.admin,
        )
        self.assertFalse(form.is_valid())
        self.assertIn("business_unit", form.errors)

    def test_home_multi_bu_deduplica_la_stessa_persona(self):
        righe = carichi_membri(
            [self.consulenza.pk, self.formazione.pk],
            self.oggi.year,
            self.oggi.month,
            deduplica_utenti=True,
        )
        righe_rbu = [r for r in righe if r["utente"].pk == self.rbu.pk]
        self.assertEqual(len(righe_rbu), 1)
        self.assertIn("Consulenza", righe_rbu[0]["business_units_label"])
        self.assertIn("Formazione", righe_rbu[0]["business_units_label"])

    def test_cambio_ruolo_responsabile_richiede_revoca_bu(self):
        form = ConsulenteUpdateForm(
            data={
                "email": self.rbu.email,
                "first_name": self.rbu.first_name,
                "last_name": self.rbu.last_name,
                "telefono": self.rbu.telefono,
                "ruolo": User.Ruolo.CONSULENTE,
                "deve_cambiare_password": "",
            },
            instance=self.rbu,
            attore=self.admin,
        )
        self.assertFalse(form.is_valid())
        self.assertIn("ruolo", form.errors)

    def test_ritorno_alla_bu_dopo_creazione_commessa(self):
        self.client.force_login(self.rbu)
        url = (
            reverse("projects:commessa-create")
            + f"?next=bu&return_bu={self.consulenza.pk}&business_unit={self.consulenza.pk}"
        )
        response = self.client.post(
            url,
            {
                "next": "bu",
                "return_bu": str(self.consulenza.pk),
                "cliente": str(self.commessa_cons.cliente_id),
                "business_unit": str(self.consulenza.pk),
                "codice": "CONS-RETURN",
                "descrizione": "Test ritorno BU",
                "ore_budget": 8,
                "data_inizio": self.oggi.isoformat(),
                "data_fine_prevista": (self.oggi + timedelta(days=10)).isoformat(),
                "note": "",
            },
        )
        self.assertRedirects(
            response,
            reverse("accounts:business-unit-detail", args=[self.consulenza.pk]),
            fetch_redirect_response=False,
        )

    def test_uuid_non_validi_su_assegnazioni_e_fasi_non_generano_500(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse("projects:assegnazione-list") + "?commessa=abc")
        self.assertEqual(response.status_code, 200)
        response = self.client.get(reverse("projects:fasi-per-commessa") + "?commessa=abc")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"fasi": []})

