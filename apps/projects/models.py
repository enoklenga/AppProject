from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q

from apps.common.models import UUIDTimeStampedModel


class Cliente(UUIDTimeStampedModel):
    ragione_sociale = models.CharField(max_length=255)
    partita_iva = models.CharField(max_length=20, unique=True)
    referente = models.CharField(max_length=255, blank=True)
    note = models.TextField(blank=True)
    attivo = models.BooleanField(default=True)

    class Meta:
        db_table = "cliente"
        ordering = ("ragione_sociale",)

    def __str__(self) -> str:
        return self.ragione_sociale


class Commessa(UUIDTimeStampedModel):
    class Stato(models.TextChoices):
        # Stato tecnico: mantiene compatibilità con i moduli operativi esistenti.
        APERTA = "APERTA", "Aperta"
        CHIUSA = "CHIUSA", "Chiusa"

    class WorkflowStato(models.TextChoices):
        DA_PRENDERE_IN_CARICO = "DA_PRENDERE_IN_CARICO", "Da prendere in carico"
        HANDOVER = "HANDOVER", "Handover commerciale"
        PIANIFICAZIONE = "PIANIFICAZIONE", "Pianificazione"
        IN_ESECUZIONE = "IN_ESECUZIONE", "In esecuzione"
        IN_CHIUSURA = "IN_CHIUSURA", "In chiusura"
        SOSPESA = "SOSPESA", "Sospesa"
        CHIUSA = "CHIUSA", "Chiusa"

    cliente = models.ForeignKey(
        Cliente,
        on_delete=models.PROTECT,
        related_name="commesse",
    )
    codice = models.CharField(max_length=80, unique=True)
    descrizione = models.TextField()
    ore_budget = models.PositiveIntegerField(null=True, blank=True)
    data_inizio = models.DateField()
    data_fine_prevista = models.DateField(null=True, blank=True)
    stato = models.CharField(
        max_length=20,
        choices=Stato.choices,
        default=Stato.APERTA,
        help_text="Stato tecnico usato per bloccare/sbloccare l'operatività.",
    )
    workflow_stato = models.CharField(
        max_length=30,
        choices=WorkflowStato.choices,
        default=WorkflowStato.DA_PRENDERE_IN_CARICO,
    )
    handover_note = models.TextField(blank=True)
    handover_completato = models.BooleanField(default=False)
    handover_completato_il = models.DateTimeField(null=True, blank=True, editable=False)
    handover_completato_da = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="handover_commesse_completati",
        null=True,
        blank=True,
        editable=False,
    )
    note = models.TextField(blank=True)

    class Meta:
        db_table = "commessa"
        ordering = ("-data_inizio", "codice")
        constraints = [
            models.CheckConstraint(
                condition=(
                    Q(data_fine_prevista__isnull=True)
                    | Q(data_fine_prevista__gte=models.F("data_inizio"))
                ),
                name="commessa_fine_non_precede_inizio",
            ),
        ]

    def _validate_children_interval_on_date_change(self) -> None:
        if not self.pk:
            return

        try:
            originale = Commessa.objects.only(
                "data_inizio", "data_fine_prevista"
            ).get(pk=self.pk)
        except Commessa.DoesNotExist:
            return

        if (
            originale.data_inizio == self.data_inizio
            and originale.data_fine_prevista == self.data_fine_prevista
        ):
            return

        from django.core.exceptions import ValidationError
        from apps.phases.models import FaseCommessa
        from apps.planning.models import GiornoPianificato
        from apps.tasks.models import Task
        from apps.timesheets.models import RigaOre, SpesaTrasferta

        inizio = self.data_inizio
        fine = self.data_fine_prevista
        fasi = FaseCommessa.objects.filter(commessa_id=self.pk, sistema=False)
        assegnazioni = Assegnazione.objects.filter(commessa_id=self.pk)

        if fasi.filter(data_inizio__lt=inizio).exists() or assegnazioni.filter(
            data_inizio__lt=inizio
        ).exists():
            raise ValidationError(
                "La nuova data di inizio della commessa escluderebbe fasi o assegnazioni esistenti."
            )

        if fine and (
            fasi.filter(data_inizio__gt=fine).exists()
            or fasi.filter(data_fine_prevista__gt=fine).exists()
            or assegnazioni.filter(data_inizio__gt=fine).exists()
            or assegnazioni.filter(data_fine__gt=fine).exists()
        ):
            raise ValidationError(
                "La nuova data di fine della commessa escluderebbe fasi o assegnazioni esistenti."
            )

        prima = (
            RigaOre.objects.filter(assegnazione__commessa_id=self.pk, data__lt=inizio).exists()
            or SpesaTrasferta.objects.filter(assegnazione__commessa_id=self.pk, data__lt=inizio).exists()
            or GiornoPianificato.objects.filter(assegnazione__commessa_id=self.pk, data__lt=inizio).exists()
            or Task.objects.filter(commessa_id=self.pk, data_inizio__lt=inizio).exists()
            or Task.objects.filter(commessa_id=self.pk, data_scadenza__lt=inizio).exists()
        )
        if prima:
            raise ValidationError(
                "La nuova data di inizio della commessa escluderebbe dati operativi già registrati."
            )

        if fine:
            dopo = (
                RigaOre.objects.filter(assegnazione__commessa_id=self.pk, data__gt=fine).exists()
                or SpesaTrasferta.objects.filter(assegnazione__commessa_id=self.pk, data__gt=fine).exists()
                or GiornoPianificato.objects.filter(assegnazione__commessa_id=self.pk, data__gt=fine).exists()
                or Task.objects.filter(commessa_id=self.pk, data_inizio__gt=fine).exists()
                or Task.objects.filter(commessa_id=self.pk, data_scadenza__gt=fine).exists()
            )
            if dopo:
                raise ValidationError(
                    "La nuova data di fine della commessa escluderebbe dati operativi già registrati."
                )

    def save(self, *args, **kwargs):
        self._validate_children_interval_on_date_change()
        return super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.codice} – {self.cliente}"


