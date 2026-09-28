
from django import forms

from apps.common.widgets import DateInput, MonthInput
from django.conf import settings

from .models import ConfigurazionePromemoria






class PeriodoFiltroForm(forms.Form):
    mese = forms.DateField(
        label="Mese",
        input_formats=["%Y-%m"],
        widget=MonthInput(format="%Y-%m"),
    )


class ChiusuraPeriodoForm(forms.Form):
    forza_tariffe_mancanti = forms.BooleanField(
        label="Forza la chiusura nonostante le tariffe mancanti",
        required=False,
    )
    forza_approvazioni_mancanti = forms.BooleanField(
        label="Forza la chiusura nonostante ore/spese non approvate o rifiutate",
        required=False,
    )
    motivazione = forms.CharField(
        label="Motivazione",
        required=False,
        widget=forms.Textarea(attrs={"rows": 4}),
    )

    def clean(self):
        cleaned = super().clean()
        if (
            (
                cleaned.get("forza_tariffe_mancanti")
                or cleaned.get("forza_approvazioni_mancanti")
            )
            and not cleaned.get("motivazione", "").strip()
        ):
            self.add_error(
                "motivazione",
                "La chiusura forzata richiede una motivazione.",
            )
        return cleaned


class RiaperturaPeriodoForm(forms.Form):
    motivazione = forms.CharField(
        label="Motivazione della riapertura",
        widget=forms.Textarea(attrs={"rows": 4}),
    )

    def clean_motivazione(self):
        motivazione = self.cleaned_data["motivazione"].strip()
        if not motivazione:
            raise forms.ValidationError(
                "La riapertura richiede una motivazione."
            )
        return motivazione



class TimeInput(forms.TimeInput):
    input_type = "time"


class ConfigurazionePromemoriaForm(forms.ModelForm):
    class Meta:
        model = ConfigurazionePromemoria
        fields = (
            "giorno_invio",
            "ora_invio",
            "attiva",
            "solo_assenza_totale_ore",
        )
        labels = {
            "giorno_invio": "Giorno del mese",
            "ora_invio": "Ora di invio",
            "attiva": "Automazione attiva",
            "solo_assenza_totale_ore": (
                "Invia solo in caso di assenza totale di ore"
            ),
        }
        widgets = {
            "giorno_invio": forms.NumberInput(
                attrs={"min": 1, "max": 28}
            ),
            "ora_invio": TimeInput(format="%H:%M"),
        }

    def clean_giorno_invio(self):
        giorno = self.cleaned_data["giorno_invio"]
        if not 1 <= giorno <= 28:
            raise forms.ValidationError(
                "Il giorno deve essere compreso tra 1 e 28."
            )
        return giorno


class InvioManualePromemoriaForm(forms.Form):
    mese = forms.DateField(
        label="Mese da controllare",
        input_formats=["%Y-%m"],
        widget=MonthInput(format="%Y-%m"),
    )
    conferma = forms.BooleanField(
        label="Confermo l'invio ai consulenti indicati nell'anteprima",
        required=True,
    )



class ImportazioneFileForm(forms.Form):
    TIPO_IMPORTAZIONE_CHOICES = (
        ("ORE", "Ore"),
        ("SPESE", "Spese"),
    )

    tipo_importazione = forms.ChoiceField(
        label="Tipo di dati",
        choices=TIPO_IMPORTAZIONE_CHOICES,
    )
    file = forms.FileField(
        label="File Excel o CSV",
        help_text=(
            "Formati accettati: .xlsx e .csv. "
            f"Dimensione massima {getattr(settings, 'IMPORT_MAX_UPLOAD_SIZE_MB', 5)} MB."
        ),
    )

    def clean_file(self):
        file = self.cleaned_data["file"]
        nome = file.name.lower()
        if not (nome.endswith(".xlsx") or nome.endswith(".csv")):
            raise forms.ValidationError(
                "Il file deve essere in formato .xlsx oppure .csv."
            )
        max_mb = getattr(settings, "IMPORT_MAX_UPLOAD_SIZE_MB", 5)
        if file.size > max_mb * 1024 * 1024:
            raise forms.ValidationError(
                f"Il file supera la dimensione massima di {max_mb} MB."
            )
        return file


class AuditLogFilterForm(forms.Form):
    entita = forms.CharField(
        label="Entità",
        required=False,
        widget=forms.TextInput(
            attrs={"placeholder": "Es. RigaOre o PeriodoMensile"}
        ),
    )
    azione = forms.CharField(
        label="Azione",
        required=False,
        widget=forms.TextInput(
            attrs={"placeholder": "Es. MODIFICA_ADMIN"}
        ),
    )
    utente = forms.CharField(
        label="Utente",
        required=False,
        widget=forms.TextInput(
            attrs={"placeholder": "Email, nome o cognome"}
        ),
    )
    dal = forms.DateField(
        label="Dal",
        required=False,
        widget=DateInput(),
    )
    al = forms.DateField(
        label="Al",
        required=False,
        widget=DateInput(),
    )

    def clean(self):
        cleaned = super().clean()
        dal = cleaned.get("dal")
        al = cleaned.get("al")
        if dal and al and al < dal:
            self.add_error(
                "al",
                "La data finale non può precedere la data iniziale.",
            )
        return cleaned
