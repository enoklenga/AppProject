from django.contrib import admin

from .models import GiornoPianificato


@admin.register(GiornoPianificato)
class GiornoPianificatoAdmin(admin.ModelAdmin):
    """Vista diagnostica: le mutazioni operative devono passare dai service."""

    list_display = (
        "data",
        "consulente",
        "commessa",
        "ore_pianificate",
        "tipo_attivita",
        "stato_sessione",
        "modificata_da_admin",
        "updated_at",
    )
    list_filter = (
        "data",
        "stato_sessione",
        "tipo_attivita",
        "modificata_da_admin",
        "assegnazione__commessa",
    )
    search_fields = (
        "assegnazione__consulente__first_name",
        "assegnazione__consulente__last_name",
        "assegnazione__consulente__email",
        "assegnazione__commessa__codice",
        "assegnazione__commessa__cliente__ragione_sociale",
    )
    readonly_fields = (
        "assegnazione",
        "data",
        "ore_pianificate",
        "tipo_attivita",
        "stato_sessione",
        "confermata_il",
        "confermata_da",
        "riga_ore_generata",
        "inserita_da",
        "modificata_da_admin",
        "ultima_modifica_da",
        "created_at",
        "updated_at",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def get_actions(self, request):
        return {}

    @admin.display(description="Consulente", ordering="assegnazione__consulente__last_name")
    def consulente(self, obj):
        return obj.assegnazione.consulente

    @admin.display(description="Commessa", ordering="assegnazione__commessa__codice")
    def commessa(self, obj):
        return obj.assegnazione.commessa
