from django import forms

from apps.projects.models import Commessa

from .models import FaseCommessa
from .selectors import manageable_commesse_for_phases


class CommessaChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        return f"{obj.codice} – {obj.cliente.ragione_sociale}"


class FaseForm(forms.Form):
    commessa = CommessaChoiceField(
        queryset=Commessa.objects.none(),
        label="Commessa",
        empty_label="Seleziona una commessa",
    )

    nome = forms.CharField(
        label="Nome fase",
        max_length=255,
    )

    descrizione = forms.CharField(
        label="Descrizione (opzionale)",
        required=False,
        widget=forms.Textarea(attrs={"rows": 3}),
    )

    ordine = forms.IntegerField(
        label="Ordine",
        min_value=0,
        initial=0,
    )

    stato = forms.ChoiceField(
        label="Stato",
        choices=FaseCommessa.Stato.choices,
    )

    data_inizio = forms.DateField(
        label="Data inizio",
        required=True,
        widget=forms.DateInput(attrs={"type": "date"}),
    )

    data_fine_prevista = forms.DateField(
        label="Data fine prevista (opzionale)",
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}),
    )

    def __init__(self, *args, user=None, commessa_bloccata=None, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["commessa"].queryset = (
            manageable_commesse_for_phases(user)
            .select_related("cliente")
            .order_by("codice")
        )

        if commessa_bloccata is not None:
            self.fields["commessa"].initial = commessa_bloccata
            self.fields["commessa"].disabled = True
