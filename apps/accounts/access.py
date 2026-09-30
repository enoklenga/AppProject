"""Matrice autorizzativa centralizzata LEFTRACK.

Tre livelli di gestione (revisione 29/09/2026, flusso TO-BE Consulenza):

* **Admin LEF** — gestisce la *piattaforma*: account, ruoli, nomina dei
  Responsabili di Business Unit, configurazione tecnica. Ha inoltre tutti i
  poteri gestionali su tutto il portafoglio.
* **Amministrazione** — *gestione globale*: tutto ciò che gestisce l'Admin
  (clienti, commesse, assegnazioni, tariffe, approvazioni, chiusure,
  pianificazione, attività, documenti, report, Business Unit) tranne la
  piattaforma.
* **Responsabile Business Unit** — gli stessi poteri gestionali dell'Admin ma
  *limitati al perimetro delle proprie BU*: commesse con ``business_unit`` in
  una BU gestita e persone membri di tali BU. Fuori dal perimetro agisce come
  normale risorsa (consulente o PM sulle commesse a cui è assegnato).

Il ruolo organizzativo resta distinto dal ruolo sulla singola commessa (PM).
Tutti i controlli di "supervisione" (prima ``user.is_admin_lef``) devono
passare da ``can_manage_commessa`` / ``commesse_in_scope`` /
``can_manage_person`` / ``persone_in_scope``.
"""
from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db.models import Q
from django.utils import timezone

from .models import BusinessUnit, User, UserBusinessUnit

# ---------------------------------------------------------------------------
# Cache del perimetro BU per richiesta.
# Il set delle BU gestite viene memorizzato sull'istanza utente insieme a una
# "versione" globale che i segnali incrementano a ogni modifica di BU,
# appartenenze o ruolo: nessun dato vecchio anche nei test.
# ---------------------------------------------------------------------------
_SCOPE_VERSION = {"value": 0}
_CACHE_ATTR = "_lef_bu_scope_cache"


def invalidate_scope_cache(*args, **kwargs) -> None:
    _SCOPE_VERSION["value"] += 1


def uuid_valido(valore):
    """Restituisce l'UUID normalizzato o None (parametri GET manipolati → niente 500)."""
    import uuid

    try:
        return str(uuid.UUID(str(valore))) if valore else None
    except (TypeError, ValueError, AttributeError):
        return None


def membership_current_q(prefix: str = "") -> Q:
    """Filtro riusabile per appartenenze BU effettivamente valide oggi.

    ``attiva`` da solo non basta: una membership con data futura o gia scaduta
    non deve conferire visibilita, poteri di gestione o abilitazione PM.
    ``prefix`` consente di usare lo stesso criterio anche attraverso relazioni
    reverse (es. ``membership_business_unit__``).
    """
    oggi = timezone.localdate()
    return (
        Q(**{f"{prefix}attiva": True})
        & (Q(**{f"{prefix}data_inizio__isnull": True}) | Q(**{f"{prefix}data_inizio__lte": oggi}))
        & (Q(**{f"{prefix}data_fine__isnull": True}) | Q(**{f"{prefix}data_fine__gte": oggi}))
    )


def membership_is_current(membership) -> bool:
    """Controllo in-memory coerente con ``membership_current_q``."""
    if membership is None or not getattr(membership, "attiva", False):
        return False
    oggi = timezone.localdate()
    inizio = getattr(membership, "data_inizio", None)
    fine = getattr(membership, "data_fine", None)
    return (inizio is None or inizio <= oggi) and (fine is None or fine >= oggi)


def _authenticated(user) -> bool:
    return bool(user and getattr(user, "is_authenticated", False) and user.is_active)


def has_org_role(user, *roles: str) -> bool:
    return _authenticated(user) and getattr(user, "ruolo", None) in set(roles)


# ---------------------------------------------------------------------------
# Livelli di gestione
# ---------------------------------------------------------------------------
def is_platform_admin(user) -> bool:
    return has_org_role(user, User.Ruolo.ADMIN)


def is_global_manager(user) -> bool:
    """Admin o Amministrazione: gestione su tutto il portafoglio."""
    return has_org_role(user, User.Ruolo.ADMIN, User.Ruolo.AMMINISTRAZIONE)


def managed_business_unit_ids(user) -> frozenset:
    """ID delle BU attive di cui l'utente è Responsabile attivo."""
    if not has_org_role(user, User.Ruolo.RESPONSABILE_CONSULENZA):
        return frozenset()
    cache = getattr(user, _CACHE_ATTR, None)
    if cache and cache[0] == _SCOPE_VERSION["value"]:
        return cache[1]
    ids = frozenset(
        UserBusinessUnit.objects.filter(
            membership_current_q(),
            utente_id=user.pk,
            responsabile=True,
            business_unit__attiva=True,
        ).values_list("business_unit_id", flat=True)
    )
    try:
        setattr(user, _CACHE_ATTR, (_SCOPE_VERSION["value"], ids))
    except AttributeError:
        pass
    return ids


