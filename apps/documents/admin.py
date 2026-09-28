from django.contrib import admin

from .models import DocumentoCommessa


@admin.register(DocumentoCommessa)
class DocumentoCommessaAdmin(admin.ModelAdmin):
    list_display = (
        "nome_originale",
        "commessa",
        "categoria",
        "privato",
        "caricato_da",
        "created_at",
    )
    list_filter = ("categoria", "privato")
    search_fields = (
        "nome_originale",
        "commessa__codice",
        "descrizione",
    )
    autocomplete_fields = ("commessa", "caricato_da")
    readonly_fields = ("dimensione_byte", "created_at", "updated_at")