class Assegnazione(UUIDTimeStampedModel):
    class Ruolo(models.TextChoices):
        CONSULENTE = "CONSULENTE", "Consulente"
        PROJECT_MANAGER = "PROJECT_MANAGER", "Project Manager"

    class Stato(models.TextChoices):
        ATTIVA = "ATTIVA", "Attiva"
        CONCLUSA = "CONCLUSA", "Conclusa"

    consulente = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="assegnazioni",
    )
    commessa = models.ForeignKey(
        Commessa,
        on_delete=models.PROTECT,
        related_name="assegnazioni",
    )
    fase = models.ForeignKey(
        "phases.FaseCommessa",
        on_delete=models.PROTECT,
        related_name="assegnazioni",
        help_text="Fase operativa della commessa.",
    )
    ore_previste = models.PositiveIntegerField()
    ruolo_commessa = models.CharField(
        max_length=30,
        choices=Ruolo.choices,
        default=Ruolo.CONSULENTE,
    )
    stato = models.CharField(
        max_length=20,
        choices=Stato.choices,
        default=Stato.ATTIVA,
    )
    data_inizio = models.DateField()
    data_fine = models.DateField(null=True, blank=True)

    class Meta:
        db_table = "assegnazione"
        ordering = ("commessa__codice", "consulente__last_name")
        constraints = [
            models.UniqueConstraint(
                fields=("consulente", "fase"),
                condition=Q(stato="ATTIVA"),
                name="uq_assegnazione_attiva_consulente_fase",
            ),
            models.CheckConstraint(
                condition=(
                    Q(data_fine__isnull=True)
                    | Q(data_fine__gte=models.F("data_inizio"))
                ),
                name="assegnazione_fine_non_precede_inizio",
            ),
        ]

    def clean(self):
        from django.core.exceptions import ValidationError

        if self.fase_id and self.commessa_id and self.fase.commessa_id != self.commessa_id:
            raise ValidationError({"fase": "La fase selezionata non appartiene alla commessa."})

        if self.fase_id:
            if self.data_inizio and self.data_inizio < self.commessa.data_inizio:
                raise ValidationError({"data_inizio": "L'assegnazione non può iniziare prima della commessa."})
            if (
                self.data_inizio
                and self.commessa.data_fine_prevista
                and self.data_inizio > self.commessa.data_fine_prevista
            ):
                raise ValidationError({"data_inizio": "L'assegnazione non può iniziare dopo la fine prevista della commessa."})
            if self.data_fine and self.commessa.data_fine_prevista and self.data_fine > self.commessa.data_fine_prevista:
                raise ValidationError({"data_fine": "L'assegnazione non può terminare dopo la commessa."})
            if self.data_inizio and self.fase.data_inizio and self.data_inizio < self.fase.data_inizio:
                raise ValidationError({"data_inizio": "L'assegnazione non può iniziare prima della fase."})
            if (
                self.data_inizio
                and self.fase.data_fine_prevista
                and self.data_inizio > self.fase.data_fine_prevista
            ):
                raise ValidationError({"data_inizio": "L'assegnazione non può iniziare dopo la fine prevista della fase."})
            if self.data_fine and self.fase.data_fine_prevista and self.data_fine > self.fase.data_fine_prevista:
                raise ValidationError({"data_fine": "L'assegnazione non può terminare dopo la fase."})

    def _validate_historical_integrity(self):
        """Evita che un normale ``save()`` riscriva il significato dei dati storici."""
        if not self.pk:
            return

        from django.core.exceptions import ValidationError
        from django.db.models import Max, Min
        from apps.planning.models import GiornoPianificato
        from apps.timesheets.models import RigaOre, SpesaTrasferta

        try:
            originale = Assegnazione.objects.get(pk=self.pk)
        except Assegnazione.DoesNotExist:
            return

        identita_cambiata = (
            originale.consulente_id != self.consulente_id
            or originale.commessa_id != self.commessa_id
            or originale.fase_id != self.fase_id
        )
        date_cambiate = (
            originale.data_inizio != self.data_inizio
            or originale.data_fine != self.data_fine
        )
        if not identita_cambiata and not date_cambiate:
            return

        ha_storia = (
            RigaOre.objects.filter(assegnazione_id=self.pk).exists()
            or SpesaTrasferta.objects.filter(assegnazione_id=self.pk).exists()
            or GiornoPianificato.objects.filter(assegnazione_id=self.pk).exists()
            or TariffaAssegnazione.objects.filter(assegnazione_id=self.pk).exists()
        )
        if identita_cambiata and ha_storia:
            raise ValidationError(
                "Un'assegnazione con dati storici non può cambiare consulente, commessa o fase. "
                "Concludila e creane una nuova."
            )

        if not date_cambiate:
            return

        estremi = []
        for modello, campo in (
            (RigaOre, "data"),
            (SpesaTrasferta, "data"),
            (GiornoPianificato, "data"),
            (TariffaAssegnazione, "valida_dal"),
        ):
            valori = modello.objects.filter(assegnazione_id=self.pk).aggregate(
                minimo=Min(campo),
                massimo=Max(campo),
            )
            if valori["minimo"]:
                estremi.append((valori["minimo"], valori["massimo"]))

        if estremi:
            minimo = min(item[0] for item in estremi)
            massimo = max(item[1] for item in estremi)
            if self.data_inizio and self.data_inizio > minimo:
                raise ValidationError(
                    "La data di inizio dell'assegnazione escluderebbe dati storici già registrati."
                )
            if self.data_fine and self.data_fine < massimo:
                raise ValidationError(
                    "La data di fine dell'assegnazione escluderebbe dati storici già registrati."
                )

    def save(self, *args, **kwargs):
        # Compatibilità con codice legacy: ogni assegnazione deve appartenere
        # a una fase; se il chiamante non la valorizza viene usata la fase
        # tecnica Generale della commessa.
        if self.fase_id is None and self.commessa_id:
            from apps.phases.models import FaseCommessa
            fase, _ = FaseCommessa.objects.get_or_create(
                commessa_id=self.commessa_id,
                sistema=True,
                defaults={
                    "data_inizio": self.commessa.data_inizio,
                    "data_fine_prevista": self.commessa.data_fine_prevista,
                    "ordine": 0,
                    "stato": FaseCommessa.Stato.DA_INIZIARE,
                    "creata_da": None,
                },
            )
            self.fase = fase

        # ``clean`` non modifica i vincoli DB (quindi i test dei vincoli unici
        # continuano a verificare il database), ma impedisce save diretti incoerenti.
        self.clean()
        self._validate_historical_integrity()
        return super().save(*args, **kwargs)

    def __str__(self) -> str:
        fase = f" – {self.fase.nome}" if self.fase_id else ""
        return f"{self.consulente} – {self.commessa}{fase}"