def is_bu_manager(user) -> bool:
    return bool(managed_business_unit_ids(user))


def is_manager(user) -> bool:
    """Profilo con interfaccia di gestione (Admin, Amministrazione, Resp. BU)."""
    return is_global_manager(user) or is_bu_manager(user)


# ---------------------------------------------------------------------------
# Perimetri
# ---------------------------------------------------------------------------
def commesse_in_scope(user):
    """Commesse gestibili dall'utente (tutte, quelle della sua BU o nessuna)."""
    from apps.projects.models import Commessa

    if is_global_manager(user):
        return Commessa.objects.all()
    ids = managed_business_unit_ids(user)
    if ids:
        return Commessa.objects.filter(business_unit_id__in=ids)
    return Commessa.objects.none()


def can_manage_commessa(user, commessa) -> bool:
    if commessa is None:
        return is_global_manager(user)
    if is_global_manager(user):
        return True
    ids = managed_business_unit_ids(user)
    return bool(ids) and getattr(commessa, "business_unit_id", None) in ids


def commesse_visibili(user):
    """Commesse consultabili nelle anagrafiche.

    Profili di portafoglio (Admin, Amministrazione, Commerciale, DG): tutte.
    Responsabile BU: quelle delle proprie BU. Altri: nessuna (usano Teamwork).
    """
    from apps.projects.models import Commessa

    if can_view_portfolio(user):
        return Commessa.objects.all()
    return commesse_in_scope(user)


def can_edit_commessa_anagrafica(user, commessa) -> bool:
    """Modifica dell'anagrafica: gestione nel perimetro o Commerciale."""
    return has_org_role(user, User.Ruolo.COMMERCIALE) or can_manage_commessa(user, commessa)


def can_manage_fase(user, fase) -> bool:
    """Come ``can_manage_commessa`` ma senza caricare la commessa se non serve."""
    if is_global_manager(user):
        return True
    ids = managed_business_unit_ids(user)
    if not ids or fase is None:
        return False
    return getattr(fase.commessa, "business_unit_id", None) in ids


def persone_in_scope(user):
    """Persone gestibili: tutte (gestione globale) o i membri delle BU gestite."""
    if is_global_manager(user):
        return User.objects.all()
    ids = managed_business_unit_ids(user)
    if ids:
        return User.objects.filter(
            membership_current_q("membership_business_unit__"),
            membership_business_unit__business_unit_id__in=ids,
        ).distinct()
    return User.objects.none()


def can_manage_person(user, persona) -> bool:
    if is_global_manager(user):
        return True
    ids = managed_business_unit_ids(user)
    if not ids or persona is None:
        return False
    return UserBusinessUnit.objects.filter(
        membership_current_q(),
        utente_id=persona.pk,
        business_unit_id__in=ids,
    ).exists()


def business_units_in_scope(user):
    if is_global_manager(user) or has_org_role(user, User.Ruolo.DIREZIONE_GENERALE):
        return BusinessUnit.objects.all()
    ids = managed_business_unit_ids(user)
    if ids:
        return BusinessUnit.objects.filter(pk__in=ids)
    return BusinessUnit.objects.none()


def perimetro_business_unit(user, business_unit_richiesta=None):
    """Perimetro BU per dashboard, report e consuntivi.

    Restituisce ``None`` (nessun limite) per la gestione globale e la DG
    quando non filtrano; altrimenti una tupla di id BU. Il Responsabile BU
    è sempre limitato alle proprie BU, anche se chiede un'altra BU.
    """
    richiesta = None
    if business_unit_richiesta:
        try:
            richiesta = BusinessUnit.objects.filter(pk=business_unit_richiesta).values_list("pk", flat=True).first()
        except (ValueError, TypeError, ValidationError):  # UUID non valido
            richiesta = None
    if is_global_manager(user) or has_org_role(user, User.Ruolo.DIREZIONE_GENERALE):
        return (richiesta,) if richiesta else None
    gestite = managed_business_unit_ids(user)
    if richiesta and richiesta in gestite:
        return (richiesta,)
    return tuple(gestite)


# ---------------------------------------------------------------------------
# Piattaforma (solo Admin)
# ---------------------------------------------------------------------------
def can_manage_users(user) -> bool:
    """Account, ruoli, inviti, attivazioni."""
    return is_platform_admin(user)


def can_designate_bu_managers(user) -> bool:
    """Nominare/revocare un Responsabile BU equivale a concedere poteri."""
    return is_platform_admin(user)


# ---------------------------------------------------------------------------
# Business Unit
# ---------------------------------------------------------------------------
def can_view_business_units(user) -> bool:
    return is_manager(user) or has_org_role(user, User.Ruolo.DIREZIONE_GENERALE)


def can_edit_business_units(user) -> bool:
    """Anagrafica BU (nome, codice, descrizione, stato)."""
    return is_global_manager(user)


