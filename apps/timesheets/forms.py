from django import forms

from apps.common.widgets import DateInput
from django.db.models import Q

from apps.accounts.access import commesse_in_scope, is_manager
from apps.projects.models import Assegnazione
from .models import RigaOre, SpesaTrasferta




class ApprovazioneForm(forms.Form):
    """Usato dall'Admin per approvare o rifiutare una riga ore/spesa in
    fase di chiusura periodo. La motivazione è obbligatoria solo per il
    rifiuto (vedi validazione lato service, qui resta libera per
    permettere anche un'eventuale nota facoltativa in approvazione)."""

    motivazione = forms.CharField(
        label="Motivazione",
        required=False,
        widget=forms.Textarea(attrs={"rows": 2}),
    )


class BaseConsuntivoForm(forms.ModelForm):
    versione = forms.IntegerField(
        required=False,
        widget=forms.HiddenInput(),
    )

    def __init__(self, *args, attore, **kwargs):
        self.attore = attore
        super().__init__(*args, **kwargs)

        current_id = getattr(self.instance, "assegnazione_id", None)
        queryset = Assegnazione.objects.select_related(
            "consulente",
            "commessa",
            "commessa__cliente",
            "fase",
        ).filter(
            Q(stato=Assegnazione.Stato.ATTIVA) | Q(pk=current_id),
        )

        # Chi gestisce (Admin, Amministrazione, Resp. BU) può registrare anche
        # per le persone delle commesse nel proprio perimetro; tutti possono
        # sempre usare le proprie assegnazioni.
        if is_manager(attore):
            queryset = queryset.filter(
                Q(consulente=attore) | Q(commessa__in=commesse_in_scope(attore))
            )
        else:
            queryset = queryset.filter(consulente=attore)

        self.fields["assegnazione"].queryset = queryset.order_by(
            "commessa__codice",
            "consulente__last_name",
            "consulente__first_name",
        )
        self.fields["assegnazione"].label_from_instance = (
            lambda obj: (
                f"{obj.commessa.codice} – "
                f"{obj.fase.nome} – "
                f"{obj.commessa.cliente} – "
                f"{obj.consulente}"
            )
        )

        if self.instance and self.instance.pk:
            self.fields["versione"].initial = self.instance.versione

    def clean(self):
        cleaned = super().clean()
        assegnazione = cleaned.get("assegnazione")
        giorno = cleaned.get("data")

        if assegnazione and not self.attore.puo_gestire_commessa(assegnazione.commessa):
            if assegnazione.consulente_id != self.attore.id:
                self.add_error(
                    "assegnazione",
                    "Non puoi utilizzare l'assegnazione di un altro consulente.",
                )

        if assegnazione and giorno:
            if giorno < assegnazione.data_inizio:
                self.add_error(
                    "data",
                    "La data precede l'inizio dell'assegnazione.",
                )
            if assegnazione.data_fine and giorno > assegnazione.data_fine:
                self.add_error(
                    "data",
                    "La data supera la fine dell'assegnazione.",
                )

        return cleaned


class RigaOreForm(BaseConsuntivoForm):
    motivazione = forms.CharField(
        label="Motivazione eccezione (gestione)",
        required=False,
        widget=forms.Textarea(attrs={"rows": 2}),
        help_text="Obbligatoria solo se chi gestisce la commessa porta il totale giornaliero di un consulente oltre 8 ore.",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not is_manager(self.attore):
            self.fields.pop("motivazione", None)

    class Meta:
        model = RigaOre
        fields = (
            "assegnazione",
            "data",
            "tipo_attivita",
            "ore",
            "nota",
        )
        labels = {
            "assegnazione": "Commessa e assegnazione",
            "data": "Data attività",
            "tipo_attivita": "Tipo attività",
            "ore": "Ore intere",
            "nota": "Nota attività",
        }
        widgets = {
            "data": DateInput(),
            "ore": forms.NumberInput(attrs={"min": 1, "step": 1, "max": 24}),
            "nota": forms.Textarea(attrs={"rows": 4}),
        }

    def clean_ore(self):
        ore = self.cleaned_data["ore"]
        if ore <= 0:
            raise forms.ValidationError(
                "Le ore devono essere maggiori di zero."
            )
        return ore


class SpesaTrasfertaForm(BaseConsuntivoForm):
    class Meta:
        model = SpesaTrasferta
        fields = (
            "assegnazione",
            "data",
            "categoria",
            "importo",
            "nota",
        )
        labels = {
            "assegnazione": "Commessa e assegnazione",
            "data": "Data spesa",
            "categoria": "Categoria",
            "importo": "Importo",
            "nota": "Descrizione o giustificativo",
        }
        widgets = {
            "data": DateInput(),
            "importo": forms.NumberInput(
                attrs={"min": "0.01", "step": "0.01"}
            ),
            "nota": forms.Textarea(attrs={"rows": 4}),
        }
