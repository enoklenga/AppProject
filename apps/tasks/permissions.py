from apps.projects.models import Assegnazione
from apps.projects.permissions import is_active_phase_member, is_active_pm
from apps.projects.workflow import commessa_permette_nuovo_lavoro, fase_permette_nuovo_lavoro
from apps.accounts.access import can_view_tasks_portfolio



def _is_authenticated(user):
    return bool(user and getattr(user, "is_authenticated", False))


def is_active_pm_for_commessa(user, commessa):
    return is_active_pm(user, commessa)


def has_active_assignment(user, commessa):
    if not _is_authenticated(user):
        return False
    return Assegnazione.objects.filter(
        consulente=user,
        commessa=commessa,
        stato=Assegnazione.Stato.ATTIVA,
    ).exists()


def _can_supervise_phase(user, commessa, fase):
    if getattr(user, "is_admin_lef", False):
        return True
    return bool(is_active_pm(user, commessa) or is_active_phase_member(user, fase))


def can_create_task(user, commessa, fase=None):
    if not _is_authenticated(user) or not commessa_permette_nuovo_lavoro(commessa):
        return False
    if fase is not None and not fase_permette_nuovo_lavoro(fase):
        return False
    if getattr(user, "is_admin_lef", False):
        return True
    if fase is not None:
        return _can_supervise_phase(user, commessa, fase)
    return has_active_assignment(user, commessa)


def can_view_task(user, task):
    if not _is_authenticated(user):
        return False
    if can_view_tasks_portfolio(user):
        return True
    return _can_supervise_phase(user, task.commessa, task.fase)


def can_edit_task(user, task):
    if not _is_authenticated(user):
        return False
    if not commessa_permette_nuovo_lavoro(task.commessa):
        return False
    if not fase_permette_nuovo_lavoro(task.fase):
        return False
    return _can_supervise_phase(user, task.commessa, task.fase)


def can_update_task_status(user, task):
    return can_edit_task(user, task)


def can_comment_task(user, task):
    # La Direzione Generale ha accesso di sola lettura alle attività di
    # portafoglio: può aprire il dettaglio ma non intervenire nella
    # collaborazione operativa.
    if getattr(user, "is_direzione_generale", False):
        return False
    return can_view_task(user, task)


def can_delete_task(user, task):
    if not _is_authenticated(user):
        return False
    if not commessa_permette_nuovo_lavoro(task.commessa):
        return False
    if not fase_permette_nuovo_lavoro(task.fase):
        return False
    return _can_supervise_phase(user, task.commessa, task.fase)
