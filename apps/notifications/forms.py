from django import forms

from .models import NotificationPreference


class NotificationPreferenceForm(forms.ModelForm):

    class Meta:
        model = NotificationPreference

        fields = [
            "task_assigned",
            "task_commented",
            "task_due_soon",
            "task_overdue",
            "task_creato",
            "task_modificato",
            "task_riassegnato",
            "task_cambio_stato",
            "task_eliminato",
            "pianificazione_creata",
            "pianificazione_aggiornata",
            "fase_creata",
            "fase_aggiornata",
            "documento_caricato",
            "documento_eliminato",
        ]

        labels = {
            "task_assigned": (
                "Nuove attività assegnate"
            ),
            "task_commented": (
                "Commenti sulle attività"
            ),
            "task_due_soon": (
                "Attività in scadenza"
            ),
            "task_overdue": (
                "Attività scadute"
            ),
            "task_creato": (
                "Nuove attività create sulle mie commesse"
            ),
            "task_modificato": (
                "Attività modificate"
            ),
            "task_riassegnato": (
                "Attività riassegnate"
            ),
            "task_cambio_stato": (
                "Cambio stato di un'attività"
            ),
            "task_eliminato": (
                "Attività eliminate"
            ),
            "pianificazione_creata": (
                "Nuova pianificazione di un collega"
            ),
            "pianificazione_aggiornata": (
                "Pianificazione modificata o eliminata"
            ),
            "fase_creata": (
                "Nuova fase di commessa"
            ),
            "fase_aggiornata": (
                "Fase modificata o eliminata"
            ),
            "documento_caricato": (
                "Nuovo documento caricato"
            ),
            "documento_eliminato": (
                "Documento eliminato"
            ),
        }
        