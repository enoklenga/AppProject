from .models import Assegnazione, Commessa


def is_active_phase_member(user, fase) -> bool:
    """True quando l'utente appartiene alla squadra operativa della fase."""
    if not getattr(user, "is_authenticated", False):
        return False
    if getattr(user, "is_admin_lef", False):
        return True
    return Assegnazione.objects.filter(
        consulente=user,
        fase=fase,
        stato=Assegnazione.Stato.ATTIVA,
    ).exists()


def is_active_team_member(user, commessa: Commessa) -> bool:
    """Compatibilità: membro di almeno una fase attiva della commessa."""
    if not getattr(user, "is_authenticated", False):
        return False
    if getattr(user, "is_admin_lef", False):
        return True
    return Assegnazione.objects.filter(
        consulente=user,
        commessa=commessa,
        stato=Assegnazione.Stato.ATTIVA,
    ).exists()


def is_active_pm(user, commessa: Commessa) -> bool:
    """True quando l'utente è PM attivo in almeno una fase della commessa."""
    if not getattr(user, "is_authenticated", False):
        return False
    if getattr(user, "is_admin_lef", False):
        return True
    return Assegnazione.objects.filter(
        consulente=user,
        commessa=commessa,
        ruolo_commessa=Assegnazione.Ruolo.PROJECT_MANAGER,
        stato=Assegnazione.Stato.ATTIVA,
    ).exists()


def is_active_pm_for_phase(user, fase) -> bool:
    if not getattr(user, "is_authenticated", False):
        return False
    if getattr(user, "is_admin_lef", False):
        return True
    return Assegnazione.objects.filter(
        consulente=user,
        fase=fase,
        ruolo_commessa=Assegnazione.Ruolo.PROJECT_MANAGER,
        stato=Assegnazione.Stato.ATTIVA,
    ).exists()
