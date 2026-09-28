from decimal import Decimal

from django.utils import timezone
from rest_framework import serializers

from apps.operations.services import tariffa_vigente

from .serializers import (
    CommessaSummarySerializer,
    RigaOreSerializer,
    UserSummarySerializer,
)


class PeriodoQuerySerializer(serializers.Serializer):
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


class DashboardAdminQuerySerializer(PeriodoQuerySerializer):
    cliente_id = serializers.UUIDField(required=False)
    commessa_id = serializers.UUIDField(required=False)
    consulente_id = serializers.UUIDField(required=False)


class DashboardPMQuerySerializer(PeriodoQuerySerializer):
    commessa_id = serializers.UUIDField(required=True)


class ReportQuerySerializer(DashboardAdminQuerySerializer):
    pass


class PersonalCommessaSerializer(serializers.Serializer):
    commessa_id = serializers.UUIDField()
    codice = serializers.CharField()
    descrizione = serializers.CharField()
    cliente = serializers.CharField()
    stato = serializers.CharField()
    ore_previste = serializers.IntegerField()
    ore_consuntivate_totali = serializers.IntegerField()
    ore_residue = serializers.IntegerField()
    ore_periodo = serializers.IntegerField()
    spese_periodo = serializers.DecimalField(
        max_digits=14,
        decimal_places=2,
    )
    numero_righe_ore = serializers.IntegerField()
    numero_spese = serializers.IntegerField()
    superamento = serializers.BooleanField()


class DashboardPersonaleSerializer(serializers.Serializer):
    anno = serializers.IntegerField()
    mese = serializers.IntegerField()
    stato_periodo = serializers.CharField()
    modificabile = serializers.BooleanField()
    totale_ore_periodo = serializers.IntegerField()
    totale_spese_periodo = serializers.DecimalField(
        max_digits=14,
        decimal_places=2,
    )
    numero_righe_ore = serializers.IntegerField()
    numero_spese = serializers.IntegerField()
    commesse = PersonalCommessaSerializer(many=True)


class AggregatoEconomicoSerializer(serializers.Serializer):
    chiave = serializers.CharField()
    etichetta = serializers.CharField()
    ore = serializers.IntegerField()
    valore_ore = serializers.DecimalField(
        max_digits=14,
        decimal_places=2,
    )
    spese = serializers.DecimalField(
        max_digits=14,
        decimal_places=2,
    )
    totale = serializers.DecimalField(
        max_digits=14,
        decimal_places=2,
    )
    righe_senza_tariffa = serializers.IntegerField()


class AvanzamentoCommessaAdminSerializer(serializers.Serializer):
    commessa_id = serializers.UUIDField(source="commessa.id")
    codice = serializers.CharField(source="commessa.codice")
    descrizione = serializers.CharField(source="commessa.descrizione")
    cliente = serializers.CharField(
        source="commessa.cliente.ragione_sociale"
    )
    stato = serializers.CharField(source="commessa.stato")
    ore_previste = serializers.IntegerField()
    ore_consuntivate = serializers.IntegerField()
    ore_residue = serializers.IntegerField()
    ore_periodo = serializers.IntegerField()
    valore_ore_periodo = serializers.DecimalField(
        max_digits=14,
        decimal_places=2,
    )
    spese_periodo = serializers.DecimalField(
        max_digits=14,
        decimal_places=2,
    )
    totale_periodo = serializers.DecimalField(
        max_digits=14,
        decimal_places=2,
    )
    righe_senza_tariffa = serializers.IntegerField()
    superamento = serializers.BooleanField()


class DashboardAdminSerializer(serializers.Serializer):
    anno = serializers.IntegerField()
    mese = serializers.IntegerField()
    totale_ore = serializers.IntegerField()
    totale_valore_ore = serializers.DecimalField(
        max_digits=14,
        decimal_places=2,
    )
    totale_spese = serializers.DecimalField(
        max_digits=14,
        decimal_places=2,
    )
    totale_fatturabile = serializers.DecimalField(
        max_digits=14,
        decimal_places=2,
    )
    numero_righe_senza_tariffa = serializers.IntegerField()
    avanzamento_commesse = AvanzamentoCommessaAdminSerializer(
        many=True
    )
    per_cliente = AggregatoEconomicoSerializer(many=True)
    per_commessa = AggregatoEconomicoSerializer(many=True)
    per_fase = AggregatoEconomicoSerializer(many=True)
    per_consulente = AggregatoEconomicoSerializer(many=True)


