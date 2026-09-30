from django import forms

from apps.common.widgets import DateInput
from django.utils import timezone

from apps.projects.models import Assegnazione, TariffaAssegnazione
from .selectors import plannable_assignments_for_user

from .models import GiornoPianificato


class AssegnazioneChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        return (
            f"{obj.commessa.codice} – {obj.fase.nome} – "
            f"{obj.consulente} "
            f"({obj.commessa.cliente.ragione_sociale})"
        )


class PianificazioneForm(forms.Form):
    assegnazione = AssegnazioneChoiceField(
        queryset=Assegnazione.objects.none(),
        label="Commessa · Fase",
        empty_label="Seleziona una commessa",
    )

    data = forms.DateField(
        label="Data",
        widget=DateInput(),
    )

    ore_pianificate = forms.IntegerField(
        label="Ore pianificate",
        min_value=1,
        max_value=8,
        widget=forms.NumberInput(
            attrs={
                "min": 1,
                "max": 8,
                "step": 1,
            }
        ),
        help_text="Inserisci un numero intero da 1 a 8.",
    )

    tipo_attivita = forms.ChoiceField(
        label="Tipo attività",
        choices=TariffaAssegnazione.TipoAttivita.choices,
        help_text="La tipologia sarà riportata automaticamente nel timesheet alla conferma della sessione.",
    )

    def __init__(
        self,
        *args,
        user,
        pianificazione: GiornoPianificato | None = None,
        commessa_id=None,
        fase_id=None,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)

        self.user = user
        self.pianificazione = pianificazione

        if pianificazione:
            queryset = (
                Assegnazione.objects
                .select_related(
                    "commessa",
                    "commessa__cliente",
                    "consulente",
                )
                .filter(
                    pk=pianificazione.assegnazione_id
                )
            )

            self.fields["assegnazione"].disabled = True

            # Necessario anche nei POST:
            # un campo disabled utilizza il valore initial.
            self.initial["assegnazione"] = (
                pianificazione.assegnazione_id
            )

            if not self.is_bound:
                self.initial.update(
                    {
                        "data": pianificazione.data,
                        "ore_pianificate": (
                            pianificazione.ore_pianificate
                        ),
                        "tipo_attivita": pianificazione.tipo_attivita,
                    }
                )

        else:
            # Un solo selector governa il perimetro: il PM vede e gestisce tutte
            # le fasi della propria commessa, il consulente resta phase-scoped.
            queryset = (
                plannable_assignments_for_user(user)
                .select_related(
                    "commessa",
                    "commessa__cliente",
                    "fase",
                    "consulente",
                )
                .filter(
                    stato=Assegnazione.Stato.ATTIVA,
                    commessa__stato="APERTA",
                )
                .exclude(
                    commessa__workflow_stato__in=("SOSPESA", "IN_CHIUSURA", "CHIUSA"),
                )
                .exclude(
                    fase__stato__in=("COMPLETATA", "SOSPESA"),
                )
            )

            if commessa_id:
                queryset = queryset.filter(commessa_id=commessa_id)

            if fase_id:
                queryset = queryset.filter(fase_id=fase_id)

            queryset = queryset.order_by(
                "commessa__cliente__ragione_sociale",
                "commessa__codice",
                "fase__ordine",
                "fase__nome",
                "consulente__last_name",
            )

            self.fields["data"].widget.attrs["min"] = (
                timezone.localdate().isoformat()
            )

        self.fields["assegnazione"].queryset = queryset