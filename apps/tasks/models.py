from django.conf import settings
from django.db import models
from django.db.models import Q

from apps.common.models import UUIDTimeStampedModel
from apps.projects.models import Commessa


class Task(UUIDTimeStampedModel):
    class Stato(models.TextChoices):
        DA_FARE = "DA_FARE", "Da fare"
        IN_CORSO = "IN_CORSO", "In corso"
        COMPLETATA = "COMPLETATA", "Completata"

    class Priorita(models.TextChoices):
        BASSA = "BASSA", "Bassa"
        NORMALE = "NORMALE", "Normale"
        ALTA = "ALTA", "Alta"

    commessa = models.ForeignKey(
        Commessa,
        on_delete=models.PROTECT,
        related_name="tasks",
    )

    fase = models.ForeignKey(
        "phases.FaseCommessa",
        on_delete=models.PROTECT,
        related_name="tasks",
        help_text="Fase operativa obbligatoria della commessa.",
    )

    titolo = models.CharField(
        max_length=255,
    )

    descrizione = models.TextField(
        blank=True,
    )

    assegnato_a = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="tasks_assegnati",
    )

    creato_da = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="tasks_creati",
    )

    stato = models.CharField(
        max_length=20,
        choices=Stato.choices,
        default=Stato.DA_FARE,
    )

    priorita = models.CharField(
        max_length=20,
        choices=Priorita.choices,
        default=Priorita.NORMALE,
    )

    data_inizio = models.DateField(
        null=True,
        blank=True,
    )

    data_scadenza = models.DateField(
        null=True,
        blank=True,
        db_index=True,
    )

    completato_il = models.DateTimeField(
        null=True,
        blank=True,
    )

    class Meta:
        db_table = "task"
        ordering = (
            "data_scadenza",
            "-priorita",
            "titolo",
        )

        indexes = [
            models.Index(
                fields=("commessa", "stato"),
                name="idx_task_commessa_stato",
            ),
            models.Index(
                fields=("assegnato_a", "stato"),
                name="idx_task_assegnato_stato",
            ),
        ]

        constraints = [
            models.CheckConstraint(
                condition=(
                    Q(data_inizio__isnull=True)
                    | Q(data_scadenza__isnull=True)
                    | Q(data_scadenza__gte=models.F("data_inizio"))
                ),
                name="task_scadenza_non_precede_inizio",
            ),
        ]

    def save(self, *args, **kwargs):
        if self.fase_id is None:
            raise ValueError(
                "Un'attività deve appartenere a una fase."
            )
        return super().save(*args, **kwargs)

    def clean(self):
        from django.core.exceptions import ValidationError
        if self.fase_id and self.commessa_id and self.fase.commessa_id != self.commessa_id:
            raise ValidationError({"fase": "La fase non appartiene alla commessa selezionata."})
        if self.fase_id and self.assegnato_a_id:
            from apps.projects.models import Assegnazione
            if not self.assegnato_a.is_admin_lef and not Assegnazione.objects.filter(
                consulente_id=self.assegnato_a_id,
                fase_id=self.fase_id,
                stato=Assegnazione.Stato.ATTIVA,
            ).exists():
                raise ValidationError({"assegnato_a": "L'assegnatario non appartiene alla fase selezionata."})

    def __str__(self) -> str:
        return (
            f"{self.commessa.codice} - {self.fase.nome} - {self.titolo}"
        )

    @property
    def completata(self) -> bool:
        return self.stato == self.Stato.COMPLETATA

    @property
    def scaduta(self) -> bool:
        from django.utils import timezone

        return (
            self.data_scadenza is not None
            and self.data_scadenza < timezone.localdate()
            and not self.completata
        )


class TaskComment(UUIDTimeStampedModel):
    task = models.ForeignKey(
        Task,
        on_delete=models.CASCADE,
        related_name="commenti",
    )

    autore = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="commenti_task",
    )

    testo = models.TextField()

    class Meta:
        db_table = "task_comment"
        ordering = (
            "created_at",
        )

        indexes = [
            models.Index(
                fields=("task", "created_at"),
                name="idx_task_comment_data",
            ),
        ]

    def __str__(self) -> str:
        return (
            f"Commento di {self.autore} "
            f"su {self.task}"
        )