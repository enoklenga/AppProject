from django.contrib import admin

from .models import (
    AuditLog,
    ConfigurazionePromemoria,
    ErroreImportazione,
    Importazione,
    InvioPromemoria,
    PeriodoMensile,
)


@admin.register(PeriodoMensile)
class PeriodoMensileAdmin(admin.ModelAdmin):
    list_display = (
        "anno",
        "mese",
        "stato",
        "data_chiusura",
        "forzatura_tariffe_mancanti",
    )
    list_filter = ("stato", "anno")


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ("created_at", "utente", "entita", "azione", "entita_id")
    list_filter = ("entita", "azione", "created_at")
    search_fields = ("utente__email", "entita", "entita_id", "motivazione")
    readonly_fields = (
        "utente",
        "entita",
        "entita_id",
        "azione",
        "valore_precedente",
        "valore_nuovo",
        "motivazione",
        "created_at",
    )


admin.site.register(ConfigurazionePromemoria)
admin.site.register(InvioPromemoria)
admin.site.register(Importazione)
admin.site.register(ErroreImportazione)
