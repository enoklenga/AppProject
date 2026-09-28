from django.conf import settings
from django.db import models


from django.utils import timezone

from apps.common.models import UUIDTimeStampedModel
from apps.tasks.models import Task


class Notification(UUIDTimeStampedModel):

    class Tipo(models.TextChoices):
        TASK_ASSIGNED = (
            "TASK_ASSIGNED",
            "Nuova attività assegnata",
        )

        TASK_COMMENTED = (
            "TASK_COMMENTED",
            "Nuovo commento",
        )

        TASK_DUE_SOON = (
            "TASK_DUE_SOON",
            "Attività in scadenza",
        )

        TASK_OVERDUE = (
            "TASK_OVERDUE",
            "Attività scaduta",
        )

        TASK_CREATED = (
            "TASK_CREATED",
            "Nuova attività creata",
        )

        TASK_UPDATED = (
            "TASK_UPDATED",
            "Attività modificata",
        )

        TASK_REASSIGNED = (
            "TASK_REASSIGNED",
            "Attività riassegnata",
        )

        TASK_STATUS_CHANGED = (
            "TASK_STATUS_CHANGED",
            "Cambio stato attività",
        )

        TASK_DELETED = (
            "TASK_DELETED",
            "Attività eliminata",
        )

        PIANIFICAZIONE_CREATA = (
            "PIANIFICAZIONE_CREATA",
            "Nuova pianificazione",
        )

        PIANIFICAZIONE_AGGIORNATA = (
            "PIANIFICAZIONE_AGGIORNATA",
            "Pianificazione modificata",
        )

        FASE_CREATA = (
            "FASE_CREATA",
            "Nuova fase",
        )

        FASE_AGGIORNATA = (
            "FASE_AGGIORNATA",
            "Fase aggiornata",
        )

        DOCUMENTO_CARICATO = (
            "DOCUMENTO_CARICATO",
            "Nuovo documento",
        )

        DOCUMENTO_ELIMINATO = (
            "DOCUMENTO_ELIMINATO",
            "Documento eliminato",
        )

    destinatario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notifiche",
    )

    attore = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="notifiche_generate",
        null=True,
        blank=True,
    )

    task = models.ForeignKey(
        Task,
        on_delete=models.SET_NULL,
        related_name="notifiche",
        null=True,
        blank=True,
    )

    pianificazione = models.ForeignKey(
        "planning.GiornoPianificato",
        on_delete=models.SET_NULL,
        related_name="notifiche",
        null=True,
        blank=True,
    )

    fase = models.ForeignKey(
        "phases.FaseCommessa",
        on_delete=models.SET_NULL,
        related_name="notifiche",
        null=True,
        blank=True,
    )

    documento = models.ForeignKey(
        "documents.DocumentoCommessa",
        on_delete=models.SET_NULL,
        related_name="notifiche",
        null=True,
        blank=True,
    )

    tipo = models.CharField(
        max_length=30,
        choices=Tipo.choices,
        db_index=True,
    )

    titolo = models.CharField(
        max_length=255,
    )

    messaggio = models.TextField(
        blank=True,
    )

    letta_il = models.DateTimeField(
        null=True,
        blank=True,
        db_index=True,
    )

    data_riferimento = models.DateField(
        null=True,
        blank=True,
    )

    chiave_evento = models.CharField(
        max_length=255,
        unique=True,
        null=True,
        blank=True,
    )

    class Meta:
        db_table = "notification"

        ordering = (
            "-created_at",
        )

        indexes = [
            models.Index(
                fields=(
                    "destinatario",
                    "letta_il",
                ),
                name="idx_notification_user_read",
            ),
            models.Index(
                fields=(
                    "task",
                    "tipo",
                ),
                name="idx_notification_task_type",
            ),
        ]

    def __str__(self):
        return (
            f"{self.destinatario} - "
            f"{self.get_tipo_display()}"
        )

    @property
    def commessa(self):
        for oggetto in (self.task, self.pianificazione, self.fase, self.documento):
            if oggetto is not None:
                return oggetto.commessa if hasattr(oggetto, "commessa") else oggetto.assegnazione.commessa
        return None

    @property
    def letta(self):
        return self.letta_il is not None

    def segna_come_letta(self):
        if self.letta_il is None:
            self.letta_il = timezone.now()

            self.save(
                update_fields=[
                    "letta_il",
                    "updated_at",
                ]
            )


class NotificationPreference(UUIDTimeStampedModel):
    """
    Preferenze personali sulle notifiche.

    Ogni utente possiede una sola configurazione.
    """

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notification_preferences",
    )

    task_assigned = models.BooleanField(
        default=True,
        verbose_name="Nuove attività assegnate",
    )

    task_commented = models.BooleanField(
        default=True,
        verbose_name="Commenti sulle attività",
    )

    task_due_soon = models.BooleanField(
        default=True,
        verbose_name="Attività in scadenza",
    )

    task_overdue = models.BooleanField(
        default=True,
        verbose_name="Attività scadute",
    )

    task_creato = models.BooleanField(
        default=True,
        verbose_name="Nuove attività create sulle mie commesse",
    )

    task_modificato = models.BooleanField(
        default=True,
        verbose_name="Attività modificate",
    )

    task_riassegnato = models.BooleanField(
        default=True,
        verbose_name="Attività riassegnate",
    )

    task_cambio_stato = models.BooleanField(
        default=True,
        verbose_name="Cambio stato di un'attività",
    )

    task_eliminato = models.BooleanField(
        default=True,
        verbose_name="Attività eliminate",
    )

    pianificazione_creata = models.BooleanField(
        default=True,
        verbose_name="Nuova pianificazione di un collega",
    )

    pianificazione_aggiornata = models.BooleanField(
        default=True,
        verbose_name="Pianificazione modificata o eliminata",
    )

    fase_creata = models.BooleanField(
        default=True,
        verbose_name="Nuova fase di commessa",
    )

    fase_aggiornata = models.BooleanField(
        default=True,
        verbose_name="Fase modificata o eliminata",
    )

    documento_caricato = models.BooleanField(
        default=True,
        verbose_name="Nuovo documento caricato",
    )

    documento_eliminato = models.BooleanField(
        default=True,
        verbose_name="Documento eliminato",
    )

    class Meta:
        db_table = "notification_preference"

    def __str__(self):
        return (
            f"Preferenze notifiche - "
            f"{self.user}"
        )