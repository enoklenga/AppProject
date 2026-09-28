"""Matrice autorizzativa centralizzata LEFTRACK.

Il ruolo organizzativo dell'utente resta distinto dal ruolo sulla singola
commessa (es. Project Manager). Le funzioni qui sotto governano gli accessi
trasversali di portafoglio e di amministrazione.
"""
from __future__ import annotations

from .models import User


def _authenticated(user) -> bool:
    return bool(user and getattr(user, "is_authenticated", False) and user.is_active)


def has_org_role(user, *roles: str) -> bool:
    return _authenticated(user) and getattr(user, "ruolo", None) in set(roles)


def can_manage_users(user) -> bool:
    return has_org_role(user, User.Ruolo.ADMIN)


def can_view_people(user) -> bool:
    return has_org_role(user, User.Ruolo.ADMIN, User.Ruolo.RESPONSABILE_CONSULENZA)


def can_view_skill_matrix(user) -> bool:
    return has_org_role(
        user,
        User.Ruolo.ADMIN,
        User.Ruolo.RESPONSABILE_CONSULENZA,
        User.Ruolo.DIREZIONE_GENERALE,
    )


def can_manage_skill_matrix(user) -> bool:
    return has_org_role(user, User.Ruolo.ADMIN)


def can_view_portfolio(user) -> bool:
    """Visibilità trasversale su clienti/commesse senza assegnazione."""
    return has_org_role(
        user,
        User.Ruolo.ADMIN,
        User.Ruolo.COMMERCIALE,
        User.Ruolo.DIREZIONE_GENERALE,
    )


def can_manage_clients(user) -> bool:
    return has_org_role(user, User.Ruolo.ADMIN, User.Ruolo.COMMERCIALE)


def can_manage_projects(user) -> bool:
    """Gestione anagrafica della commessa; non lifecycle/chiusura."""
    return has_org_role(user, User.Ruolo.ADMIN, User.Ruolo.COMMERCIALE)


def can_view_all_documents(user) -> bool:
    return can_view_portfolio(user)


def can_upload_portfolio_documents(user) -> bool:
    # Per ora il Commerciale/DG hanno accesso di lettura ai documenti di
    # portafoglio. Il caricamento resta nel Teamwork o all'Admin.
    return has_org_role(user, User.Ruolo.ADMIN)


def can_view_executive_dashboard(user) -> bool:
    return has_org_role(user, User.Ruolo.ADMIN, User.Ruolo.DIREZIONE_GENERALE)


def can_view_reports(user) -> bool:
    return has_org_role(
        user,
        User.Ruolo.ADMIN,
        User.Ruolo.DIREZIONE_GENERALE,
        User.Ruolo.AMMINISTRAZIONE,
    )


def can_view_finance_ledger(user) -> bool:
    """Lettura trasversale di ore e spese per il back office."""
    return has_org_role(user, User.Ruolo.ADMIN, User.Ruolo.AMMINISTRAZIONE)


def can_manage_finance(user) -> bool:
    """Tariffe, approvazioni e chiusura mensile."""
    return has_org_role(user, User.Ruolo.ADMIN, User.Ruolo.AMMINISTRAZIONE)


def can_view_planning_portfolio(user) -> bool:
    """Planning aggregato: responsabile consulenza e DG in lettura."""
    return has_org_role(
        user,
        User.Ruolo.ADMIN,
        User.Ruolo.RESPONSABILE_CONSULENZA,
        User.Ruolo.DIREZIONE_GENERALE,
    )


def can_view_audit(user) -> bool:
    return has_org_role(user, User.Ruolo.ADMIN, User.Ruolo.DIREZIONE_GENERALE)


def can_view_operational_details(user) -> bool:
    """Accesso personale/Teamwork alle sezioni operative."""
    return _authenticated(user) and (
        getattr(user, "is_admin_lef", False)
        or getattr(user, "is_risorsa_ingaggiabile", False)
    )


def can_view_tasks_portfolio(user) -> bool:
    # La DG può leggere le attività di portafoglio; il Commerciale rimane
    # volutamente sul perimetro cliente/commessa/handover/documenti.
    return has_org_role(user, User.Ruolo.ADMIN, User.Ruolo.DIREZIONE_GENERALE)


def can_view_teamwork_without_assignment(user) -> bool:
    return can_view_portfolio(user)
