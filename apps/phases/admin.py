from django.contrib import admin

from .models import FaseCommessa


@admin.register(FaseCommessa)
class FaseCommessaAdmin(admin.ModelAdmin):
    list_display = ("nome", "commessa", "stato", "ordine", "data_inizio", "data_fine_prevista")
    list_filter = ("stato",)
    search_fields = ("nome", "commessa__codice", "descrizione")
    autocomplete_fields = ("commessa", "creata_da")
