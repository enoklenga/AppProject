from django.conf import settings
from django.db import models
from django.utils import timezone
from rest_framework.authtoken.models import Token

from apps.operations.models import Importazione


class ApiImportazioneAnteprima(models.Model):
    """
    Conserva l'anteprima validata fino alla conferma API.
    """

    importazione = models.OneToOneField(
        Importazione,
        on_delete=models.CASCADE,
        related_name="api_anteprima",
        primary_key=True,
    )
    tipo_importazione = models.CharField(max_length=20)
    dati_sessione = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "api_importazione_anteprima"

    def __str__(self) -> str:
        return (
            f"Anteprima API {self.importazione_id} "
            f"({self.tipo_importazione})"
        )


class ApiTokenMetadata(models.Model):
    """
    Metadati di sicurezza associati al token DRF.

    La chiave del token non viene duplicata in questa tabella.
    La revoca avviene eliminando il Token originale.
    """

    token = models.OneToOneField(
        Token,
        on_delete=models.CASCADE,
        related_name="lef_metadata",
        primary_key=True,
    )
    expires_at = models.DateTimeField()
    last_used_at = models.DateTimeField(null=True, blank=True)
    last_used_ip_hash = models.CharField(max_length=64, blank=True)
    rotated_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="token_api_creati",
        null=True,
        blank=True,
    )

    class Meta:
        db_table = "api_token_metadata"
        indexes = [
            models.Index(
                fields=("expires_at",),
                name="idx_api_token_expires",
            ),
        ]

    @property
    def is_expired(self) -> bool:
        return timezone.now() >= self.expires_at

    def __str__(self) -> str:
        return f"Token API di {self.token.user.email}"
