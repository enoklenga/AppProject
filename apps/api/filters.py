from django_filters import rest_framework as filters

from apps.operations.models import PeriodoMensile
from apps.projects.models import Assegnazione, Cliente, Commessa
from apps.timesheets.models import RigaOre, SpesaTrasferta


class ClienteFilter(filters.FilterSet):
    class Meta:
        model = Cliente
        fields = {
            "attivo": ["exact"],
        }


class CommessaFilter(filters.FilterSet):
    data_inizio_da = filters.DateFilter(
        field_name="data_inizio",
        lookup_expr="gte",
    )
    data_inizio_a = filters.DateFilter(
        field_name="data_inizio",
        lookup_expr="lte",
    )

    class Meta:
        model = Commessa
        fields = {
            "cliente": ["exact"],
            "stato": ["exact"],
        }


class AssegnazioneFilter(filters.FilterSet):
    class Meta:
        model = Assegnazione
        fields = {
            "consulente": ["exact"],
            "commessa": ["exact"],
            "ruolo_commessa": ["exact"],
            "stato": ["exact"],
        }


class RigaOreFilter(filters.FilterSet):
    data_da = filters.DateFilter(
        field_name="data",
        lookup_expr="gte",
    )
    data_a = filters.DateFilter(
        field_name="data",
        lookup_expr="lte",
    )

    class Meta:
        model = RigaOre
        fields = {
            "assegnazione": ["exact"],
            "tipo_attivita": ["exact"],
        }


class SpesaTrasfertaFilter(filters.FilterSet):
    data_da = filters.DateFilter(
        field_name="data",
        lookup_expr="gte",
    )
    data_a = filters.DateFilter(
        field_name="data",
        lookup_expr="lte",
    )
    importo_min = filters.NumberFilter(
        field_name="importo",
        lookup_expr="gte",
    )
    importo_max = filters.NumberFilter(
        field_name="importo",
        lookup_expr="lte",
    )

    class Meta:
        model = SpesaTrasferta
        fields = {
            "assegnazione": ["exact"],
            "categoria": ["exact"],
        }


class PeriodoMensileFilter(filters.FilterSet):
    class Meta:
        model = PeriodoMensile
        fields = {
            "anno": ["exact", "gte", "lte"],
            "mese": ["exact"],
            "stato": ["exact"],
        }
