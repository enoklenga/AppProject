from decimal import Decimal

from django.contrib.auth import authenticate
from rest_framework import serializers

from apps.accounts.models import User
from apps.operations.models import PeriodoMensile
from apps.projects.models import (
    Assegnazione,
    Cliente,
    Commessa,
    TariffaAssegnazione,
)
from apps.timesheets.models import RigaOre, SpesaTrasferta

from .querysets import commesse_gestite_ids


class UserSummarySerializer(serializers.ModelSerializer):
    nome_completo = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = (
            "id",
            "email",
            "first_name",
            "last_name",
            "nome_completo",
            "ruolo",
            "is_active",
        )

    def get_nome_completo(self, obj) -> str:
        return obj.get_full_name().strip() or obj.email


class MeSerializer(UserSummarySerializer):
    project_manager = serializers.SerializerMethodField()

    class Meta(UserSummarySerializer.Meta):
        fields = UserSummarySerializer.Meta.fields + (
            "telefono",
            "deve_cambiare_password",
            "project_manager",
        )

    def get_project_manager(self, obj) -> bool:
        return commesse_gestite_ids(obj).exists()


class TokenLoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(
        write_only=True,
        trim_whitespace=False,
    )

    default_error_messages = {
        "invalid_credentials": "Email o password non validi.",
        "inactive": "L’account non è attivo.",
    }

    def validate(self, attrs):
        user = authenticate(
            request=self.context.get("request"),
            email=attrs["email"],
            password=attrs["password"],
        )
        if user is None:
            self.fail("invalid_credentials")
        if not user.is_active:
            self.fail("inactive")
        attrs["user"] = user
        return attrs


class ClienteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Cliente
        fields = (
            "id",
            "ragione_sociale",
            "partita_iva",
            "referente",
            "note",
            "attivo",
            "created_at",
            "updated_at",
        )


class CommessaSummarySerializer(serializers.ModelSerializer):
    cliente = ClienteSerializer(read_only=True)

    class Meta:
        model = Commessa
        fields = (
            "id",
            "codice",
            "descrizione",
            "cliente",
            "ore_budget",
            "data_inizio",
            "data_fine_prevista",
            "stato",
            "workflow_stato",
        )


class CommessaSerializer(CommessaSummarySerializer):
    class Meta(CommessaSummarySerializer.Meta):
        fields = CommessaSummarySerializer.Meta.fields + (
            "handover_completato",
            "handover_completato_il",
            "handover_completato_da",
            "handover_note",
            "note",
            "created_at",
            "updated_at",
        )


class AssegnazioneSummarySerializer(serializers.ModelSerializer):
    consulente = UserSummarySerializer(read_only=True)
    commessa = CommessaSummarySerializer(read_only=True)
    fase_id = serializers.SerializerMethodField()
    fase = serializers.SerializerMethodField()

    def get_fase_id(self, obj):
        return obj.fase_id

    def get_fase(self, obj):
        return obj.fase.nome

    class Meta:
        model = Assegnazione
        fields = (
            "id",
            "consulente",
            "commessa",
            "fase_id",
            "fase",
            "ore_previste",
            "ruolo_commessa",
            "stato",
            "data_inizio",
            "data_fine",
        )


class AssegnazioneSerializer(AssegnazioneSummarySerializer):
    class Meta(AssegnazioneSummarySerializer.Meta):
        fields = AssegnazioneSummarySerializer.Meta.fields + (
            "created_at",
            "updated_at",
        )


class RigaOreSerializer(serializers.ModelSerializer):
    assegnazione = AssegnazioneSummarySerializer(read_only=True)
    tipo_attivita_descrizione = serializers.CharField(
        source="get_tipo_attivita_display",
        read_only=True,
    )

    class Meta:
        model = RigaOre
        fields = (
            "id",
            "assegnazione",
            "data",
            "tipo_attivita",
            "tipo_attivita_descrizione",
            "ore",
            "nota",
            "bloccata_per_consulente",
            "versione",
            "created_at",
            "updated_at",
        )


class SpesaTrasfertaSerializer(serializers.ModelSerializer):
    assegnazione = AssegnazioneSummarySerializer(read_only=True)
    categoria_descrizione = serializers.CharField(
        source="get_categoria_display",
        read_only=True,
    )

    class Meta:
        model = SpesaTrasferta
        fields = (
            "id",
            "assegnazione",
            "data",
            "categoria",
            "categoria_descrizione",
            "importo",
            "nota",
            "bloccata_per_consulente",
            "versione",
            "created_at",
            "updated_at",
        )


class PeriodoMensileSerializer(serializers.ModelSerializer):
    stato_descrizione = serializers.CharField(
        source="get_stato_display",
        read_only=True,
    )

    class Meta:
        model = PeriodoMensile
        fields = (
            "id",
            "anno",
            "mese",
            "stato",
            "stato_descrizione",
            "data_chiusura",
            "data_riapertura",
        )



class RigaOreCreateSerializer(serializers.Serializer):
    assegnazione_id = serializers.UUIDField()
    data = serializers.DateField()
    tipo_attivita = serializers.ChoiceField(
        choices=TariffaAssegnazione.TipoAttivita.choices
    )
    ore = serializers.IntegerField(min_value=1, max_value=24)
    nota = serializers.CharField(
        required=False,
        allow_blank=True,
        default="",
    )
    motivazione = serializers.CharField(
        required=False,
        allow_blank=True,
        default="",
    )


class RigaOreUpdateSerializer(RigaOreCreateSerializer):
    versione = serializers.IntegerField(min_value=1)


class SpesaCreateSerializer(serializers.Serializer):
    assegnazione_id = serializers.UUIDField()
    data = serializers.DateField()
    categoria = serializers.ChoiceField(
        choices=SpesaTrasferta.Categoria.choices
    )
    importo = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        min_value=Decimal("0.01"),
    )
    nota = serializers.CharField(
        required=False,
        allow_blank=True,
        default="",
    )


class SpesaUpdateSerializer(SpesaCreateSerializer):
    versione = serializers.IntegerField(min_value=1)
    motivazione = serializers.CharField(
        required=False,
        allow_blank=True,
        default="",
    )


class MutationWarningsSerializer(serializers.Serializer):
    monte_ore_superato = serializers.BooleanField()
    limite_giornaliero_superato = serializers.BooleanField()


class RigaOreMutationResponseSerializer(serializers.Serializer):
    riga = RigaOreSerializer()
    avvisi = MutationWarningsSerializer()


class SpesaMutationResponseSerializer(serializers.Serializer):
    spesa = SpesaTrasfertaSerializer()


class DeleteVersionSerializer(serializers.Serializer):
    versione = serializers.IntegerField(min_value=1)
    motivazione = serializers.CharField(
        required=False,
        allow_blank=True,
        default="",
    )
