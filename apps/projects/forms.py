from django import forms
from django.core.exceptions import ValidationError
from django.db.models import Max, Min, Q, Sum

from apps.accounts.models import User
from apps.phases.models import FaseCommessa

from .models import Assegnazione, Cliente, Commessa, TariffaAssegnazione
from .workflow import commessa_permette_nuovo_lavoro, fase_permette_nuovo_lavoro


class DateInput(forms.DateInput):
    input_type = "date"


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
            "codice",
            "descrizione",
            "ore_budget",
            "data_inizio",
            "data_fine_prevista",
            "note",
        )
        labels = {
            "ore_budget": "Budget complessivo ore",
            "data_inizio": "Data di inizio",
            "data_fine_prevista": "Data di fine prevista",
        }
        widgets = {
            "data_inizio": DateInput(),
            "data_fine_prevista": DateInput(),
            "note": forms.Textarea(attrs={"rows": 4}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        current_cliente_id = getattr(self.instance, "cliente_id", None)
        self.fields["cliente"].queryset = Cliente.objects.filter(
            Q(attivo=True) | Q(pk=current_cliente_id)
        ).order_by("ragione_sociale")

    def clean_codice(self):
        return self.cleaned_data["codice"].strip().upper()

    def _valida_figli_nel_nuovo_intervallo(self, inizio, fine):
        """Impedisce che una modifica della commessa invalidi dati esistenti."""
        if not self.instance.pk or not inizio:
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

    def clean(self):
        cleaned = super().clean()
        inizio = cleaned.get("data_inizio")
        fine = cleaned.get("data_fine_prevista")
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
            "data_inizio": "Data di inizio",
            "data_fine": "Data di fine",
        }
        widgets = {
            "data_inizio": DateInput(),
            "data_fine": DateInput(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
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
        ).select_related("cliente").order_by("codice")

        commessa_id = self.data.get("commessa") if self.is_bound else current_commessa_id
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
        if self.instance.pk:
            self.fields["stato"].disabled = True
            self.fields["stato"].help_text = (
                "Per concludere o riattivare l'assegnazione usa l'azione dedicata "
                "nell'elenco assegnazioni."
            )

    def _valida_integrita_storica(self, cleaned):
        if not self.instance.pk:
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
                not self.instance.pk
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
            "tipo_attivita": "Tipo di attività",
            "tariffa_oraria": "Tariffa oraria",
            "valida_dal": "Valida dal",
        }
        widgets = {
            "valida_dal": DateInput(),
            "tariffa_oraria": forms.NumberInput(
                attrs={"min": "0", "step": "0.01"}
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["assegnazione"].queryset = (
            Assegnazione.objects.select_related(
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