class TariffaAssegnazione(UUIDTimeStampedModel):
    class TipoAttivita(models.TextChoices):
        FORMAZIONE = "FORMAZIONE", "Formazione"
        CONSULENZA = "CONSULENZA", "Consulenza"

    assegnazione = models.ForeignKey(
        Assegnazione,
        on_delete=models.PROTECT,
        related_name="tariffe",
    )
    tipo_attivita = models.CharField(
        max_length=20,
        choices=TipoAttivita.choices,
    )
    tariffa_oraria = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    valida_dal = models.DateField()
    creata_da = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="tariffe_create",
    )

    class Meta:
        db_table = "tariffa_assegnazione"
        ordering = ("assegnazione", "tipo_attivita", "-valida_dal")
        constraints = [
            models.UniqueConstraint(
                fields=("assegnazione", "tipo_attivita", "valida_dal"),
                name="uq_tariffa_assegnazione_tipo_data",
            ),
            models.CheckConstraint(
                condition=Q(tariffa_oraria__gte=0),
                name="tariffa_oraria_non_negativa",
            ),
        ]

    def clean(self):
        from django.core.exceptions import ValidationError

        if self.assegnazione_id and self.valida_dal:
            assegnazione = self.assegnazione
            if self.valida_dal < assegnazione.data_inizio:
                raise ValidationError(
                    {"valida_dal": "La tariffa non può iniziare prima dell'assegnazione."}
                )
            if assegnazione.data_fine and self.valida_dal > assegnazione.data_fine:
                raise ValidationError(
                    {"valida_dal": "La tariffa non può iniziare dopo la fine dell'assegnazione."}
                )

            # Difesa per salvataggi diretti/admin: il percorso applicativo usa
            # anche il lock transazionale in TariffaCreateView.
            from .services import verifica_tariffa_periodi_aperti
            verifica_tariffa_periodi_aperti(
                assegnazione=assegnazione,
                tipo_attivita=self.tipo_attivita,
                valida_dal=self.valida_dal,
                lock=False,
            )

    def save(self, *args, **kwargs):
        self.clean()
        return super().save(*args, **kwargs)

    def __str__(self) -> str:
        return (
            f"{self.assegnazione} – {self.get_tipo_attivita_display()} "
            f"€ {self.tariffa_oraria} dal {self.valida_dal}"
        )
