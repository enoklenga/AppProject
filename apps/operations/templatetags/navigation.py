from __future__ import annotations

from typing import Any

from django import template
from django.core.exceptions import ValidationError
from django.urls import NoReverseMatch, resolve, reverse

from apps.accounts.access import can_view_portfolio, can_view_tasks_portfolio
from apps.projects.models import Assegnazione

register = template.Library()


SECTION_CONFIG: dict[str, dict[str, str]] = {
    "home": {
        "label": "Home",
        "root": "home",
        "back_label": "Torna alla Home",
    },
    "ore": {
        "label": "Ore",
        "root": "timesheets:ore-list",
        "back_label": "Torna alle ore",
    },
    "spese": {
        "label": "Spese",
        "root": "timesheets:spesa-list",
        "back_label": "Torna alle spese",
    },
    "pianificazione": {
        "label": "Pianificazione",
        "root": "planning:pianificazione-list",
        "back_label": "Torna alla pianificazione",
    },
    "mie_attivita": {
        "label": "Le mie attività",
        "root": "tasks:my-task-list",
        "back_label": "Torna alle mie attività",
    },
    "attivita": {
        "label": "Attività",
        "root": "tasks:task-list",
        "back_label": "Torna alle attività",
    },
    "consulenti": {
        "label": "Persone e ruoli",
        "root": "accounts:consulente-list",
        "back_label": "Torna a persone e ruoli",
    },
    "skill-matrix": {
        "label": "Skill Matrix",
        "root": "accounts:skill-matrix",
        "back_label": "Torna alla Skill Matrix",
    },
    "clienti": {
        "label": "Clienti",
        "root": "projects:cliente-list",
        "back_label": "Torna ai clienti",
    },
    "commesse": {
        "label": "Commesse",
        "root": "projects:commessa-list",
        "back_label": "Torna alle commesse",
    },
    "assegnazioni": {
        "label": "Assegnazioni",
        "root": "projects:assegnazione-list",
        "back_label": "Torna alle assegnazioni",
    },
    "tariffe": {
        "label": "Tariffe",
        "root": "projects:tariffa-list",
        "back_label": "Torna alle tariffe",
    },
    "dashboard": {
        "label": "Dashboard",
        "root": "operations:dashboard-admin",
        "back_label": "Torna alla Dashboard",
    },
    "periodi": {
        "label": "Chiusura mese",
        "root": "operations:periodo-detail",
        "back_label": "Torna alla chiusura mese",
    },
    "promemoria": {
        "label": "Promemoria",
        "root": "operations:promemoria",
        "back_label": "Torna ai promemoria",
    },
    "importazioni": {
        "label": "Importazioni",
        "root": "operations:importazione-list",
        "back_label": "Torna alle importazioni",
    },
    "audit": {
        "label": "Audit",
        "root": "operations:audit-list",
        "back_label": "Torna all’audit",
    },
    "report": {
        "label": "Report",
        "root": "operations:report-mensile",
        "back_label": "Torna al report",
    },

    "notifiche": {
        "label": "Notifiche",
        "root": "notifications:notification-list",
        "back_label": "Torna alle notifiche",
    },

    "documenti": {
        "label": "Documenti",
        "root": "documents:document-list",
        "back_label": "Torna ai documenti",
    },

    "fasi": {
        "label": "Fasi",
        "root": "phases:fase-list",
        "back_label": "Torna alle fasi",
    },
}


