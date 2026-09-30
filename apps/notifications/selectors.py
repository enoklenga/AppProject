from __future__ import annotations

from datetime import timedelta

from django.db.models import Count, Exists, OuterRef, Q
from django.utils import timezone

from apps.accounts.models import User, UserBusinessUnit
from apps.projects.models import Assegnazione
from apps.tasks.models import Task

from .models import Notification


def _is_authenticated(
    user,
) -> bool:
    return bool(
        user
        and getattr(
            user,
            "is_authenticated",
            False,
        )
    )


def _base_notifications():
    """
    QuerySet base ottimizzato.
    """

    return (
        Notification.objects
        .select_related(
            "destinatario",
            "attore",
            "task",
            "task__assegnato_a",
            "task__commessa",
            "task__commessa__cliente",
            "pianificazione__assegnazione__commessa",
            "pianificazione__assegnazione__commessa__cliente",
            "fase__commessa",
            "fase__commessa__cliente",
            "documento__commessa",
            "documento__commessa__cliente",
        )
    )


# =========================================================
# NOTIFICHE UTENTE
# =========================================================


def notifications_for_user(
    *,
    user,
    unread_only=False,
):
    """
    Tutte le notifiche dell'utente.
    """

    queryset = (
        _base_notifications()
    )

    if not _is_authenticated(
        user
    ):
        return queryset.none()

    queryset = queryset.filter(
        destinatario=user
    )

    if unread_only:
        queryset = queryset.filter(
            letta_il__isnull=True
        )

    return queryset.order_by(
        "-created_at"
    )


def unread_notifications_for_user(
    *,
    user,
):
    """
    Solo notifiche non lette.
    """

    return notifications_for_user(
        user=user,
        unread_only=True,
    )


def unread_notification_count(
    *,
    user,
) -> int:
    """
    Numero utilizzato dalla futura campanella.
    """

    return (
        unread_notifications_for_user(
            user=user
        )
        .count()
    )


def recent_notifications_for_user(
    *,
    user,
    limit=10,
):
    """
    Ultime N notifiche.

    Utile per il menu a tendina della campanella.
    """

    if limit < 1:
        limit = 1

    return notifications_for_user(
        user=user
    )[:limit]


def notification_for_user(
    *,
    user,
    pk,
):
    """
    QuerySet sicuro per recuperare una singola
    notifica appartenente all'utente.
    """

    if not _is_authenticated(
        user
    ):
        return (
            _base_notifications()
            .none()
        )

    return (
        _base_notifications()
        .filter(
            destinatario=user,
            pk=pk,
        )
    )


# =========================================================
# RIEPILOGO NOTIFICHE
# =========================================================


def notification_summary(
    *,
    user,
):
    """
    KPI per l'eventuale pagina Notifiche.
    """

    if not _is_authenticated(
        user
    ):
        return {
            "totale": 0,
            "non_lette": 0,
            "task_assegnati": 0,
            "commenti": 0,
            "in_scadenza": 0,
            "scadute": 0,
        }

    queryset = (
        Notification.objects
        .filter(
            destinatario=user
        )
    )

    data = queryset.aggregate(
        totale=Count(
            "id"
        ),

        non_lette=Count(
            "id",
            filter=Q(
                letta_il__isnull=True
            ),
        ),

        task_assegnati=Count(
            "id",
            filter=Q(
                tipo=(
                    Notification
                    .Tipo
                    .TASK_ASSIGNED
                )
            ),
        ),

        commenti=Count(
            "id",
            filter=Q(
                tipo=(
                    Notification
                    .Tipo
                    .TASK_COMMENTED
                )
            ),
        ),

        in_scadenza=Count(
            "id",
            filter=Q(
                tipo=(
                    Notification
                    .Tipo
                    .TASK_DUE_SOON
                )
            ),
        ),

        scadute=Count(
            "id",
            filter=Q(
                tipo=(
                    Notification
                    .Tipo
                    .TASK_OVERDUE
                )
            ),
        ),
    )

    return {
        "totale": (
            data["totale"]
            or 0
        ),
        "non_lette": (
            data["non_lette"]
            or 0
        ),
        "task_assegnati": (
            data["task_assegnati"]
            or 0
        ),
        "commenti": (
            data["commenti"]
            or 0
        ),
        "in_scadenza": (
            data["in_scadenza"]
            or 0
        ),
        "scadute": (
            data["scadute"]
            or 0
        ),
    }


def _tasks_with_current_assignee_access(queryset):
    """
    Limita i task a destinatari che hanno ancora accesso alla fase.

    Gli Admin LEF possono essere assegnatari anche senza una propria
    assegnazione; per ogni altro utente è richiesta un'assegnazione
    ATTIVA sulla stessa fase.
    """

    active_assignment = Assegnazione.objects.filter(
        consulente_id=OuterRef("assegnato_a_id"),
        fase_id=OuterRef("fase_id"),
        stato=Assegnazione.Stato.ATTIVA,
    )

    return (
        queryset
        .annotate(
            assegnatario_ha_accesso=Exists(active_assignment),
        )
        .annotate(
            assegnatario_resp_bu=Exists(
                UserBusinessUnit.objects.filter(
                    utente_id=OuterRef("assegnato_a_id"),
                    business_unit_id=OuterRef("commessa__business_unit_id"),
                    responsabile=True,
                    attiva=True,
                    utente__ruolo=User.Ruolo.RESPONSABILE_CONSULENZA,
                )
            ),
        )
        .filter(
            Q(assegnato_a__ruolo__in=(User.Ruolo.ADMIN, User.Ruolo.AMMINISTRAZIONE))
            | Q(assegnatario_ha_accesso=True)
            | Q(assegnatario_resp_bu=True)
        )
    )


# =========================================================
# TASK DA NOTIFICARE — PROSSIMA SCADENZA
# =========================================================


def tasks_due_soon_for_notifications(
    *,
    giorni=7,
    oggi=None,
):
    """
    Task non completati che scadono da oggi
    ai prossimi N giorni.

    Restituisce esclusivamente task con
    assegnatario attivo.
    """

    if oggi is None:
        oggi = timezone.localdate()

    if giorni < 0:
        giorni = 0

    limite = (
        oggi
        + timedelta(
            days=giorni
        )
    )

    queryset = (
        Task.objects
        .select_related(
            "assegnato_a",
            "fase",
            "commessa",
            "commessa__cliente",
        )
        .filter(
            assegnato_a__is_active=True,
            data_scadenza__isnull=False,
            data_scadenza__gte=oggi,
            data_scadenza__lte=limite,
        )
        .exclude(
            stato=Task.Stato.COMPLETATA
        )
    )

    return (
        _tasks_with_current_assignee_access(queryset)
        .order_by(
            "data_scadenza",
            "commessa__codice",
            "titolo",
        )
    )


# =========================================================
# TASK DA NOTIFICARE — SCADUTI
# =========================================================


def tasks_overdue_for_notifications(
    *,
    oggi=None,
):
    """
    Task non completati con data di scadenza
    precedente a oggi.
    """

    if oggi is None:
        oggi = timezone.localdate()

    queryset = (
        Task.objects
        .select_related(
            "assegnato_a",
            "fase",
            "commessa",
            "commessa__cliente",
        )
        .filter(
            assegnato_a__is_active=True,
            data_scadenza__isnull=False,
            data_scadenza__lt=oggi,
        )
        .exclude(
            stato=Task.Stato.COMPLETATA
        )
    )

    return (
        _tasks_with_current_assignee_access(queryset)
        .order_by(
            "data_scadenza",
            "commessa__codice",
            "titolo",
        )
    )
