from django.contrib import admin

from .models import Task, TaskComment


@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = (
        "titolo",
        "commessa",
        "assegnato_a",
        "stato",
        "priorita",
        "data_scadenza",
        "created_at",
    )

    list_filter = (
        "stato",
        "priorita",
        "commessa",
    )

    search_fields = (
        "titolo",
        "descrizione",
        "commessa__codice",
        "commessa__cliente__ragione_sociale",
        "assegnato_a__first_name",
        "assegnato_a__last_name",
        "assegnato_a__email",
    )

    autocomplete_fields = (
        "commessa",
        "assegnato_a",
        "creato_da",
    )

    readonly_fields = (
        "created_at",
        "updated_at",
        "completato_il",
    )


@admin.register(TaskComment)
class TaskCommentAdmin(admin.ModelAdmin):
    list_display = (
        "task",
        "autore",
        "created_at",
    )

    search_fields = (
        "task__titolo",
        "testo",
        "autore__first_name",
        "autore__last_name",
        "autore__email",
    )

    autocomplete_fields = (
        "task",
        "autore",
    )

    readonly_fields = (
        "created_at",
        "updated_at",
    )