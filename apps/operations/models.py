import uuid

from django.conf import settings
from django.db import models
from django.db.models import Q

from apps.common.models import UUIDTimeStampedModel


class PeriodoMensile(UUIDTimeStampedModel):
    class Stato(models.TextChoices):
        APERTO = "APERTO", "Aperto"
        CHIUSO = "CHIUSO", "Chiuso"

    anno = models.PositiveSmallIntegerField()
    mese = models.PositiveSmallIntegerField()
    stato = models.CharField(
        max_length=20,
        choices=Stato.choices,
        default=Stato.APERTO,
    )
    chiuso_da = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="periodi_chiusi",
        null=True,
        blank=True,
    )
    data_chiusura = models.DateTimeField(null=True, blank=True)
    riaperto_da = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="periodi_riaperti",
        null=True,
        blank=True,
    )
    data_riapertura = models.DateTimeField(null=True, blank=True)
    forzatura_tariffe_mancanti = models.BooleanField(default=False)
    forzatura_approvazioni_mancanti = models.BooleanField(default=False)
    motivazione_forzatura = models.TextField(blank=True)

    class Meta:
        db_table = "periodo_mensile"
        ordering = ("-anno", "-mese")
        constraints = [
            models.UniqueConstraint(
                fields=("anno", "mese"),
                name="uq_periodo_anno_mese",
            ),
            models.CheckConstraint(
                condition=Q(mese__gte=1) & Q(mese__lte=12),
                name="periodo_mese_valido",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.mese:02d}/{self.anno} – {self.get_stato_display()}"


class AuditLog(models.Model):
    id = models.BigAutoField(primary_key=True)
    utente = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="eventi_audit",
    )
    entita = models.CharField(max_length=80)
    entita_id = models.UUIDField()
    azione = models.CharField(max_length=50)
    valore_precedente = models.JSONField(null=True, blank=True)
    valore_nuovo = models.JSONField(null=True, blank=True)
    motivazione = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "audit_log"
        ordering = ("-created_at",)
        indexes = [
            models.Index(
                fields=("entita", "entita_id"),
                name="idx_audit_entita_id",
            ),
        ]


class ConfigurazionePromemoria(models.Model):
    id = models.SmallAutoField(primary_key=True)
    giorno_invio = models.PositiveSmallIntegerField(default=25)
    ora_invio = models.TimeField()
    attiva = models.BooleanField(default=True)
    solo_assenza_totale_ore = models.BooleanField(default=True)
    aggiornata_da = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="configurazioni_promemoria_aggiornate",
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "configurazione_promemoria"
        constraints = [
            models.CheckConstraint(
                condition=Q(giorno_invio__gte=1) & Q(giorno_invio__lte=28),
                name="promemoria_giorno_tra_1_e_28",
            ),
        ]


class InvioPromemoria(UUIDTimeStampedModel):
    class Stato(models.TextChoices):
        INVIATO = "INVIATO", "Inviato"
        ERRORE = "ERRORE", "Errore"

    configurazione = models.ForeignKey(
        ConfigurazionePromemoria,
        on_delete=models.PROTECT,
        related_name="invii",
    )
    consulente = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="promemoria_ricevuti",
    )
    anno = models.PositiveSmallIntegerField()
    mese = models.PositiveSmallIntegerField()
    stato = models.CharField(max_length=20, choices=Stato.choices)
    data_tentativo = models.DateTimeField()
    errore = models.TextField(blank=True)

    class Meta:
        db_table = "invio_promemoria"
        constraints = [
            models.UniqueConstraint(
                fields=("consulente", "anno", "mese"),
                name="uq_promemoria_consulente_periodo",
            ),
            models.CheckConstraint(
                condition=Q(mese__gte=1) & Q(mese__lte=12),
                name="promemoria_mese_valido",
            ),
        ]


class Importazione(UUIDTimeStampedModel):
    class Stato(models.TextChoices):
        VALIDAZIONE = "VALIDAZIONE", "In validazione"
        PRONTA = "PRONTA", "Pronta"
        COMPLETATA = "COMPLETATA", "Completata"
        ERRORE = "ERRORE", "Errore"

    avviata_da = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="importazioni_avviate",
    )
    nome_file = models.CharField(max_length=255)
    file_hash = models.CharField(max_length=128, blank=True)
    stato = models.CharField(max_length=30, choices=Stato.choices)
    righe_totali = models.PositiveIntegerField(default=0)
    righe_valide = models.PositiveIntegerField(default=0)
    righe_errore = models.PositiveIntegerField(default=0)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "importazione"


class ErroreImportazione(models.Model):
    id = models.BigAutoField(primary_key=True)
    importazione = models.ForeignKey(
        Importazione,
        on_delete=models.CASCADE,
        related_name="errori",
    )
    numero_riga = models.PositiveIntegerField()
    campo = models.CharField(max_length=100, blank=True)
    codice_errore = models.CharField(max_length=50, blank=True)
    messaggio = models.TextField()
    dati_riga = models.JSONField()

    class Meta:
        db_table = "errore_importazione"
        ordering = ("numero_riga", "id")
