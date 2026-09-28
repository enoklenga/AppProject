from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from apps.common.models import UUIDTimeStampedModel
from apps.projects.models import Assegnazione, TariffaAssegnazione


class GiornoPianificato(UUIDTimeStampedModel):
    """Sessione giornaliera di agenda collegata a una specifica assegnazione."""

    class StatoSessione(models.TextChoices):
        PIANIFICATA = "PIANIFICATA", "Pianificata"
        CONFERMATA = "CONFERMATA", "Conclusa e confermata"
        STORICO_ALLINEATO = "STORICO_ALLINEATO", "Storico allineato al timesheet"
        STORICO_ESENTE = "STORICO_ESENTE", "Storico precedente al go-live"

    assegnazione = models.ForeignKey(
        Assegnazione,
        on_delete=models.PROTECT,
        related_name="giorni_pianificati",
    )
    data = models.DateField()
    ore_pianificate = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(8)],
    )
    tipo_attivita = models.CharField(
        max_length=20,
        choices=TariffaAssegnazione.TipoAttivita.choices,
        default=TariffaAssegnazione.TipoAttivita.CONSULENZA,
    )
    stato_sessione = models.CharField(
        max_length=20,
        choices=StatoSessione.choices,
        default=StatoSessione.PIANIFICATA,
        db_index=True,
    )
    confermata_il = models.DateTimeField(null=True, blank=True, editable=False)
    confermata_da = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="sessioni_agenda_confermate",
        null=True,
        blank=True,
        editable=False,
    )
    riga_ore_generata = models.OneToOneField(
        "timesheets.RigaOre",
        on_delete=models.PROTECT,
        related_name="sessione_agenda",
        null=True,
        blank=True,
        editable=False,
    )
    inserita_da = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="pianificazioni_inserite",
    )
    modificata_da_admin = models.BooleanField(default=False)
    ultima_modifica_da = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="pianificazioni_modificate",
        null=True,
        blank=True,
    )

    class Meta:
        db_table = "giorno_pianificato"
        ordering = (
            "data",
            "assegnazione__consulente__last_name",
            "assegnazione__commessa__codice",
        )
        constraints = [
            models.UniqueConstraint(
                fields=("assegnazione", "data"),
                name="uq_giorno_pianificato_assegnazione_data",
            ),
            models.CheckConstraint(
                condition=models.Q(ore_pianificate__gte=1, ore_pianificate__lte=8),
                name="giorno_pianificato_ore_1_8",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(
                        stato_sessione="PIANIFICATA",
                        confermata_il__isnull=True,
                        confermata_da__isnull=True,
                        riga_ore_generata__isnull=True,
                    )
                    | models.Q(
                        stato_sessione="CONFERMATA",
                        confermata_il__isnull=False,
                        confermata_da__isnull=False,
                        riga_ore_generata__isnull=False,
                    )
                    | models.Q(
                        stato_sessione="STORICO_ALLINEATO",
                        confermata_il__isnull=True,
                        confermata_da__isnull=True,
                        riga_ore_generata__isnull=False,
                    )
                    | models.Q(
                        stato_sessione="STORICO_ESENTE",
                        confermata_il__isnull=True,
                        confermata_da__isnull=True,
                        riga_ore_generata__isnull=True,
                    )
                ),
                name="giorno_pianificato_stato_coerente",
            ),
        ]
        indexes = [
            models.Index(fields=("data",), name="idx_pianificazione_data"),
            models.Index(fields=("assegnazione", "data"), name="idx_pianificazione_ass_data"),
        ]

    def __str__(self) -> str:
        return (
            f"{self.assegnazione.consulente} - "
            f"{self.assegnazione.commessa.codice} - "
            f"{self.data:%d/%m/%Y} - {self.ore_pianificate}h"
        )

    @property
    def congelata(self) -> bool:
        from django.utils import timezone
        return self.data < timezone.localdate()

    @property
    def confermata(self) -> bool:
        """Compatibilità: True quando la sessione non richiede più azioni utente."""
        return self.stato_sessione in {
            self.StatoSessione.CONFERMATA,
            self.StatoSessione.STORICO_ALLINEATO,
            self.StatoSessione.STORICO_ESENTE,
        }

    @property
    def confermata_dalla_risorsa(self) -> bool:
        return self.stato_sessione == self.StatoSessione.CONFERMATA

    @classmethod
    def stati_risolti(cls):
        return (
            cls.StatoSessione.CONFERMATA,
            cls.StatoSessione.STORICO_ALLINEATO,
            cls.StatoSessione.STORICO_ESENTE,
        )