def can_manage_business_unit(user, business_unit) -> bool:
    """Gestione della singola BU: membri, abilitazione PM, commesse."""
    if business_unit is None:
        return False
    if is_global_manager(user):
        return True
    return business_unit.pk in managed_business_unit_ids(user)


def managed_business_units(user):
    """BU gestibili dall'utente (compatibilità con il codice esistente)."""
    if is_global_manager(user):
        return BusinessUnit.objects.filter(attiva=True)
    return BusinessUnit.objects.filter(pk__in=managed_business_unit_ids(user))


def business_units_for_user(user):
    """Business Unit attive a cui l'utente appartiene."""
    if not _authenticated(user):
        return BusinessUnit.objects.none()
    return BusinessUnit.objects.filter(
        membership_current_q("membership__"),
        membership__utente=user,
        attiva=True,
    ).distinct()


def can_be_project_manager(user, business_unit) -> bool:
    if not _authenticated(user):
        return False
    if getattr(user, "is_admin_lef", False):
        return True
    if business_unit is None:
        return getattr(user, "is_risorsa_ingaggiabile", False)
    return UserBusinessUnit.objects.filter(
        membership_current_q(),
        utente=user,
        business_unit=business_unit,
        puo_essere_pm=True,
    ).exists()


# ---------------------------------------------------------------------------
# Persone e competenze
# ---------------------------------------------------------------------------
def can_view_people(user) -> bool:
    return is_manager(user)


def can_view_skill_matrix(user) -> bool:
    return is_manager(user) or has_org_role(user, User.Ruolo.DIREZIONE_GENERALE)


def can_manage_skill_matrix(user) -> bool:
    """Valutazione delle competenze (sulle persone nel proprio perimetro)."""
    return is_manager(user)


def can_manage_skill_catalog(user) -> bool:
    return is_global_manager(user)


# ---------------------------------------------------------------------------
# Portafoglio: clienti, commesse, assegnazioni, tariffe
# ---------------------------------------------------------------------------
def can_view_portfolio(user) -> bool:
    """Visibilità trasversale su clienti/commesse senza assegnazione."""
    return is_global_manager(user) or has_org_role(
        user, User.Ruolo.COMMERCIALE, User.Ruolo.DIREZIONE_GENERALE
    )


def can_view_reference_portfolio(user) -> bool:
    """Anagrafiche cliente/commessa consultabili (commesse filtrate per perimetro)."""
    return can_view_portfolio(user) or is_bu_manager(user)


def can_manage_clients(user) -> bool:
    return is_manager(user) or has_org_role(user, User.Ruolo.COMMERCIALE)


def can_manage_projects(user) -> bool:
    """Creazione/modifica anagrafica commessa (Resp. BU: solo nella propria BU)."""
    return is_manager(user) or has_org_role(user, User.Ruolo.COMMERCIALE)


def can_manage_project_lifecycle(user, commessa) -> bool:
    """Apertura/chiusura tecnica e workflow della commessa."""
    return can_manage_commessa(user, commessa)


def can_view_assignments_register(user) -> bool:
    return is_manager(user)


def can_manage_assignments(user) -> bool:
    return is_manager(user)


# ---------------------------------------------------------------------------
# Controllo, economico, back office
# ---------------------------------------------------------------------------
def can_use_backoffice_control(user) -> bool:
    """Importazioni massive e promemoria automatici (tutta l'azienda)."""
    return is_global_manager(user)


def can_close_periods(user) -> bool:
    """La chiusura del mese è aziendale, non per BU."""
    return is_global_manager(user)


def can_view_executive_dashboard(user) -> bool:
    return is_manager(user) or has_org_role(user, User.Ruolo.DIREZIONE_GENERALE)


def can_view_reports(user) -> bool:
    return is_manager(user) or has_org_role(user, User.Ruolo.DIREZIONE_GENERALE)


def can_view_finance_ledger(user) -> bool:
    """Lettura di ore e spese di altri (Resp. BU: solo commesse della BU)."""
    return is_manager(user)


def can_manage_finance(user) -> bool:
    """Tariffe e approvazioni (Resp. BU: solo commesse della BU)."""
    return is_manager(user)


def can_view_planning_portfolio(user) -> bool:
    return is_manager(user) or has_org_role(user, User.Ruolo.DIREZIONE_GENERALE)


def can_view_audit(user) -> bool:
    return is_global_manager(user) or has_org_role(user, User.Ruolo.DIREZIONE_GENERALE)


def can_view_operational_details(user) -> bool:
    """Accesso alle sezioni operative (personali, Teamwork o di gestione)."""
    return _authenticated(user) and (
        is_manager(user) or getattr(user, "is_risorsa_ingaggiabile", False)
    )


def can_view_tasks_portfolio(user) -> bool:
    return is_manager(user) or has_org_role(user, User.Ruolo.DIREZIONE_GENERALE)


def can_view_all_documents(user) -> bool:
    return can_view_portfolio(user)


def can_upload_portfolio_documents(user) -> bool:
    return is_manager(user)


def can_view_teamwork_without_assignment(user) -> bool:
    return can_view_portfolio(user)
