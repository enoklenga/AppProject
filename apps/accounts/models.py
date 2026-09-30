import uuid

from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator
from django.db import models
from django.db.models.functions import Lower

from apps.common.models import UUIDTimeStampedModel

from .managers import UserManager


def validate_profile_photo_size(file):
    """Limita gli avatar a 3 MB per evitare upload eccessivi."""
    max_bytes = 3 * 1024 * 1024
    if file.size > max_bytes:
        raise ValidationError("La foto profilo non può superare 3 MB.")


class User(AbstractUser):
    class Ruolo(models.TextChoices):
        ADMIN = "ADMIN", "Admin LEF"
        CONSULENTE = "CONSULENTE", "Consulente / Team esecutivo"
        RESPONSABILE_CONSULENZA = (
            "RESP_CONSULENZA",
            "Responsabile Business Unit",
        )
        AMMINISTRAZIONE = "AMMINISTRAZIONE", "Amministrazione"
        COMMERCIALE = "COMMERCIALE", "Commerciale"
        DIREZIONE_GENERALE = "DIREZIONE_GENERALE", "Direzione Generale"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    username = None
    email = models.EmailField("email", unique=True)
    telefono = models.CharField(max_length=30, blank=True)
    foto_profilo = models.ImageField(
        "foto profilo",
        upload_to="avatars/%Y/%m/",
        blank=True,
        null=True,
        validators=[
            FileExtensionValidator(allowed_extensions=("jpg", "jpeg", "png", "webp")),
            validate_profile_photo_size,
        ],
        help_text="JPG, PNG o WebP. Dimensione massima 3 MB.",
    )
    ruolo = models.CharField(
        max_length=30,
        choices=Ruolo.choices,
        default=Ruolo.CONSULENTE,
    )
    deve_cambiare_password = models.BooleanField(default=True)
    invito_inviato_il = models.DateTimeField(null=True, blank=True, editable=False)
    attivato_il = models.DateTimeField(null=True, blank=True, editable=False)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS: list[str] = []

    business_units = models.ManyToManyField(
        "BusinessUnit",
        through="UserBusinessUnit",
        related_name="utenti",
        blank=True,
    )

    objects = UserManager()

    class Meta:
        db_table = "utente"
        ordering = ("last_name", "first_name", "email")

    def __str__(self) -> str:
        nome_completo = self.get_full_name().strip()
        return nome_completo or self.email

    @property
    def is_admin_lef(self) -> bool:
        return self.ruolo == self.Ruolo.ADMIN

    @property
    def is_responsabile_consulenza(self) -> bool:
        # Alias legacy mantenuto per compatibilità con template e permessi esistenti.
        return self.ruolo == self.Ruolo.RESPONSABILE_CONSULENZA

    @property
    def is_responsabile_business_unit(self) -> bool:
        return self.is_responsabile_consulenza

    # -- Livelli di gestione (vedi apps/accounts/access.py) -----------------
    @property
    def is_gestore_globale(self) -> bool:
        """Admin o Amministrazione: gestione di tutto il portafoglio."""
        from .access import is_global_manager

        return is_global_manager(self)

    @property
    def is_gestore_bu(self) -> bool:
        """Responsabile di almeno una Business Unit attiva."""
        from .access import is_bu_manager

        return is_bu_manager(self)

    @property
    def is_gestore(self) -> bool:
        """Ha l'interfaccia di gestione (Admin, Amministrazione, Resp. BU)."""
        from .access import is_manager

        return is_manager(self)

    def puo_gestire_commessa(self, commessa) -> bool:
        from .access import can_manage_commessa

        return can_manage_commessa(self, commessa)

    def business_unit_attive(self):
        from .access import membership_current_q

        return BusinessUnit.objects.filter(
            membership_current_q("membership__"),
            membership__utente=self,
            attiva=True,
        ).distinct()

    def business_unit_gestite(self):
        from .access import membership_current_q

        return BusinessUnit.objects.filter(
            membership_current_q("membership__"),
            membership__utente=self,
            membership__responsabile=True,
            attiva=True,
        ).distinct()

    def puo_essere_pm_in_business_unit(self, business_unit) -> bool:
        if self.is_admin_lef:
            return True
        if business_unit is None:
            # Compatibilità con commesse legacy non ancora classificate per BU.
            return self.is_risorsa_ingaggiabile
        from .access import membership_current_q

        return UserBusinessUnit.objects.filter(
            membership_current_q(),
            utente=self,
            business_unit=business_unit,
            puo_essere_pm=True,
        ).exists()

    @property
    def is_amministrazione(self) -> bool:
        return self.ruolo == self.Ruolo.AMMINISTRAZIONE

    @property
    def is_commerciale(self) -> bool:
        return self.ruolo == self.Ruolo.COMMERCIALE

    @property
    def is_direzione_generale(self) -> bool:
        return self.ruolo == self.Ruolo.DIREZIONE_GENERALE

    @property
    def is_risorsa_ingaggiabile(self) -> bool:
        """Risorsa selezionabile sul Teamwork/agenda di progetto.

        La matrice autorizzativa dei ruoli organizzativi resta separata dal
        ruolo ricoperto sulla singola commessa (Consulente/PM).
        """
        return self.is_active and self.ruolo in {
            self.Ruolo.CONSULENTE,
            self.Ruolo.RESPONSABILE_CONSULENZA,
        }

    def is_risorsa_ingaggiabile_in_data(self, giorno, ore_richieste: int = 1) -> bool:
        """Ingaggiabilità operativa V1: ruolo/attivazione + disponibilità agenda del giorno."""
        from apps.planning.selectors import is_consultant_available
        return is_consultant_available(
            consulente=self,
            giorno=giorno,
            ore_richieste=ore_richieste,
        )

    @property
    def is_pending_activation(self) -> bool:
        """Account creato tramite invito che non ha ancora una password propria."""
        return not self.has_usable_password()