class AvanzamentoConsulentePMSerializer(serializers.Serializer):
    assegnazione_id = serializers.UUIDField(source="assegnazione.id")
    consulente = UserSummarySerializer(
        source="assegnazione.consulente"
    )
    fase_id = serializers.SerializerMethodField()
    fase = serializers.SerializerMethodField()
    ruolo_commessa = serializers.CharField(
        source="assegnazione.ruolo_commessa"
    )
    stato_assegnazione = serializers.CharField(
        source="assegnazione.stato"
    )
    ore_previste = serializers.IntegerField()
    ore_consuntivate = serializers.IntegerField()
    ore_residue = serializers.IntegerField()
    ore_periodo = serializers.IntegerField()
    superamento = serializers.BooleanField()

    def get_fase_id(self, obj):
        fase = obj.assegnazione.fase
        return fase.id

    def get_fase(self, obj):
        # L'assegnazione di un PM (incarico sull'intera commessa) non
        # ha una fase: senza questo controllo, .fase.nome andrebbe in
        # errore su quelle righe.
        fase = obj.assegnazione.fase
        return fase.nome


class DashboardPMSerializer(serializers.Serializer):
    anno = serializers.IntegerField()
    mese = serializers.IntegerField()
    commessa = CommessaSummarySerializer()
    totale_ore_periodo = serializers.IntegerField()
    totale_ore_consuntivate = serializers.IntegerField()
    totale_ore_previste = serializers.IntegerField()
    totale_ore_residue = serializers.IntegerField()
    team = AvanzamentoConsulentePMSerializer(many=True)
    righe_ore = RigaOreSerializer(many=True)


class ReportRigaOreSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    data = serializers.DateField()
    cliente = serializers.CharField(
        source="assegnazione.commessa.cliente.ragione_sociale"
    )
    commessa_id = serializers.UUIDField(
        source="assegnazione.commessa.id"
    )
    commessa = serializers.CharField(
        source="assegnazione.commessa.codice"
    )
    fase_id = serializers.SerializerMethodField()
    fase = serializers.SerializerMethodField()
    consulente = UserSummarySerializer(
        source="assegnazione.consulente"
    )
    tipo_attivita = serializers.CharField()
    tipo_attivita_descrizione = serializers.CharField(
        source="get_tipo_attivita_display"
    )
    ore = serializers.IntegerField()
    tariffa_oraria = serializers.SerializerMethodField()
    importo_valorizzato = serializers.SerializerMethodField()
    nota = serializers.CharField()
    bloccata_per_consulente = serializers.BooleanField()

    def get_fase_id(self, obj):
        fase = obj.assegnazione.fase
        return fase.id

    def get_fase(self, obj):
        fase = obj.assegnazione.fase
        return fase.nome

    def get_tariffa_oraria(self, obj):
        tariffa = tariffa_vigente(obj)
        return tariffa.tariffa_oraria if tariffa else None

    def get_importo_valorizzato(self, obj):
        tariffa = tariffa_vigente(obj)
        if tariffa is None:
            return None
        return Decimal(obj.ore) * tariffa.tariffa_oraria


class ReportSpesaSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    data = serializers.DateField()
    cliente = serializers.CharField(
        source="assegnazione.commessa.cliente.ragione_sociale"
    )
    commessa_id = serializers.UUIDField(
        source="assegnazione.commessa.id"
    )
    commessa = serializers.CharField(
        source="assegnazione.commessa.codice"
    )
    fase_id = serializers.SerializerMethodField()
    fase = serializers.SerializerMethodField()
    consulente = UserSummarySerializer(
        source="assegnazione.consulente"
    )
    categoria = serializers.CharField()
    categoria_descrizione = serializers.CharField(
        source="get_categoria_display"
    )
    importo = serializers.DecimalField(
        max_digits=14,
        decimal_places=2,
    )
    nota = serializers.CharField()
    bloccata_per_consulente = serializers.BooleanField()

    def get_fase_id(self, obj):
        fase = obj.assegnazione.fase
        return fase.id

    def get_fase(self, obj):
        fase = obj.assegnazione.fase
        return fase.nome
