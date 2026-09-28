from django import forms

from apps.projects.models import Commessa
from apps.phases.models import FaseCommessa

from .models import DocumentoCommessa
from .selectors import manageable_projects_for_upload


class CommessaChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        return f"{obj.codice} – {obj.cliente.ragione_sociale}"

class DocumentoUploadForm(forms.Form):
    commessa = CommessaChoiceField(
        queryset=Commessa.objects.none(),
        label="Commessa",
        empty_label="Seleziona una commessa",
    )

    fase = forms.ModelChoiceField(
        queryset=FaseCommessa.objects.none(),
        label="Fase (opzionale per documenti generali)",
        required=False,
        empty_label="Documento generale di commessa",
    )

    categoria = forms.ChoiceField(
        label="Categoria",
        choices=DocumentoCommessa.Categoria.choices,
    )

    descrizione = forms.CharField(
        label="Descrizione (opzionale)",
        required=False,
        widget=forms.Textarea(
            attrs={
                "rows": 3,
                "placeholder": "Es. Contratto firmato il 12/03, versione definitiva...",
            }
        ),
    )

    file = forms.FileField(
        label="File",
    )

    privato = forms.BooleanField(
        label="Documento privato (visibile solo agli Admin)",
        required=False,
        help_text=(
            "Usalo per contratti o materiale riservato: PM e consulenti "
            "non lo vedranno né nell'elenco né nel download, anche se "
            "hanno un'assegnazione attiva sulla commessa."
        ),
    )

    def __init__(
        self,
        *args,
        user=None,
        commessa_bloccata=None,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)

        self.user = user

        # Solo un Admin LEF può marcare un documento come privato: per
        # chiunque altro il campo non viene nemmeno mostrato nel form,
        # così non può essere valorizzato via richiesta manipolata.
        if not getattr(user, "is_admin_lef", False):
            del self.fields["privato"]

        commesse_queryset = (
            manageable_projects_for_upload(user)
            .select_related("cliente")
            .order_by("codice")
        )

        self.fields["commessa"].queryset = commesse_queryset

        # Nessuna fase finché non viene identificata la commessa.
        self.fields["fase"].queryset = FaseCommessa.objects.none()

        # Caso: arrivo dal Teamwork di una specifica commessa.
        if commessa_bloccata is not None:
            self.fields["commessa"].initial = commessa_bloccata
            self.fields["commessa"].disabled = True

            self.fields["fase"].queryset = (
                FaseCommessa.objects
                .filter(commessa=commessa_bloccata)
                .order_by("ordine", "nome")
            )

        # Caso: POST del form.
        elif self.is_bound:
            commessa_id = self.data.get("commessa")

            if commessa_id:
                self.fields["fase"].queryset = (
                    FaseCommessa.objects
                    .filter(
                        commessa_id=commessa_id,
                        commessa__in=commesse_queryset,
                    )
                    .order_by("ordine", "nome")
                )

    def clean(self):
        cleaned = super().clean()

        commessa = cleaned.get("commessa")
        fase = cleaned.get("fase")

        if (
            fase
            and commessa
            and fase.commessa_id != commessa.id
        ):
            self.add_error(
                "fase",
                "La fase non appartiene alla commessa selezionata.",
            )

        return cleaned
# La validazione fase/commessa viene eseguita nel service per coprire anche gli accessi non UI.
