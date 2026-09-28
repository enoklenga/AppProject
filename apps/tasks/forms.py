from django import forms

from apps.common.widgets import DateInput
from django.core.exceptions import ValidationError

from apps.accounts.models import User
from apps.projects.models import Assegnazione, Commessa
from apps.phases.models import FaseCommessa

from .models import Task
from .selectors import (
    assignable_users_for_phase,
    manageable_projects_for_user,
    manageable_phases_for_user,
)


class CommessaChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        return (
            f"{obj.codice} – "
            f"{obj.cliente.ragione_sociale}"
        )


class UserChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        nome = obj.get_full_name().strip()

        return nome or obj.email


class TaskForm(forms.Form):
    commessa = CommessaChoiceField(
        queryset=Commessa.objects.none(),
        label="Commessa",
        empty_label="Seleziona una commessa",
    )

    fase = forms.ModelChoiceField(
        queryset=FaseCommessa.objects.none(),
        label="Fase",
        empty_label="Seleziona una fase",
    )

    titolo = forms.CharField(
        label="Titolo",
        max_length=255,
        widget=forms.TextInput(
            attrs={
                "placeholder": "Es. Preparare report finale",
            }
        ),
    )

    descrizione = forms.CharField(
        label="Descrizione",
        required=False,
        widget=forms.Textarea(
            attrs={
                "rows": 5,
                "placeholder": "Descrivi l'attività da svolgere...",
            }
        ),
    )

    assegnato_a = UserChoiceField(
        queryset=User.objects.none(),
        label="Assegnato a",
        empty_label="Seleziona un utente",
    )

    priorita = forms.ChoiceField(
        label="Priorità",
        choices=Task.Priorita.choices,
        initial=Task.Priorita.NORMALE,
    )

    data_inizio = forms.DateField(
        label="Data inizio",
        required=False,
        widget=DateInput(),
    )

    data_scadenza = forms.DateField(
        label="Data scadenza",
        required=False,
        widget=DateInput(),
    )

    def __init__(
        self,
        *args,
        user,
        task: Task | None = None,
        commessa=None,
        **kwargs,
    ):
        super().__init__(
            *args,
            **kwargs,
        )

        self.user = user
        self.task = task

        commesse_queryset = manageable_projects_for_user(
            user
        )

        self.fields["commessa"].queryset = commesse_queryset
        fasi_queryset = manageable_phases_for_user(user)
        self.fields["fase"].queryset = fasi_queryset

        commessa_selezionata = None
        fase_selezionata = None

        # =================================================
        # MODIFICA TASK
        # =================================================

        if task is not None:
            commessa_selezionata = task.commessa
            fase_selezionata = task.fase

            # La commessa e la fase di un task esistente

            # non può essere cambiata.
            self.fields["commessa"].queryset = (
                Commessa.objects
                .select_related("cliente")
                .filter(
                    pk=task.commessa_id
                )
            )

            self.fields["commessa"].disabled = True
            self.fields["fase"].queryset = fasi_queryset.filter(commessa=task.commessa)

            self.initial["commessa"] = task.commessa_id
            self.initial["fase"] = task.fase_id

            if not self.is_bound:
                self.initial.update(
                    {
                        "titolo": task.titolo,
                        "descrizione": task.descrizione,
                        "assegnato_a": task.assegnato_a_id,
                        "priorita": task.priorita,
                        "data_inizio": task.data_inizio,
                        "data_scadenza": task.data_scadenza,
                    }
                )

        # =================================================
        # POST CREAZIONE
        # =================================================

        elif self.is_bound:
            commessa_id = self.data.get(
                "commessa"
            )

            fase_id = self.data.get("fase")
            if commessa_id:
                try:
                    commessa_selezionata = (
                        commesse_queryset
                        .filter(
                            pk=commessa_id
                        )
                        .first()
                    )
                except (
                    ValidationError,
                    ValueError,
                    TypeError,
                ):
                    commessa_selezionata = None

        # =================================================
        # COMMESSA PASSATA DALLA VIEW
        # =================================================

        elif commessa is not None:
            if commesse_queryset.filter(
                pk=commessa.pk
            ).exists():
                commessa_selezionata = commessa

                self.initial["commessa"] = (
                    commessa.pk
                )

        # =================================================
        # UNA SOLA COMMESSA DISPONIBILE
        # =================================================

        elif commesse_queryset.count() == 1:
            commessa_selezionata = (
                commesse_queryset.first()
            )

            self.initial["commessa"] = (
                commessa_selezionata.pk
            )

        # =================================================
        # ASSEGNATARI
        # =================================================

        if commessa_selezionata:
            self.fields["fase"].queryset = fasi_queryset.filter(commessa=commessa_selezionata)

        if fase_selezionata is not None:
            self.fields["fase"].initial = fase_selezionata.pk
            self.fields["assegnato_a"].queryset = assignable_users_for_phase(
                user=user, fase=fase_selezionata
            )
        elif self.is_bound:
            fase_id = self.data.get("fase")
            if fase_id:
                try:
                    fase_selezionata = fasi_queryset.filter(pk=fase_id).first()
                except (ValidationError, ValueError, TypeError):
                    fase_selezionata = None
            if fase_selezionata is not None:
                self.fields["assegnato_a"].queryset = assignable_users_for_phase(
                    user=user, fase=fase_selezionata
                )
            else:
                self.fields["assegnato_a"].queryset = User.objects.none()
        else:
            self.fields["assegnato_a"].queryset = User.objects.none()

    def clean_titolo(self):
        titolo = (
            self.cleaned_data["titolo"]
            .strip()
        )

        if not titolo:
            raise forms.ValidationError(
                "Il titolo è obbligatorio."
            )

        return titolo

    def clean_descrizione(self):
        return (
            self.cleaned_data.get(
                "descrizione"
            )
            or ""
        ).strip()

    def clean(self):
        cleaned_data = super().clean()

        commessa = cleaned_data.get(
            "commessa"
        )

        assegnato_a = cleaned_data.get("assegnato_a")
        fase = cleaned_data.get("fase")

        if commessa and fase and fase.commessa_id != commessa.id:
            self.add_error("fase", "La fase non appartiene alla commessa selezionata.")
        if not fase:
            self.add_error("fase", "La fase è obbligatoria.")

        data_inizio = cleaned_data.get(
            "data_inizio"
        )

        data_scadenza = cleaned_data.get(
            "data_scadenza"
        )

        # =================================================
        # VALIDAZIONE DATE
        # =================================================

        if (
            data_inizio
            and data_scadenza
            and data_scadenza < data_inizio
        ):
            self.add_error(
                "data_scadenza",
                (
                    "La data di scadenza "
                    "non può precedere "
                    "la data di inizio."
                ),
            )

        # =================================================
        # VALIDAZIONE ASSEGNATARIO
        # =================================================

        if commessa and assegnato_a:

            # Un utente disattivato non può
            # ricevere nuove attività.
            if not assegnato_a.is_active:
                self.add_error(
                    "assegnato_a",
                    "L'utente selezionato non è attivo.",
                )

            # Gli Admin LEF possono ricevere task
            # anche senza un'assegnazione formale
            # sulla commessa.
            elif not assegnato_a.is_admin_lef:

                assegnazione_valida = (
                    Assegnazione.objects
                    .filter(
                        consulente=assegnato_a,
                        commessa=commessa,
                        fase=fase,
                        stato=Assegnazione.Stato.ATTIVA,
                    )
                    .exists()
                )

                if not assegnazione_valida:
                    self.add_error(
                        "assegnato_a",
                        (
                            "L'utente selezionato non possiede "
                            "un'assegnazione attiva sulla fase selezionata."
                        ),
                    )

        return cleaned_data


class TaskStatusForm(forms.Form):
    stato = forms.ChoiceField(
        label="Stato",
        choices=Task.Stato.choices,
    )

    def __init__(
        self,
        *args,
        task=None,
        **kwargs,
    ):
        super().__init__(
            *args,
            **kwargs,
        )

        if (
            task is not None
            and not self.is_bound
        ):
            self.initial["stato"] = (
                task.stato
            )


class TaskCommentForm(forms.Form):
    testo = forms.CharField(
        label="Commento",
        max_length=4000,
        widget=forms.Textarea(
            attrs={
                "rows": 3,
                "placeholder": "Scrivi un commento...",
            }
        ),
    )

    def clean_testo(self):
        testo = (
            self.cleaned_data["testo"]
            .strip()
        )

        if not testo:
            raise forms.ValidationError(
                "Il commento non può essere vuoto."
            )

        return testo