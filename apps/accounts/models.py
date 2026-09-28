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
            "Responsabile consulenza / Business Unit",
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
        return self.ruolo == self.Ruolo.RESPONSABILE_CONSULENZA

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
