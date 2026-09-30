from django import forms

from apps.common.widgets import DateInput
from django.core.exceptions import ValidationError
from django.db.models import Max, Min, Q, Sum

from apps.accounts.access import (
    can_be_project_manager,
    commesse_in_scope,
    is_global_manager,
    managed_business_unit_ids,
)
from apps.accounts.models import BusinessUnit, User
from apps.phases.models import FaseCommessa

from .models import Assegnazione, Cliente, Commessa, TariffaAssegnazione
from .workflow import commessa_permette_nuovo_lavoro, fase_permette_nuovo_lavoro




class ClienteForm(forms.ModelForm):
    class Meta:
        model = Cliente
        fields = (
            "ragione_sociale",
            "partita_iva",
            "referente",
            "note",
            "attivo",
        )
        labels = {
            "ragione_sociale": "Ragione sociale",
            "partita_iva": "Partita IVA",
            "attivo": "Cliente attivo",
        }

    def clean_partita_iva(self):
        return self.cleaned_data["partita_iva"].strip().upper().replace(" ", "")


class CommessaForm(forms.ModelForm):
    class Meta:
        model = Commessa
        fields = (
            "cliente",
            "business_unit",
            "codice",
            "descrizione",
            "ore_budget",
            "data_inizio",
            "data_fine_prevista",
            "note",
        )
        labels = {
            "business_unit": "Business Unit",
            "ore_budget": "Budget complessivo ore",
            "data_inizio": "Data inizio",
            "data_fine_prevista": "Data fine prevista",
        }
        widgets = {
            "data_inizio": DateInput(),
            "data_fine_prevista": DateInput(),
            "note": forms.Textarea(attrs={"rows": 4}),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        current_cliente_id = getattr(self.instance, "cliente_id", None)
        self.fields["cliente"].queryset = Cliente.objects.filter(
            Q(attivo=True) | Q(pk=current_cliente_id)
        ).order_by("ragione_sociale")
        current_bu_id = getattr(self.instance, "business_unit_id", None)
        self.fields["business_unit"].queryset = BusinessUnit.objects.filter(
            Q(attiva=True) | Q(pk=current_bu_id)
        ).order_by("nome")
        self.fields["business_unit"].help_text = ""
        # Flusso TO-BE: ogni nuova commessa nasce dentro una Business Unit.
        # Le commesse legacy senza BU restano modificabili finché non vengono
        # classificate.
        if self.instance._state.adding and BusinessUnit.objects.filter(attiva=True).exists():
            self.fields["business_unit"].required = True
        # Il Responsabile BU crea e modifica commesse solo nelle proprie BU.
        if user is not None and not is_global_manager(user) and not getattr(user, "is_commerciale", False):
            gestite = managed_business_unit_ids(user)
            if gestite:
                self.fields["business_unit"].queryset = BusinessUnit.objects.filter(
                    pk__in=gestite
                ).order_by("nome")
                self.fields["business_unit"].required = True
                self.fields["business_unit"].empty_label = None

    def clean_codice(self):
        return self.cleaned_data["codice"].strip().upper()

    def _valida_figli_nel_nuovo_intervallo(self, inizio, fine):
        """Impedisce che una modifica della commessa invalidi dati esistenti."""
        # L'id UUID esiste già prima del salvataggio: per distinguere una
        # creazione si usa _state.adding.
        if self.instance._state.adding or not inizio:
            return

        commessa_id = self.instance.pk

        # La fase tecnica Generale viene riallineata automaticamente dopo il
        # salvataggio. Le fasi esplicite, invece, devono già rientrare.
        fasi = FaseCommessa.objects.filter(
            commessa_id=commessa_id,
            sistema=False,
        )
        if fasi.filter(data_inizio__lt=inizio).exists():
            self.add_error(
                "data_inizio",
                "Esistono fasi che iniziano prima della nuova data della commessa.",
            )
        if fine and (
            fasi.filter(data_inizio__gt=fine).exists()
            or fasi.filter(data_fine_prevista__gt=fine).exists()
        ):
            self.add_error(
                "data_fine_prevista",
                "Esistono fasi che terminano o iniziano oltre la nuova fine prevista.",
            )

        assegnazioni = Assegnazione.objects.filter(commessa_id=commessa_id)
        if assegnazioni.filter(data_inizio__lt=inizio).exists():
            self.add_error(
                "data_inizio",
                "Esistono assegnazioni che iniziano prima della nuova data della commessa.",
            )
        if fine and (
            assegnazioni.filter(data_inizio__gt=fine).exists()
            or assegnazioni.filter(data_fine__gt=fine).exists()
        ):
            self.add_error(
                "data_fine_prevista",
                "Esistono assegnazioni fuori dal nuovo intervallo della commessa.",
            )

        # I dati consuntivi/planning sono storici: non possono essere spinti
        # fuori dal perimetro semplicemente restringendo la commessa.
        from apps.planning.models import GiornoPianificato
        from apps.tasks.models import Task
        from apps.timesheets.models import RigaOre, SpesaTrasferta

        if (
            RigaOre.objects.filter(
                assegnazione__commessa_id=commessa_id,
                data__lt=inizio,
            ).exists()
            or SpesaTrasferta.objects.filter(
                assegnazione__commessa_id=commessa_id,
                data__lt=inizio,
            ).exists()
            or GiornoPianificato.objects.filter(
                assegnazione__commessa_id=commessa_id,
                data__lt=inizio,
            ).exists()
            or Task.objects.filter(
                commessa_id=commessa_id,
                data_inizio__lt=inizio,
            ).exists()
            or Task.objects.filter(
                commessa_id=commessa_id,
                data_scadenza__lt=inizio,
            ).exists()
        ):
            self.add_error(
                "data_inizio",
                "Esistono dati operativi precedenti alla nuova data di inizio.",
            )

        if fine and (
            RigaOre.objects.filter(
                assegnazione__commessa_id=commessa_id,
                data__gt=fine,
            ).exists()
            or SpesaTrasferta.objects.filter(
                assegnazione__commessa_id=commessa_id,
                data__gt=fine,
            ).exists()
            or GiornoPianificato.objects.filter(
                assegnazione__commessa_id=commessa_id,
                data__gt=fine,
            ).exists()
            or Task.objects.filter(
                commessa_id=commessa_id,
                data_inizio__gt=fine,
            ).exists()
            or Task.objects.filter(
                commessa_id=commessa_id,
                data_scadenza__gt=fine,
            ).exists()
        ):
            self.add_error(
                "data_fine_prevista",
                "Esistono dati operativi successivi alla nuova fine prevista.",
            )

    def _valida_cambio_business_unit(self, nuova_bu):
        """Blocca trasferimenti impliciti di commesse gia operative.

        La prima classificazione di una commessa legacy (BU None -> BU) resta
        consentita. Un vero cambio da una BU a un'altra, o la rimozione della
        BU, richiede invece un futuro workflow esplicito di trasferimento.
        """
        if self.instance._state.adding:
            return
        originale = Commessa.objects.filter(pk=self.instance.pk).values(
            "business_unit_id", "handover_completato"
        ).first()
        if not originale:
            return
        vecchia_bu_id = originale["business_unit_id"]
        nuova_bu_id = getattr(nuova_bu, "pk", None)
        if not vecchia_bu_id or vecchia_bu_id == nuova_bu_id:
            return

        from apps.planning.models import GiornoPianificato
        from apps.tasks.models import Task
        from apps.timesheets.models import RigaOre, SpesaTrasferta

        ha_storia = (
            originale["handover_completato"]
            or FaseCommessa.objects.filter(commessa_id=self.instance.pk, sistema=False).exists()
            or Assegnazione.objects.filter(commessa_id=self.instance.pk).exists()
            or GiornoPianificato.objects.filter(assegnazione__commessa_id=self.instance.pk).exists()
            or RigaOre.objects.filter(assegnazione__commessa_id=self.instance.pk).exists()
            or SpesaTrasferta.objects.filter(assegnazione__commessa_id=self.instance.pk).exists()
            or Task.objects.filter(commessa_id=self.instance.pk).exists()
        )
        if ha_storia:
            self.add_error(
                "business_unit",
                "La Business Unit non può essere cambiata su una commessa già operativa. "
                "Chiudi/riclassifica il lavoro con una procedura di trasferimento dedicata.",
            )

    def clean(self):
        cleaned = super().clean()
        inizio = cleaned.get("data_inizio")
        fine = cleaned.get("data_fine_prevista")
        self._valida_cambio_business_unit(cleaned.get("business_unit"))
        if inizio and fine and fine < inizio:
            self.add_error(
                "data_fine_prevista",
                "La data di fine non può precedere la data di inizio.",
            )
        if inizio:
            self._valida_figli_nel_nuovo_intervallo(inizio, fine)
        return cleaned


class HandoverCommessaForm(forms.ModelForm):
    """Presa in carico PM: V1 volutamente leggera, senza checklist applicativa."""

    class Meta:
        model = Commessa
        fields = (
            "handover_note",
            "handover_completato",
        )
        labels = {
            "handover_note": "Note handover commerciale",
            "handover_completato": "Handover verificato e preso in carico",
        }
        widgets = {
            "handover_note": forms.Textarea(attrs={"rows": 6}),
        }



class WorkflowCommessaForm(forms.Form):
    workflow_stato = forms.ChoiceField(
        label="Stato workflow",
        choices=[
            choice
            for choice in Commessa.WorkflowStato.choices
            if choice[0] != Commessa.WorkflowStato.CHIUSA
        ],
    )
    motivazione = forms.CharField(
        label="Motivazione",
        required=True,
        widget=forms.Textarea(attrs={"rows": 4}),
        help_text="Obbligatoria: ogni transizione viene registrata nell'audit.",
    )

    def clean_motivazione(self):
        valore = self.cleaned_data["motivazione"].strip()
        if not valore:
            raise forms.ValidationError("Indica la motivazione del cambio workflow.")
        return valore


class AssegnazioneForm(forms.ModelForm):
    class Meta:
        model = Assegnazione
        fields = (
            "consulente",
            "commessa",
            "fase",
            "ore_previste",
            "ruolo_commessa",
            "stato",
            "data_inizio",
            "data_fine",
        )
        labels = {
            "ore_previste": "Ore previste per il consulente",
            "ruolo_commessa": "Ruolo sulla commessa",
            "data_inizio": "Data inizio",
            "data_fine": "Data fine",
        }
        widgets = {
            "data_inizio": DateInput(),
            "data_fine": DateInput(),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        current_consulente_id = getattr(self.instance, "consulente_id", None)
        current_commessa_id = getattr(self.instance, "commessa_id", None)
        current_fase_id = getattr(self.instance, "fase_id", None)
        self.fields["consulente"].queryset = User.objects.filter(
            ruolo__in=(
                User.Ruolo.CONSULENTE,
                User.Ruolo.RESPONSABILE_CONSULENZA,
            ),
        ).filter(
            Q(is_active=True) | Q(pk=current_consulente_id)
        ).order_by("last_name", "first_name", "email")
        self.fields["commessa"].queryset = Commessa.objects.filter(
            Q(stato=Commessa.Stato.APERTA) | Q(pk=current_commessa_id)
        ).select_related("cliente", "business_unit").order_by("codice")
        if user is not None:
            # Perimetro di gestione: tutte (Admin/Amministrazione) o solo BU gestite.
            self.fields["commessa"].queryset = self.fields["commessa"].queryset.filter(
                pk__in=commesse_in_scope(user).values("pk")
            )

        commessa_id = self.data.get("commessa") if self.is_bound else current_commessa_id
        commessa_selezionata = None
        if commessa_id:
            commessa_selezionata = (
                Commessa.objects.filter(pk=commessa_id)
                .select_related("business_unit")
                .first()
            )

        # Il team di commessa è operativo e può essere cross-BU: una persona può
        # contribuire a una commessa anche se la sua BU principale è diversa.
        # La BU owner governa invece ownership, permessi e abilitazione del PM.
        self.fields["consulente"].help_text = (
            "Il team può includere risorse di altre Business Unit. "
            "Solo il Project Manager deve essere abilitato nella Business Unit owner della commessa."
        )
        if commessa_id:
            self.fields["fase"].queryset = FaseCommessa.objects.filter(
                commessa_id=commessa_id
            ).order_by("ordine", "nome")
        else:
            self.fields["fase"].queryset = FaseCommessa.objects.none()
        if current_fase_id:
            self.fields["fase"].initial = current_fase_id

        # Dopo la creazione lo stato cambia esclusivamente tramite il workflow
        # dedicato (conclusione/riattivazione), che applica lock, validazioni e audit.
        if not self.instance._state.adding:
            self.fields["stato"].disabled = True
            self.fields["stato"].help_text = (
                "Per concludere o riattivare l'assegnazione usa l'azione dedicata "
                "nell'elenco assegnazioni."
            )

    def _valida_integrita_storica(self, cleaned):
        if self.instance._state.adding:
            return

        originale = Assegnazione.objects.filter(pk=self.instance.pk).first()
        if originale is None:
            return

        ha_storia = (
            originale.righe_ore.exists()
            or originale.spese_trasferta.exists()
            or originale.giorni_pianificati.exists()
            or originale.tariffe.exists()
        )

        if ha_storia:
            for campo, etichetta in (
                ("consulente", "consulente"),
                ("commessa", "commessa"),
                ("fase", "fase"),
            ):
                nuovo = cleaned.get(campo)
                vecchio_id = getattr(originale, f"{campo}_id")
                nuovo_id = getattr(nuovo, "pk", None)
                if nuovo_id and nuovo_id != vecchio_id:
                    self.add_error(
                        campo,
                        f"Non puoi cambiare {etichetta}: l'assegnazione contiene dati storici. "
                        "Concludi questa assegnazione e creane una nuova.",
                    )

        # Le date possono essere corrette solo finché continuano a contenere
        # tutti i record storici già associati all'assegnazione.
        date_min = []
        date_max = []
        for manager, campo_data in (
            (originale.righe_ore, "data"),
            (originale.spese_trasferta, "data"),
            (originale.giorni_pianificati, "data"),
            (originale.tariffe, "valida_dal"),
        ):
            estremi = manager.aggregate(
                minimo=Min(campo_data),
                massimo=Max(campo_data),
            )
            if estremi["minimo"]:
                date_min.append(estremi["minimo"])
            if estremi["massimo"]:
                date_max.append(estremi["massimo"])

        inizio = cleaned.get("data_inizio")
        fine = cleaned.get("data_fine")
        if inizio and date_min and inizio > min(date_min):
            self.add_error(
                "data_inizio",
                "La nuova data di inizio escluderebbe dati storici già registrati.",
            )
        if fine and date_max and fine < max(date_max):
            self.add_error(
                "data_fine",
                "La nuova data di fine escluderebbe dati storici già registrati.",
            )

        ore_previste = cleaned.get("ore_previste")
        if ore_previste is not None:
            pianificate = (
                originale.giorni_pianificati.aggregate(
                    totale=Sum("ore_pianificate")
                )["totale"]
                or 0
            )
            if ore_previste < pianificate:
                self.add_error(
                    "ore_previste",
                    f"Le ore previste non possono scendere sotto le {pianificate} ore già pianificate.",
                )

    def clean(self):
        cleaned = super().clean()
        consulente = cleaned.get("consulente")
        commessa = cleaned.get("commessa")
        fase = cleaned.get("fase")
        stato = cleaned.get("stato")
        inizio = cleaned.get("data_inizio")
        fine = cleaned.get("data_fine")

        if not fase:
            self.add_error("fase", "La fase è obbligatoria.")
        elif commessa and fase.commessa_id != commessa.id:
            self.add_error("fase", "La fase non appartiene alla commessa selezionata.")

        ruolo_commessa = cleaned.get("ruolo_commessa")
        if (
            commessa
            and consulente
            and ruolo_commessa == Assegnazione.Ruolo.PROJECT_MANAGER
            and not can_be_project_manager(consulente, commessa.business_unit)
        ):
            self.add_error(
                "ruolo_commessa",
                "La risorsa non è abilitata come Project Manager nella Business Unit owner della commessa.",
            )

        if commessa and inizio and inizio < commessa.data_inizio:
            self.add_error(
                "data_inizio",
                "L'assegnazione non può iniziare prima della commessa.",
            )
        if commessa and inizio and commessa.data_fine_prevista and inizio > commessa.data_fine_prevista:
            self.add_error(
                "data_inizio",
                "L'assegnazione non può iniziare dopo la fine prevista della commessa.",
            )
        if commessa and fine and commessa.data_fine_prevista and fine > commessa.data_fine_prevista:
            self.add_error(
                "data_fine",
                "L'assegnazione non può terminare dopo la commessa.",
            )
        if fase and inizio and inizio < fase.data_inizio:
            self.add_error("data_inizio", "L'assegnazione non può iniziare prima della fase.")
        if fase and inizio and fase.data_fine_prevista and inizio > fase.data_fine_prevista:
            self.add_error("data_inizio", "L'assegnazione non può iniziare dopo la fine prevista della fase.")
        if fase and fine and fase.data_fine_prevista and fine > fase.data_fine_prevista:
            self.add_error("data_fine", "L'assegnazione non può terminare dopo la fase.")
        if inizio and fine and fine < inizio:
            self.add_error("data_fine", "La data di fine non può precedere la data di inizio.")

        if stato == Assegnazione.Stato.ATTIVA:
            deve_verificare_ingaggiabilita = (
                self.instance._state.adding
                or "consulente" in self.changed_data
                or "data_inizio" in self.changed_data
            )
            if (
                deve_verificare_ingaggiabilita
                and consulente
                and inizio
                and not consulente.is_risorsa_ingaggiabile_in_data(inizio)
            ):
                self.add_error(
                    "consulente",
                    "La risorsa non è ingaggiabile nella data di inizio: agenda giornaliera già completa o ruolo non operativo.",
                )
            if consulente and not consulente.is_active:
                self.add_error("consulente", "Un consulente disattivato non può avere una nuova assegnazione attiva.")
            if commessa and not commessa_permette_nuovo_lavoro(commessa):
                self.add_error(
                    "commessa",
                    "La commessa non può ricevere nuove assegnazioni nello stato workflow corrente.",
                )
            if fase and not fase_permette_nuovo_lavoro(fase):
                self.add_error(
                    "fase",
                    "Una fase completata o sospesa non può ricevere un'assegnazione attiva.",
                )
            if consulente and fase:
                duplicata = Assegnazione.objects.filter(
                    consulente=consulente,
                    fase=fase,
                    stato=Assegnazione.Stato.ATTIVA,
                ).exclude(pk=self.instance.pk)
                if duplicata.exists():
                    raise forms.ValidationError(
                        "Esiste già un'assegnazione attiva per questo consulente e questa fase."
                    )

        self._valida_integrita_storica(cleaned)
        return cleaned


class TariffaAssegnazioneForm(forms.ModelForm):
    class Meta:
        model = TariffaAssegnazione
        fields = (
            "assegnazione",
            "tipo_attivita",
            "tariffa_oraria",
            "valida_dal",
        )
        labels = {
            "assegnazione": "Assegnazione",
            "tipo_attivita": "Tipo attività",
            "tariffa_oraria": "Tariffa oraria",
            "valida_dal": "Valida dal",
        }
        widgets = {
            "valida_dal": DateInput(),
            "tariffa_oraria": forms.NumberInput(
                attrs={"min": "0", "step": "0.01"}
            ),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        assegnazioni = Assegnazione.objects.all()
        if user is not None:
            assegnazioni = assegnazioni.filter(commessa__in=commesse_in_scope(user))
        self.fields["assegnazione"].queryset = (
            assegnazioni.select_related(
                "consulente",
                "commessa",
                "commessa__cliente",
                "fase",
            )
            .order_by(
                "commessa__codice",
                "fase__ordine",
                "consulente__last_name",
                "consulente__first_name",
            )
        )
        self.fields["assegnazione"].label_from_instance = (
            lambda obj: (
                f"{obj.commessa.codice} – "
                f"{obj.fase.nome} – "
                f"{obj.consulente} – "
                f"{obj.commessa.cliente}"
            )
        )

    def _valida_periodi_chiusi(self, assegnazione, tipo_attivita, valida_dal):
        from .services import verifica_tariffa_periodi_aperti

        try:
            verifica_tariffa_periodi_aperti(
                assegnazione=assegnazione,
                tipo_attivita=tipo_attivita,
                valida_dal=valida_dal,
                lock=False,
            )
        except ValidationError as exc:
            self.add_error("valida_dal", "; ".join(exc.messages))

    def clean(self):
        cleaned = super().clean()
        assegnazione = cleaned.get("assegnazione")
        tipo_attivita = cleaned.get("tipo_attivita")
        valida_dal = cleaned.get("valida_dal")

        if assegnazione and valida_dal:
            if valida_dal < assegnazione.data_inizio:
                self.add_error(
                    "valida_dal",
                    "La tariffa non può iniziare prima dell'assegnazione.",
                )
            if assegnazione.data_fine and valida_dal > assegnazione.data_fine:
                self.add_error(
                    "valida_dal",
                    "La tariffa non può iniziare dopo la fine dell'assegnazione.",
                )

        if assegnazione and tipo_attivita and valida_dal:
            duplicata = TariffaAssegnazione.objects.filter(
                assegnazione=assegnazione,
                tipo_attivita=tipo_attivita,
                valida_dal=valida_dal,
            ).exists()
            if duplicata:
                raise forms.ValidationError(
                    "Esiste già una tariffa per questa assegnazione, "
                    "attività e data di decorrenza."
                )
            self._valida_periodi_chiusi(
                assegnazione,
                tipo_attivita,
                valida_dal,
            )
        return cleaned