PAGE_LABELS: dict[str, str] = {
    "home": "Home",

    "timesheets:ore-list": "Ore",
    "timesheets:ore-create": "Inserisci ore",
    "timesheets:ore-update": "Modifica ore",
    "timesheets:ore-delete": "Elimina ore",

    "timesheets:spesa-list": "Spese",
    "timesheets:spesa-create": "Inserisci spesa",
    "timesheets:spesa-update": "Modifica spesa",
    "timesheets:spesa-delete": "Elimina spesa",

    "planning:pianificazione-list": "Pianificazione",
    "planning:pianificazione-create": "Pianifica ore",
    "planning:pianificazione-update": "Modifica pianificazione",
    "planning:pianificazione-delete": "Elimina pianificazione",

    "accounts:consulente-list": "Persone e ruoli",
    "accounts:consulente-create": "Nuovo consulente",
    "accounts:consulente-update": "Modifica consulente",
    "accounts:consulente-toggle-active": "Cambia stato consulente",
    "accounts:consulente-resend-invite": "Reinvia invito",
    "accounts:skill-list": "Catalogo skill",
    "accounts:skill-create": "Nuova skill",
    "accounts:skill-update": "Modifica skill",
    "accounts:skill-matrix": "Skill Matrix",
    "accounts:skill-matrix-user-update": "Valutazione skill",

    "projects:cliente-list": "Clienti",
    "projects:cliente-create": "Nuovo cliente",
    "projects:cliente-update": "Modifica cliente",
    "projects:cliente-toggle-active": "Cambia stato cliente",

    "projects:commessa-list": "Commesse",
    "projects:commessa-create": "Nuova commessa",
    "projects:commessa-update": "Modifica commessa",
    "projects:commessa-toggle-state": "Cambia stato commessa",
    "projects:commessa-handover": "Handover",
    "projects:commessa-workflow": "Workflow",
    "projects:commessa-teamwork": "Teamwork",

    "projects:assegnazione-list": "Assegnazioni",
    "projects:assegnazione-create": "Nuova assegnazione",
    "projects:assegnazione-update": "Modifica assegnazione",
    "projects:assegnazione-toggle-state": "Cambia stato assegnazione",

    "projects:tariffa-list": "Tariffe",
    "projects:tariffa-create": "Nuova tariffa",

    "operations:dashboard-admin": "Dashboard economica",
    "operations:dashboard-pm": "Dashboard di progetto",
    "operations:periodo-detail": "Chiusura mese",
    "operations:promemoria": "Promemoria",
    "operations:importazione-list": "Importazioni",
    "operations:importazione-create": "Nuova importazione",
    "operations:importazione-detail": "Dettaglio importazione",
    "operations:importazione-commit": "Conferma importazione",
    "operations:audit-list": "Audit",
    "operations:report-mensile": "Report mensile",

    "password_change": "Cambia password",

    "tasks:my-task-list": "Le mie attività",
    "tasks:task-list": "Attività",
    "tasks:task-create": "Nuova attività",
    "tasks:task-detail": "Dettaglio attività",
    "tasks:task-update": "Modifica attività",
    "tasks:task-status-update": "Aggiorna stato attività",
    "tasks:task-comment-create": "Aggiungi commento",
    "tasks:task-delete": "Elimina attività",
    "notifications:notification-list": "Notifiche",
    "notifications:notification-open": "Notifica",
    "notifications:notification-mark-read": "Segna notifica come letta",
    "notifications:notification-mark-unread": "Segna notifica come non letta",
    "notifications:notification-mark-all-read": "Segna tutte come lette",
    "notifications:preferences": "Preferenze notifiche",

    "documents:document-list": "Documenti",
    "documents:document-upload": "Carica documento",
    "documents:document-download": "Scarica documento",
    "documents:document-delete": "Elimina documento",

    "phases:fase-list": "Fasi",
    "phases:fase-create": "Nuova fase",
    "phases:fase-update": "Modifica fase",
    "phases:fase-delete": "Elimina fase",
}


def _route_name(match: Any) -> str:
    if match is None:
        return ""

    namespace = (
        getattr(
            match,
            "namespace",
            "",
        )
        or ""
    )

    url_name = (
        getattr(
            match,
            "url_name",
            "",
        )
        or ""
    )

    if namespace:
        return f"{namespace}:{url_name}"

    return url_name


