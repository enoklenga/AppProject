from apps.projects.models import Commessa
from apps.projects.permissions import is_active_pm, is_active_pm_for_phase, is_active_team_member
from apps.accounts.access import can_view_portfolio

from .models import FaseCommessa


def can_view_fasi(user, commessa: Commessa) -> bool:
    return is_active_team_member(user, commessa) or can_view_portfolio(user)


def can_manage_fasi(user, commessa: Commessa) -> bool:
    if commessa.stato != Commessa.Stato.APERTA:
        return False
    return is_active_pm(user, commessa)


def can_edit_fase(user, fase: FaseCommessa) -> bool:
    # Una fase conclusa può essere modificata, purché la commessa sia aperta.
    return can_manage_fasi(user, fase.commessa)


def can_delete_fase(user, fase: FaseCommessa) -> bool:
    if fase.sistema:
        return False
    return can_manage_fasi(user, fase.commessa)
