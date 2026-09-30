from django import forms

from apps.common.widgets import MonthInput

from apps.accounts.access import business_units_in_scope, perimetro_business_unit
from apps.accounts.models import BusinessUnit, User
from apps.projects.models import Cliente, Commessa
from apps.phases.models import FaseCommessa




class ReportMensileFilterForm(forms.Form):
    mese = forms.DateField(
        label="Mese",
        input_formats=["%Y-%m"],
        widget=MonthInput(format="%Y-%m"),
    )
    business_unit = forms.ModelChoiceField(
        label="Business Unit",
        required=False,
        queryset=BusinessUnit.objects.none(),
        empty_label="Tutte le Business Unit",
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

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        # Perimetro massimo dell'utente: None = tutta l'azienda.
        self.perimetro_massimo = perimetro_business_unit(user) if user is not None else None
        commesse = Commessa.objects.all()
        consulenti = User.objects.filter(
            ruolo__in=(User.Ruolo.CONSULENTE, User.Ruolo.RESPONSABILE_CONSULENZA)
        )
        if self.perimetro_massimo is not None:
            commesse = commesse.filter(business_unit_id__in=self.perimetro_massimo)
            consulenti = consulenti.filter(assegnazioni__commessa__in=commesse).distinct()
        bu_queryset = (
            business_units_in_scope(user).filter(attiva=True)
            if user is not None
            else BusinessUnit.objects.filter(attiva=True)
        )
        self.fields["business_unit"].queryset = bu_queryset.order_by("nome")
        if self.perimetro_massimo is not None:
            self.fields["business_unit"].empty_label = "Tutte le mie Business Unit"
        self.fields["cliente"].queryset = Cliente.objects.order_by(
            "ragione_sociale"
        )
        self.fields["commessa"].queryset = commesse.select_related(
            "cliente"
        ).order_by("codice")
        self.fields["fase"].queryset = FaseCommessa.objects.filter(
            commessa__in=commesse
        ).select_related("commessa").order_by("commessa__codice", "ordine", "nome")
        self.fields["consulente"].queryset = consulenti.order_by("last_name", "first_name", "email")

    def business_unit_ids(self):
        """Perimetro effettivo: BU scelta (se consentita) o perimetro massimo."""
        scelta = self.cleaned_data.get("business_unit")
        if scelta is not None:
            return (scelta.pk,)
        return self.perimetro_massimo

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