def _match_from_context(
    context: template.Context,
):
    request = context.get(
        "request"
    )

    if request is None:
        return None

    match = getattr(
        request,
        "resolver_match",
        None,
    )

    if match is not None:
        return match

    try:
        return resolve(
            request.path_info
        )

    except Exception:
        return None


def _can_manage_tasks(user) -> bool:
    """
    True per:

    - Admin LEF
    - PM con almeno una commessa attiva

    False per il consulente standard.
    """

    if not user:
        return False

    if not getattr(
        user,
        "is_authenticated",
        False,
    ):
        return False

    if getattr(
        user,
        "is_admin_lef",
        False,
    ):
        return True

    if can_view_tasks_portfolio(user):
        return True

    return (
        Assegnazione.objects
        .filter(
            consulente=user,
            ruolo_commessa=(
                Assegnazione
                .Ruolo
                .PROJECT_MANAGER
            ),
            stato=(
                Assegnazione
                .Stato
                .ATTIVA
            ),
        )
        .exists()
    )


def section_for_match(
    match: Any,
    user=None,
) -> str:
    route = _route_name(
        match
    )

    namespace = (
        getattr(
            match,
            "namespace",
            "",
        )
        or ""
    )

    url_name = (
        getattr(
            match,
            "url_name",
            "",
        )
        or ""
    )

    if route == "home":
        return "home"

    # =====================================================
    # TIMESHEET
    # =====================================================

    if namespace == "timesheets":

        if url_name.startswith(
            "ore-"
        ):
            return "ore"

        if url_name.startswith(
            "spesa-"
        ):
            return "spese"

    # =====================================================
    # PIANIFICAZIONE
    # =====================================================

    if namespace == "planning":
        return "pianificazione"

    # =====================================================
    # ATTIVITÀ
    # =====================================================

    if namespace == "tasks":

        # La pagina personale appartiene sempre
        # alla sezione "Le mie attività".
        if url_name == "my-task-list":
            return "mie_attivita"

        # Le pagine che possono essere utilizzate
        # anche dal consulente devono tornare alla
        # sua area personale se non è Admin/PM.
        if url_name in {
            "task-detail",
            "task-status-update",
            "task-comment-create",
        }:
            if not _can_manage_tasks(
                user
            ):
                return "mie_attivita"

        # Creazione, modifica, eliminazione e
        # lista gestionale appartengono invece
        # alla sezione Attività.
        return "attivita"
    
    if namespace == "notifications":
        return "notifiche"

    if namespace == "documents":
        return "documenti"

    if namespace == "phases":
        return "fasi"

    # =====================================================
    # CONSULENTI
    # =====================================================

    if namespace == "accounts" and url_name.startswith("skill-"):
        return "skill-matrix"

    if (
        namespace == "accounts"
        and url_name.startswith(
            "consulente-"
        )
    ):
        return "consulenti"

    # =====================================================
    # PROGETTI
    # =====================================================

    if namespace == "projects":

        if url_name.startswith(
            "cliente-"
        ):
            return "clienti"

        if url_name.startswith(
            "commessa-"
        ):
            return "commesse"

        if url_name.startswith(
            "assegnazione-"
        ):
            return "assegnazioni"

        if url_name.startswith(
            "tariffa-"
        ):
            return "tariffe"

    # =====================================================
    # OPERATIONS
    # =====================================================

    if namespace == "operations":

        if url_name.startswith(
            "dashboard-"
        ):
            return "dashboard"

        if url_name.startswith(
            "periodo-"
        ):
            return "periodi"

        if url_name == "promemoria":
            return "promemoria"

        if url_name.startswith(
            "importazione-"
        ):
            return "importazioni"

        if url_name.startswith(
            "audit-"
        ):
            return "audit"

        if url_name.startswith(
            "report-"
        ):
            return "report"

    return ""


def _safe_reverse(
    name: str,
) -> str:
    try:
        return reverse(
            name
        )

    except NoReverseMatch:
        return ""


