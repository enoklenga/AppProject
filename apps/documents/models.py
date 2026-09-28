from django.conf import settings
from django.core.files.storage import FileSystemStorage
from django.db import models

from apps.common.models import UUIDTimeStampedModel
from apps.projects.models import Commessa
from apps.phases.models import FaseCommessa


# Storage dedicato, puntato su PRIVATE_MEDIA_ROOT (mai servito da nginx):
# ogni download passa sempre dalla view document_download, che verifica
# i permessi prima di inviare il file.
documenti_storage = FileSystemStorage(
    location=settings.PRIVATE_MEDIA_ROOT,
)


def percorso_documento(instance, filename):
    """
    Organizza i file caricati in una sottocartella per commessa, cosi'
    non si accumulano tutti insieme e non ci sono collisioni di nome tra
    commesse diverse.
    """

    return f"documenti_commesse/{instance.commessa_id}/{instance.fase_id or "generali"}/{filename}"


class DocumentoCommessa(UUIDTimeStampedModel):
    """
    Documento allegato a una commessa: contratto, obiettivi concordati,
    o altro materiale di riferimento.
    """

    class Categoria(models.TextChoices):
        CONTRATTO = "CONTRATTO", "Contratto"
        OBIETTIVO = "OBIETTIVO", "Obiettivo"
        ALTRO = "ALTRO", "Altro"

    commessa = models.ForeignKey(
        Commessa,
        on_delete=models.PROTECT,
        related_name="documenti",
    )

    fase = models.ForeignKey(
        FaseCommessa,
        on_delete=models.PROTECT,
        related_name="documenti",
        null=True,
        blank=True,
        help_text="Fase di lavoro; vuota solo per documenti generali di commessa.",
    )

    file = models.FileField(
        upload_to=percorso_documento,
        storage=documenti_storage,
        max_length=500,
    )

    privato = models.BooleanField(
        default=False,
        help_text=(
            "Se selezionato, il documento è visibile solo agli Admin LEF "
            "(es. contratti riservati): non compare né nell'elenco né nel "
            "download per PM e consulenti, anche se hanno un'assegnazione "
            "attiva sulla commessa."
        ),
    )

    nome_originale = models.CharField(
        max_length=255,
    )

    categoria = models.CharField(
        max_length=20,
        choices=Categoria.choices,
        default=Categoria.ALTRO,
    )

    descrizione = models.TextField(
        blank=True,
    )

    dimensione_byte = models.PositiveIntegerField()

    caricato_da = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="documenti_caricati",
    )

    class Meta:
        db_table = "documento_commessa"
        ordering = ("-created_at",)

        indexes = [
            models.Index(
                fields=("commessa", "categoria"),
                name="idx_documento_commessa_cat",
            ),
        ]

    def __str__(self):
        return f"{self.commessa.codice} - {self.nome_originale}"

    @property
    def dimensione_leggibile(self):
        """Dimensione in un formato leggibile (KB/MB) invece dei byte grezzi."""

        valore = self.dimensione_byte

        for unita in ("B", "KB", "MB", "GB"):
            if valore < 1024:
                return f"{valore:.0f} {unita}" if unita == "B" else f"{valore:.1f} {unita}"
            valore /= 1024

        return f"{valore:.1f} TB"

    @property
    def estensione(self):
        return self.nome_originale.rsplit(".", 1)[-1].lower() if "." in self.nome_originale else ""
