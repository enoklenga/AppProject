from django.contrib import admin

from .models import Notification


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):

    list_display = (
        "tipo",
        "destinatario",
        "task",
        "letta_il",
        "created_at",
    )

    list_filter = (
        "tipo",
        "letta_il",
        "created_at",
    )

    search_fields = (
        "titolo",
        "messaggio",
        "destinatario__email",
        "destinatario__first_name",
        "destinatario__last_name",
        "task__titolo",
        "task__commessa__codice",
    )

    autocomplete_fields = (
        "destinatario",
        "attore",
        "task",
    )

    readonly_fields = (
        "created_at",
        "updated_at",
    )