def build_navigation_data(
    match: Any,
    user=None,
    request=None,
) -> dict[str, Any]:

    route = _route_name(
        match
    )

    section = section_for_match(
        match,
        user=user,
    )

    home_url = _safe_reverse(
        "home"
    )

    # =====================================================
    # TEAMWORK — spazio operativo contestuale
    # =====================================================
    if route == "projects:commessa-teamwork":
        is_admin = bool(getattr(user, "is_admin_lef", False))
        is_portfolio = can_view_portfolio(user)
        commessa_id = getattr(match, "kwargs", {}).get("pk") if match else None
        teamwork_url = (
            reverse(
                "projects:commessa-teamwork",
                kwargs={"pk": commessa_id},
            )
            if commessa_id
            else ""
        )

        if is_admin or is_portfolio:
            back_url = _safe_reverse("projects:commessa-list")
            back_label = "Torna alle commesse"
            breadcrumbs = [
                {"label": "Home", "url": home_url},
                {"label": "Commesse", "url": back_url},
                {"label": "Teamwork", "url": ""},
            ]
        else:
            back_url = home_url
            back_label = "Torna alla Home"
            breadcrumbs = [
                {"label": "Home", "url": home_url},
                {"label": "Teamwork", "url": ""},
            ]

        return {
            "section": "teamwork",
            "current_label": "Teamwork",
            "breadcrumbs": breadcrumbs,
            "back_url": back_url,
            "back_label": back_label,
        }

    # Handover e workflow sono pagine di gestione interne al Teamwork.
    # Non devono mai rimandare il PM alla lista amministrativa delle commesse.
    teamwork_management_routes = {
        "projects:commessa-handover": "Handover",
        "projects:commessa-workflow": "Workflow",
    }

    if route in teamwork_management_routes:
        commessa_id = getattr(match, "kwargs", {}).get("pk") if match else None
        teamwork_url = (
            reverse(
                "projects:commessa-teamwork",
                kwargs={"pk": commessa_id},
            )
            if commessa_id
            else ""
        )
        current_label = teamwork_management_routes[route]
        return {
            "section": "teamwork",
            "current_label": current_label,
            "breadcrumbs": [
                {"label": "Home", "url": home_url},
                {"label": "Teamwork", "url": teamwork_url},
                {"label": current_label, "url": ""},
            ],
            "back_url": teamwork_url,
            "back_label": "Torna al Teamwork",
        }

    # Se una sezione operativa viene aperta dal Teamwork con il filtro
    # della commessa, la navigazione deve mantenere il contesto e tornare
    # al Teamwork invece che alla Home/sezione globale.
    teamwork_child_routes = {
        "planning:pianificazione-list",
        "planning:pianificazione-create",
        "planning:pianificazione-update",
        "planning:pianificazione-delete",
        "tasks:task-list",
        "tasks:task-create",
        "tasks:task-detail",
        "tasks:task-update",
        "documents:document-list",
        "documents:document-upload",
        "phases:fase-list",
        "phases:fase-create",
        "phases:fase-update",
        "phases:fase-delete",
    }

    commessa_context_id = (
        request.GET.get("commessa")
        if request is not None
        else None
    )

    # Alcuni link contestuali (es. il Calendario di una singola fase nel
    # Teamwork) passano solo "fase" senza "commessa": risaliamo comunque
    # alla commessa così il ritorno al Teamwork funziona anche in quel caso.
    if not commessa_context_id and request is not None:
        fase_context_id = request.GET.get("fase")
        if fase_context_id:
            try:
                from apps.phases.models import FaseCommessa
                commessa_context_id = (
                    FaseCommessa.objects
                    .filter(pk=fase_context_id)
                    .values_list("commessa_id", flat=True)
                    .first()
                )
            except (ValueError, ValidationError):
                commessa_context_id = None

    if route in teamwork_child_routes and commessa_context_id:
        try:
            teamwork_url = reverse(
                "projects:commessa-teamwork",
                kwargs={"pk": commessa_context_id},
            )
        except NoReverseMatch:
            teamwork_url = ""

        current_label = PAGE_LABELS.get(route, "Teamwork")
        return {
            "section": "teamwork",
            "current_label": current_label,
            "breadcrumbs": [
                {"label": "Home", "url": home_url},
                {"label": "Teamwork", "url": teamwork_url},
                {"label": current_label, "url": ""},
            ],
            "back_url": teamwork_url,
            "back_label": "Torna al Teamwork",
        }

    if route == "home":
        return {
            "section": "home",
            "current_label": "Home",
            "breadcrumbs": [
                {
                    "label": "Home",
                    "url": "",
                }
            ],
            "back_url": "",
            "back_label": "",
        }

    if section:
        config = SECTION_CONFIG[
            section
        ]

        # Le due dashboard sono pagine
        # principali alternative.
        if (
            route
            == "operations:dashboard-pm"
        ):
            section_root = (
                "operations:dashboard-pm"
            )

        else:
            section_root = config[
                "root"
            ]

        section_url = _safe_reverse(
            section_root
        )

        current_label = (
            PAGE_LABELS.get(
                route,
                config["label"],
            )
        )

        if route == "operations:dashboard-admin" and getattr(
            user, "is_direzione_generale", False
        ):
            current_label = "Dashboard direzionale"

        if route == section_root:

            breadcrumbs = [
                {
                    "label": "Home",
                    "url": home_url,
                },
                {
                    "label": current_label,
                    "url": "",
                },
            ]

            back_url = home_url
            back_label = (
                "Torna alla Home"
            )

        else:

            breadcrumbs = [
                {
                    "label": "Home",
                    "url": home_url,
                },
                {
                    "label": config[
                        "label"
                    ],
                    "url": section_url,
                },
                {
                    "label": current_label,
                    "url": "",
                },
            ]

            back_url = section_url
            back_label = config[
                "back_label"
            ]

        return {
            "section": section,
            "current_label": current_label,
            "breadcrumbs": breadcrumbs,
            "back_url": back_url,
            "back_label": back_label,
        }

    current_label = (
        PAGE_LABELS.get(
            route
        )
    )

    if current_label:
        return {
            "section": "",
            "current_label": current_label,
            "breadcrumbs": [
                {
                    "label": "Home",
                    "url": home_url,
                },
                {
                    "label": current_label,
                    "url": "",
                },
            ],
            "back_url": home_url,
            "back_label": (
                "Torna alla Home"
            ),
        }

    return {
        "section": "",
        "current_label": "",
        "breadcrumbs": [],
        "back_url": "",
        "back_label": "",
    }


