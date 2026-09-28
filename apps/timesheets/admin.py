from django.contrib import admin

from .models import RigaOre, SpesaTrasferta


class ServiceBackedReadOnlyAdmin(admin.ModelAdmin):
    """Il Django Admin è solo diagnostico: nessun bypass di lock/audit."""

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def get_actions(self, request):
        return {}

    def get_readonly_fields(self, request, obj=None):
        return tuple(field.name for field in self.model._meta.fields)


@admin.register(RigaOre)
class RigaOreAdmin(ServiceBackedReadOnlyAdmin):
    list_display = (
        "data",
        "assegnazione",
        "tipo_attivita",
        "ore",
        "bloccata_per_consulente",
    )
    list_filter = (
        "tipo_attivita",
        "bloccata_per_consulente",
        "modificata_da_admin",
        "data",
    )
    search_fields = (
        "assegnazione__consulente__email",
        "assegnazione__commessa__codice",
        "nota",
    )


@admin.register(SpesaTrasferta)
class SpesaTrasfertaAdmin(ServiceBackedReadOnlyAdmin):
    list_display = (
        "data",
        "assegnazione",
        "categoria",
        "importo",
        "bloccata_per_consulente",
    )
    list_filter = ("categoria", "bloccata_per_consulente", "data")