class BusinessUnit(UUIDTimeStampedModel):
    """Area organizzativa LEF (es. Consulenza, Formazione, AI)."""

    nome = models.CharField(max_length=120, unique=True)
    codice = models.CharField(max_length=40, unique=True)
    descrizione = models.TextField(blank=True)
    attiva = models.BooleanField(default=True)

    class Meta:
        db_table = "business_unit"
        ordering = ("nome",)
        constraints = [
            models.UniqueConstraint(Lower("nome"), name="uq_business_unit_nome_ci"),
            models.UniqueConstraint(Lower("codice"), name="uq_business_unit_codice_ci"),
        ]

    def clean(self):
        super().clean()
        self.nome = (self.nome or "").strip()
        self.codice = (self.codice or "").strip().upper()
        if BusinessUnit.objects.filter(nome__iexact=self.nome).exclude(pk=self.pk).exists():
            raise ValidationError({"nome": "Esiste già una Business Unit con questo nome."})
        if BusinessUnit.objects.filter(codice__iexact=self.codice).exclude(pk=self.pk).exists():
            raise ValidationError({"codice": "Esiste già una Business Unit con questo codice."})

        # Una BU con commesse ancora aperte non può essere disattivata: il
        # perimetro autorizzativo sparirebbe mentre il lavoro e ancora attivo.
        if self.pk and not self.attiva:
            originale_attiva = (
                BusinessUnit.objects.filter(pk=self.pk)
                .values_list("attiva", flat=True)
                .first()
            )
            if originale_attiva:
                from apps.projects.models import Commessa

                aperte = Commessa.objects.filter(
                    business_unit_id=self.pk,
                    stato=Commessa.Stato.APERTA,
                ).count()
                if aperte:
                    raise ValidationError(
                        {
                            "attiva": (
                                f"La Business Unit non può essere disattivata: "
                                f"sono presenti {aperte} commesse aperte. "
                                "Chiudile o riclassificale prima di procedere."
                            )
                        }
                    )

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self) -> str:
        return self.nome


