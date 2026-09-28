from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q

from apps.common.models import UUIDTimeStampedModel
from apps.projects.models import Assegnazione, TariffaAssegnazione


class StatoApprovazione(models.TextChoices):
    """Stato di controllo Admin su una riga ore o una spesa, usato in
    fase di chiusura periodo per tracciare cosa è stato verificato e cosa
    è stato compilato male dal consulente (spec richiesta lato Admin)."""

    IN_ATTESA = "IN_ATTESA", "Da approvare"
    APPROVATA = "APPROVATA", "Approvata"
    RIFIUTATA = "RIFIUTATA", "Rifiutata"


class RigaOre(UUIDTimeStampedModel):
    assegnazione = models.ForeignKey(
        Assegnazione,
        on_delete=models.PROTECT,
        related_name="righe_ore",
    )
    data = models.DateField(db_index=True)
    tipo_attivita = models.CharField(
        max_length=20,
        choices=TariffaAssegnazione.TipoAttivita.choices,
    )
    ore = models.PositiveSmallIntegerField()
    nota = models.TextField(blank=True)
    inserita_da = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="righe_ore_inserite",
    )
    modificata_da_admin = models.BooleanField(default=False)
    bloccata_per_consulente = models.BooleanField(default=False)
    ultima_modifica_da = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="righe_ore_modificate",
        null=True,
        blank=True,
    )
    versione = models.PositiveIntegerField(default=1)

    stato_approvazione = models.CharField(
        max_length=20,
        choices=StatoApprovazione.choices,
        default=StatoApprovazione.IN_ATTESA,
        db_index=True,
    )
    nota_approvazione = models.TextField(blank=True)
    approvata_da = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="righe_ore_approvate",
        null=True,
        blank=True,
    )
    data_approvazione = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "riga_ore"
        ordering = ("-data", "-created_at")
        indexes = [
            models.Index(
                fields=("assegnazione", "data"),
                name="idx_ore_assegnazione_data",
            ),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(ore__gt=0),
                name="riga_ore_maggiore_zero",
            ),
        ]

    def __str__(self) -> str:
        return (
            f"{self.data} – {self.assegnazione.consulente} – "
            f"{self.ore} ore"
        )


class SpesaTrasferta(UUIDTimeStampedModel):
    class Categoria(models.TextChoices):
        VIAGGIO = "VIAGGIO", "Viaggio"
        VITTO = "VITTO", "Vitto"
        ALLOGGIO = "ALLOGGIO", "Alloggio"
        ALTRO = "ALTRO", "Altro"

    assegnazione = models.ForeignKey(
        Assegnazione,
        on_delete=models.PROTECT,
        related_name="spese_trasferta",
    )
    data = models.DateField(db_index=True)
    categoria = models.CharField(max_length=20, choices=Categoria.choices)
    importo = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    nota = models.TextField(blank=True)
    inserita_da = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="spese_inserite",
    )
    modificata_da_admin = models.BooleanField(default=False)
    bloccata_per_consulente = models.BooleanField(default=False)
    ultima_modifica_da = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="spese_modificate",
        null=True,
        blank=True,
    )
    versione = models.PositiveIntegerField(default=1)

    stato_approvazione = models.CharField(
        max_length=20,
        choices=StatoApprovazione.choices,
        default=StatoApprovazione.IN_ATTESA,
        db_index=True,
    )
    nota_approvazione = models.TextField(blank=True)
    approvata_da = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="spese_approvate",
        null=True,
        blank=True,
    )
    data_approvazione = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "spesa_trasferta"
        ordering = ("-data", "-created_at")
        indexes = [
            models.Index(
                fields=("assegnazione", "data"),
                name="idx_spesa_assegnazione_data",
            ),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(importo__gt=0),
                name="spesa_importo_maggiore_zero",
            ),
        ]

    def __str__(self) -> str:
        return (
            f"{self.data} – {self.assegnazione.consulente} – "
            f"€ {self.importo}"
        )
