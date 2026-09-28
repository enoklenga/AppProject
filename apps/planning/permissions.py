from django.utils import timezone

from apps.phases.models import FaseCommessa
from apps.projects.models import Assegnazione
from apps.projects.permissions import is_active_phase_member, is_active_pm
from apps.projects.workflow import (
    commessa_permette_nuovo_lavoro,
    commessa_permette_operativita,
    fase_permette_nuovo_lavoro,
)

from .models import GiornoPianificato


def _can_supervise_assignment(user, assegnazione: Assegnazione) -> bool:
    """Admin e PM supervisionano trasversalmente; gli altri restano phase-scoped."""
    if getattr(user, "is_admin_lef", False):
        return True
    return bool(
        is_active_pm(user, assegnazione.commessa)
        or is_active_phase_member(user, assegnazione.fase)
    )


def can_create_planning(user, assegnazione: Assegnazione) -> bool:
    if not getattr(user, "is_authenticated", False):
        return False
    if assegnazione.stato != Assegnazione.Stato.ATTIVA:
        return False
    if not commessa_permette_nuovo_lavoro(assegnazione.commessa):
        return False
    if not fase_permette_nuovo_lavoro(assegnazione.fase):
        return False
    return _can_supervise_assignment(user, assegnazione)


def can_view_planning(user, pianificazione: GiornoPianificato) -> bool:
    if not getattr(user, "is_authenticated", False):
        return False
    return _can_supervise_assignment(user, pianificazione.assegnazione)


def can_edit_planning(user, pianificazione: GiornoPianificato) -> bool:
    if not getattr(user, "is_authenticated", False):
        return False
    # Una sessione risolta ha già alimentato il timesheet o appartiene allo
    # storico allineato/esente: non è più modificabile.
    if pianificazione.confermata:
        return False
    # Il passato resta congelato per tutti, Admin compreso.
    if pianificazione.data < timezone.localdate():
        return False
    assegnazione = pianificazione.assegnazione
    if assegnazione.stato != Assegnazione.Stato.ATTIVA:
        return False
    if not commessa_permette_nuovo_lavoro(assegnazione.commessa):
        return False
    if not fase_permette_nuovo_lavoro(assegnazione.fase):
        return False
    return _can_supervise_assignment(user, assegnazione)


def can_delete_planning(user, pianificazione: GiornoPianificato) -> bool:
    if not getattr(user, "is_authenticated", False):
        return False
    if pianificazione.confermata:
        return False
    if pianificazione.data < timezone.localdate():
        return False
    assegnazione = pianificazione.assegnazione
    if assegnazione.stato != Assegnazione.Stato.ATTIVA:
        return False
    if not commessa_permette_nuovo_lavoro(assegnazione.commessa):
        return False
    if not fase_permette_nuovo_lavoro(assegnazione.fase):
        return False
    return _can_supervise_assignment(user, assegnazione)


def can_confirm_planning(user, pianificazione: GiornoPianificato) -> bool:
    """Solo la risorsa pianificata può dichiarare conclusa la propria sessione."""
    if not getattr(user, "is_authenticated", False):
        return False
    if pianificazione.assegnazione.consulente_id != user.id:
        return False
    if pianificazione.assegnazione.stato != Assegnazione.Stato.ATTIVA:
        return False
    if not commessa_permette_operativita(pianificazione.assegnazione.commessa):
        return False
    if pianificazione.data > timezone.localdate():
        return False
    return not pianificazione.confermata
