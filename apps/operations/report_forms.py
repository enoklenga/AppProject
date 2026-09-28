from django import forms

from apps.common.widgets import MonthInput

from apps.accounts.models import User
from apps.projects.models import Cliente, Commessa
from apps.phases.models import FaseCommessa




class ReportMensileFilterForm(forms.Form):
    mese = forms.DateField(
        label="Mese",
        input_formats=["%Y-%m"],
        widget=MonthInput(format="%Y-%m"),
    )
    cliente = forms.ModelChoiceField(
        label="Cliente",
        required=False,
        queryset=Cliente.objects.none(),
        empty_label="Tutti i clienti",
    )
    commessa = forms.ModelChoiceField(
        label="Commessa",
        required=False,
        queryset=Commessa.objects.none(),
        empty_label="Tutte le commesse",
    )
    fase = forms.ModelChoiceField(
        label="Fase",
        required=False,
        queryset=FaseCommessa.objects.none(),
        empty_label="Tutte le fasi",
    )
    consulente = forms.ModelChoiceField(
        label="Consulente",
        required=False,
        queryset=User.objects.none(),
        empty_label="Tutti i consulenti",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["cliente"].queryset = Cliente.objects.order_by(
            "ragione_sociale"
        )
        self.fields["commessa"].queryset = Commessa.objects.select_related(
            "cliente"
        ).order_by("codice")
        self.fields["fase"].queryset = FaseCommessa.objects.select_related("commessa").order_by("commessa__codice", "ordine", "nome")
        self.fields["consulente"].queryset = User.objects.filter(
            ruolo__in=(User.Ruolo.CONSULENTE, User.Ruolo.RESPONSABILE_CONSULENZA)
        ).order_by("last_name", "first_name", "email")

    def clean(self):
        cleaned = super().clean()
        cliente = cleaned.get("cliente")
        commessa = cleaned.get("commessa")
        fase = cleaned.get("fase")

        if cliente and commessa and commessa.cliente_id != cliente.id:
            self.add_error(
                "commessa",
                "La commessa selezionata non appartiene al cliente indicato.",
            )

        if fase and commessa and fase.commessa_id != commessa.id:
            self.add_error(
                "fase",
                "La fase selezionata non appartiene alla commessa indicata.",
            )

        if fase and cliente and fase.commessa.cliente_id != cliente.id:
            self.add_error(
                "fase",
                "La fase selezionata non appartiene al cliente indicato.",
            )

        return cleaned