class UserBusinessUnit(UUIDTimeStampedModel):
    """Appartenenza di una persona a una o più Business Unit.

    Le capability sono indipendenti: una persona può essere membro operativo,
    responsabile di BU e/o PM abilitato nello stesso perimetro.
    """

    utente = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="membership_business_unit",
    )
    business_unit = models.ForeignKey(
        BusinessUnit,
        on_delete=models.PROTECT,
        related_name="membership",
    )
    responsabile = models.BooleanField(default=False)
    puo_essere_pm = models.BooleanField(default=False)
    attiva = models.BooleanField(default=True)
    data_inizio = models.DateField(null=True, blank=True)
    data_fine = models.DateField(null=True, blank=True)

    class Meta:
        db_table = "utente_business_unit"
        ordering = ("business_unit__nome", "utente__last_name", "utente__first_name")
        constraints = [
            models.UniqueConstraint(
                fields=("utente", "business_unit"),
                name="uq_utente_business_unit",
            ),
            models.CheckConstraint(
                condition=models.Q(data_fine__isnull=True) | models.Q(data_inizio__isnull=True) | models.Q(data_fine__gte=models.F("data_inizio")),
                name="utente_bu_fine_non_precede_inizio",
            ),
        ]

    def clean(self):
        super().clean()
        if self.data_inizio and self.data_fine and self.data_fine < self.data_inizio:
            raise ValidationError({"data_fine": "La data di fine non può precedere la data di inizio."})
        if self.responsabile and self.utente_id and not self.utente.is_active:
            raise ValidationError({"utente": "Un responsabile di Business Unit deve essere un utente attivo."})

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self) -> str:
        qualifiche = []
        if self.responsabile:
            qualifiche.append("Responsabile")
        if self.puo_essere_pm:
            qualifiche.append("PM")
        suffix = f" ({', '.join(qualifiche)})" if qualifiche else ""
        return f"{self.utente} – {self.business_unit}{suffix}"


class Skill(UUIDTimeStampedModel):
    """Voce configurabile della Skill Matrix LEF."""

    nome = models.CharField(max_length=120, unique=True)
    categoria = models.CharField(max_length=120, blank=True)
    descrizione = models.TextField(blank=True)
    attiva = models.BooleanField(default=True)

    class Meta:
        db_table = "skill"
        ordering = ("categoria", "nome")
        constraints = [
            models.UniqueConstraint(
                Lower("nome"),
                name="uq_skill_nome_ci",
            ),
        ]

    def clean(self):
        super().clean()
        if self.nome:
            duplicata = Skill.objects.filter(nome__iexact=self.nome.strip()).exclude(pk=self.pk)
            if duplicata.exists():
                raise ValidationError({"nome": "Esiste già una skill con questo nome."})

    def save(self, *args, **kwargs):
        self.nome = (self.nome or "").strip()
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self) -> str:
        return self.nome


class UserSkill(UUIDTimeStampedModel):
    """Livello di una risorsa su una skill.

    La V1 usa volutamente tre livelli neutri: potranno essere rinominati o
    arricchiti in seguito senza cambiare la relazione dati.
    """

    class Livello(models.IntegerChoices):
        LIVELLO_1 = 1, "Livello 1"
        LIVELLO_2 = 2, "Livello 2"
        LIVELLO_3 = 3, "Livello 3"

    utente = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="skill_matrix",
    )
    skill = models.ForeignKey(
        Skill,
        on_delete=models.PROTECT,
        related_name="livelli_utenti",
    )
    livello = models.PositiveSmallIntegerField(choices=Livello.choices)

    class Meta:
        db_table = "utente_skill"
        ordering = ("utente__last_name", "utente__first_name", "skill__nome")
        constraints = [
            models.UniqueConstraint(
                fields=("utente", "skill"),
                name="uq_utente_skill",
            ),
            models.CheckConstraint(
                condition=models.Q(livello__in=(1, 2, 3)),
                name="utente_skill_livello_1_3",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.utente} – {self.skill}: {self.get_livello_display()}"