@register.simple_tag(
    takes_context=True
)
def active_section(
    context: template.Context,
) -> str:

    request = context.get(
        "request"
    )

    user = getattr(
        request,
        "user",
        None,
    )

    return section_for_match(
        _match_from_context(
            context
        ),
        user=user,
    )


@register.simple_tag(
    takes_context=True
)
def navigation_data(
    context: template.Context,
) -> dict[str, Any]:

    request = context.get(
        "request"
    )

    user = getattr(
        request,
        "user",
        None,
    )

    return build_navigation_data(
        _match_from_context(
            context
        ),
        user=user,
        request=request,
    )


@register.simple_tag
def has_pm_access(
    user,
) -> bool:
    """
    Mostra la Dashboard PM solo agli utenti
    che gestiscono almeno una commessa tramite
    un'assegnazione attiva.

    L'Admin dispone della dashboard economica
    dedicata e non viene classificato come PM.
    """

    if not user:
        return False

    if not getattr(
        user,
        "is_authenticated",
        False,
    ):
        return False

    if getattr(
        user,
        "is_admin_lef",
        False,
    ):
        return False

    return (
        Assegnazione.objects
        .filter(
            consulente=user,
            ruolo_commessa=(
                Assegnazione
                .Ruolo
                .PROJECT_MANAGER
            ),
            stato=(
                Assegnazione
                .Stato
                .ATTIVA
            ),
        )
        .exists()
    )