from django.conf import settings
from django.utils import timezone
from rest_framework import serializers

from apps.operations.models import (
    AuditLog,
    ConfigurazionePromemoria,
    ErroreImportazione,
    Importazione,
    InvioPromemoria,
)

from .serializers import UserSummarySerializer


class PeriodoPromemoriaQuerySerializer(serializers.Serializer):
    anno = serializers.IntegerField(
        required=False,
        min_value=2000,
        max_value=2100,
    )
    mese = serializers.IntegerField(
        required=False,
        min_value=1,
        max_value=12,
    )

    def validate(self, attrs):
        oggi = timezone.localdate()
        attrs.setdefault("anno", oggi.year)
        attrs.setdefault("mese", oggi.month)
        return attrs


class ConfigurazionePromemoriaSerializer(serializers.ModelSerializer):
    aggiornata_da = UserSummarySerializer(read_only=True)

    class Meta:
        model = ConfigurazionePromemoria
        fields = (
            "id",
            "giorno_invio",
            "ora_invio",
            "attiva",
            "solo_assenza_totale_ore",
            "aggiornata_da",
            "updated_at",
        )
        read_only_fields = (
            "id",
            "aggiornata_da",
            "updated_at",
        )

    def validate_giorno_invio(self, value):
        if not 1 <= value <= 28:
            raise serializers.ValidationError(
                "Il giorno deve essere compreso tra 1 e 28."
            )
        return value


class DestinatarioPromemoriaSerializer(serializers.Serializer):
    consulente = UserSummarySerializer()
    gia_inviato = serializers.BooleanField()
    ultimo_stato = serializers.CharField(
        allow_null=True,
        required=False,
    )


class AnteprimaPromemoriaSerializer(serializers.Serializer):
    anno = serializers.IntegerField()
    mese = serializers.IntegerField()
    totale_destinatari = serializers.IntegerField()
    destinatari = DestinatarioPromemoriaSerializer(many=True)


class InvioManualePromemoriaSerializer(
    PeriodoPromemoriaQuerySerializer
):
    conferma = serializers.BooleanField()

    def validate_conferma(self, value):
        if value is not True:
            raise serializers.ValidationError(
                "È necessaria la conferma esplicita dell’invio."
            )
        return value


class EsitoPromemoriaSerializer(serializers.Serializer):
    anno = serializers.IntegerField()
    mese = serializers.IntegerField()
    destinatari = serializers.IntegerField()
    inviati = serializers.IntegerField()
    saltati = serializers.IntegerField()
    errori = serializers.IntegerField()
    motivo_salto = serializers.CharField(
        allow_blank=True,
        required=False,
    )


class InvioPromemoriaSerializer(serializers.ModelSerializer):
    consulente = UserSummarySerializer(read_only=True)
    stato_descrizione = serializers.CharField(
        source="get_stato_display",
        read_only=True,
    )

    class Meta:
        model = InvioPromemoria
        fields = (
            "id",
            "consulente",
            "anno",
            "mese",
            "stato",
            "stato_descrizione",
            "data_tentativo",
            "errore",
            "created_at",
            "updated_at",
        )


class InvioPromemoriaFilterSerializer(
    PeriodoPromemoriaQuerySerializer
):
    anno = serializers.IntegerField(
        required=False,
        min_value=2000,
        max_value=2100,
    )
    mese = serializers.IntegerField(
        required=False,
        min_value=1,
        max_value=12,
    )
    stato = serializers.ChoiceField(
        required=False,
        choices=InvioPromemoria.Stato.choices,
    )
    consulente_id = serializers.UUIDField(required=False)

    def validate(self, attrs):
        # Nei filtri l'assenza del periodo significa "tutti i periodi".
        return attrs


class ErroreImportazioneSerializer(serializers.ModelSerializer):
    class Meta:
        model = ErroreImportazione
        fields = (
            "id",
            "numero_riga",
            "campo",
            "codice_errore",
            "messaggio",
            "dati_riga",
        )


class ImportazioneSerializer(serializers.ModelSerializer):
    avviata_da = UserSummarySerializer(read_only=True)
    stato_descrizione = serializers.CharField(
        source="get_stato_display",
        read_only=True,
    )
    errori = ErroreImportazioneSerializer(many=True, read_only=True)
    conferma_disponibile = serializers.SerializerMethodField()

    class Meta:
        model = Importazione
        fields = (
            "id",
            "avviata_da",
            "nome_file",
            "file_hash",
            "stato",
            "stato_descrizione",
            "righe_totali",
            "righe_valide",
            "righe_errore",
            "completed_at",
            "created_at",
            "updated_at",
            "conferma_disponibile",
            "errori",
        )

    def get_conferma_disponibile(self, obj) -> bool:
        return (
            obj.stato == Importazione.Stato.PRONTA
            and hasattr(obj, "api_anteprima")
        )


class ImportazioneUploadSerializer(serializers.Serializer):
    tipo_importazione = serializers.ChoiceField(
        choices=(("ORE", "Ore"), ("SPESE", "Spese")),
    )
    file = serializers.FileField()

    def validate_file(self, value):
        nome = value.name.lower()
        if not (nome.endswith(".xlsx") or nome.endswith(".csv")):
            raise serializers.ValidationError(
                "Il file deve essere in formato .xlsx oppure .csv."
            )
        max_mb = getattr(settings, "IMPORT_MAX_UPLOAD_SIZE_MB", 5)
        if value.size > max_mb * 1024 * 1024:
            raise serializers.ValidationError(
                f"Il file supera la dimensione massima di {max_mb} MB."
            )
        return value


class ImportazioneConfermaSerializer(serializers.Serializer):
    conferma = serializers.BooleanField()

    def validate_conferma(self, value):
        if value is not True:
            raise serializers.ValidationError(
                "È necessaria la conferma esplicita dell’importazione."
            )
        return value


class ImportazioneFilterSerializer(serializers.Serializer):
    stato = serializers.ChoiceField(
        required=False,
        choices=Importazione.Stato.choices,
    )
    avviata_da_id = serializers.UUIDField(required=False)
    dal = serializers.DateField(required=False)
    al = serializers.DateField(required=False)

    def validate(self, attrs):
        dal = attrs.get("dal")
        al = attrs.get("al")
        if dal and al and al < dal:
            raise serializers.ValidationError(
                {"al": "La data finale non può precedere quella iniziale."}
            )
        return attrs


class AuditLogSerializer(serializers.ModelSerializer):
    utente = UserSummarySerializer(read_only=True)

    class Meta:
        model = AuditLog
        fields = (
            "id",
            "utente",
            "entita",
            "entita_id",
            "azione",
            "valore_precedente",
            "valore_nuovo",
            "motivazione",
            "created_at",
        )


class AuditLogFilterSerializer(serializers.Serializer):
    entita = serializers.CharField(required=False)
    entita_id = serializers.UUIDField(required=False)
    azione = serializers.CharField(required=False)
    utente = serializers.CharField(required=False)
    dal = serializers.DateField(required=False)
    al = serializers.DateField(required=False)

    def validate(self, attrs):
        dal = attrs.get("dal")
        al = attrs.get("al")
        if dal and al and al < dal:
            raise serializers.ValidationError(
                {"al": "La data finale non può precedere quella iniziale."}
            )
        return attrs
