from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q

from apps.common.models import UUIDTimeStampedModel
from apps.projects.models import Commessa


class FaseCommessa(UUIDTimeStampedModel):
    """
    Unità operativa di una commessa.

    Ogni commessa dispone sempre di almeno una fase: per le commesse che
    non richiedono una scomposizione operativa viene utilizzata la fase
    tecnica "Generale". Le attività operative (assegnazioni, planning,
    consuntivi, task) lavorano quindi sempre nel contesto della fase.
    """

    class Stato(models.TextChoices):
        DA_INIZIARE = "DA_INIZIARE", "Da iniziare"
        IN_CORSO = "IN_CORSO", "In corso"
        COMPLETATA = "COMPLETATA", "Completata"
        SOSPESA = "SOSPESA", "Sospesa"

    commessa = models.ForeignKey(
        Commessa,
        on_delete=models.PROTECT,
        related_name="fasi",
    )

    nome = models.CharField(
        max_length=255,
    )

    sistema = models.BooleanField(
        default=False,
        help_text="Fase tecnica creata dal sistema per le commesse senza scomposizione esplicita.",
    )

    descrizione = models.TextField(
        blank=True,
    )

    ordine = models.PositiveIntegerField(
        default=0,
    )

    stato = models.CharField(
        max_length=20,
        choices=Stato.choices,
        default=Stato.DA_INIZIARE,
    )

    data_inizio = models.DateField()

    data_fine_prevista = models.DateField(
        null=True,
        blank=True,
    )

    creata_da = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="fasi_create",
        null=True,
        blank=True,
    )

    class Meta:
        db_table = "fase_commessa"

        ordering = ("commessa", "ordine", "nome")

        constraints = [
            models.CheckConstraint(
                condition=(Q(data_fine_prevista__isnull=True) | Q(data_fine_prevista__gte=models.F("data_inizio"))),
                name="fase_fine_non_precede_inizio",
            ),
            models.UniqueConstraint(
                fields=("commessa", "nome"),
                name="uq_fase_commessa_nome",
            ),
        ]

        indexes = [
            models.Index(
                fields=("commessa", "stato"),
                name="idx_fase_commessa_stato",
            ),
        ]

    def _validate_children_interval_on_date_change(self) -> None:
        if not self.pk:
            return

        try:
            originale = FaseCommessa.objects.only(
                "data_inizio", "data_fine_prevista"
            ).get(pk=self.pk)
        except FaseCommessa.DoesNotExist:
            return

        if (
            originale.data_inizio == self.data_inizio
            and originale.data_fine_prevista == self.data_fine_prevista
        ):
            return

        inizio = self.data_inizio
        fine = self.data_fine_prevista
        assegnazioni = self.assegnazioni.all()
        if assegnazioni.filter(data_inizio__lt=inizio).exists():
            raise ValidationError(
                "La nuova data di inizio della fase escluderebbe assegnazioni esistenti."
            )
        if fine and (
            assegnazioni.filter(data_inizio__gt=fine).exists()
            or assegnazioni.filter(data_fine__gt=fine).exists()
        ):
            raise ValidationError(
                "La nuova data di fine della fase escluderebbe assegnazioni esistenti."
            )

        from apps.planning.models import GiornoPianificato
        from apps.timesheets.models import RigaOre, SpesaTrasferta

        if (
            RigaOre.objects.filter(assegnazione__fase_id=self.pk, data__lt=inizio).exists()
            or SpesaTrasferta.objects.filter(assegnazione__fase_id=self.pk, data__lt=inizio).exists()
            or GiornoPianificato.objects.filter(assegnazione__fase_id=self.pk, data__lt=inizio).exists()
            or self.tasks.filter(data_inizio__lt=inizio).exists()
            or self.tasks.filter(data_scadenza__lt=inizio).exists()
        ):
            raise ValidationError(
                "La nuova data di inizio della fase escluderebbe dati operativi già registrati."
            )
        if fine and (
            RigaOre.objects.filter(assegnazione__fase_id=self.pk, data__gt=fine).exists()
            or SpesaTrasferta.objects.filter(assegnazione__fase_id=self.pk, data__gt=fine).exists()
            or GiornoPianificato.objects.filter(assegnazione__fase_id=self.pk, data__gt=fine).exists()
            or self.tasks.filter(data_inizio__gt=fine).exists()
            or self.tasks.filter(data_scadenza__gt=fine).exists()
        ):
            raise ValidationError(
                "La nuova data di fine della fase escluderebbe dati operativi già registrati."
            )

    def save(self, *args, **kwargs):
        if self.data_inizio is None and self.commessa_id:
            self.data_inizio = self.commessa.data_inizio
        self.full_clean()
        self._validate_children_interval_on_date_change()
        return super().save(*args, **kwargs)

    def clean(self):
        super().clean()

        if not self.commessa_id:
            return

        if (
            self.data_inizio
            and self.commessa.data_inizio
            and self.data_inizio < self.commessa.data_inizio
        ):
            raise ValidationError(
                {
                    "data_inizio": (
                        "La data di inizio della fase non può precedere "
                        "la data di inizio della commessa."
                    )
                }
            )

        if (
            self.data_fine_prevista
            and self.commessa.data_fine_prevista
            and self.data_fine_prevista > self.commessa.data_fine_prevista
        ):
            raise ValidationError(
                {
                    "data_fine_prevista": (
                        "La data di fine prevista della fase non può "
                        "superare quella della commessa."
                    )
                }
            )

    def __str__(self):
        return f"{self.commessa.codice} — {self.nome}"

    @property
    def conclusa(self) -> bool:
        return self.stato == self.Stato.COMPLETATA
