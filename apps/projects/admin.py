from django.contrib import admin

from .forms import AssegnazioneForm, CommessaForm, TariffaAssegnazioneForm
from .models import Assegnazione, Cliente, Commessa, TariffaAssegnazione
from .services import sync_general_phase_dates, verifica_tariffa_periodi_aperti


@admin.register(Cliente)
class ClienteAdmin(admin.ModelAdmin):
    list_display = ("ragione_sociale", "partita_iva", "attivo")
    list_filter = ("attivo",)
    search_fields = ("ragione_sociale", "partita_iva")


@admin.register(Commessa)
class CommessaAdmin(admin.ModelAdmin):
    form = CommessaForm
    list_display = ("codice", "cliente", "data_inizio", "workflow_stato", "stato", "handover_completato", "ore_budget")
    list_filter = ("stato", "workflow_stato", "handover_completato", "cliente")
    search_fields = ("codice", "cliente__ragione_sociale", "descrizione")
    readonly_fields = (
        "stato",
        "workflow_stato",
        "handover_completato",
        "handover_note",
        "handover_completato_il",
        "handover_completato_da",
    )

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        sync_general_phase_dates(obj)


@admin.register(Assegnazione)
class AssegnazioneAdmin(admin.ModelAdmin):
    form = AssegnazioneForm
    list_display = (
        "consulente",
        "commessa",
        "fase",
        "ore_previste",
        "ruolo_commessa",
        "stato",
    )
    list_filter = ("stato", "ruolo_commessa", "commessa")
    search_fields = (
        "consulente__email",
        "consulente__first_name",
        "consulente__last_name",
        "commessa__codice",
    )


@admin.register(TariffaAssegnazione)
class TariffaAssegnazioneAdmin(admin.ModelAdmin):
    form = TariffaAssegnazioneForm
    list_display = (
        "assegnazione",
        "tipo_attivita",
        "tariffa_oraria",
        "valida_dal",
    )
    list_filter = ("tipo_attivita", "valida_dal")

    def save_model(self, request, obj, form, change):
        verifica_tariffa_periodi_aperti(
            assegnazione=obj.assegnazione,
            tipo_attivita=obj.tipo_attivita,
            valida_dal=obj.valida_dal,
            lock=True,
        )
        super().save_model(request, obj, form, change)
