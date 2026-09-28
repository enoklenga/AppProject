from apps.projects.models import Commessa
from apps.projects.permissions import is_active_pm, is_active_team_member, is_active_phase_member
from apps.accounts.access import can_view_all_documents

from .models import DocumentoCommessa


def can_view_documents(user, commessa: Commessa, fase=None, privato=False) -> bool:
    if not getattr(user, "is_authenticated", False):
        return False
    if getattr(user, "is_admin_lef", False):
        return True
    if privato:
        # Un documento privato è riservato agli Admin LEF, indipendentemente
        # dall'appartenenza al team della commessa/fase.
        return False
    if can_view_all_documents(user):
        return True
    if fase is not None:
        return is_active_phase_member(user, fase)
    return is_active_team_member(user, commessa)


def can_upload_document(user, commessa: Commessa, fase=None) -> bool:
    if not getattr(user, "is_authenticated", False):
        return False
    if getattr(user, "is_admin_lef", False):
        return True
    if commessa.stato != Commessa.Stato.APERTA:
        return False
    if fase is not None:
        return is_active_phase_member(user, fase)
    return is_active_team_member(user, commessa)


def can_delete_document(user, documento: DocumentoCommessa) -> bool:
    if not getattr(user, "is_authenticated", False):
        return False
    if getattr(user, "is_admin_lef", False):
        return True
    if documento.privato:
        # Un documento privato può essere eliminato solo da un Admin LEF.
        return False
    if documento.commessa.stato != Commessa.Stato.APERTA:
        return False
    if documento.fase_id:
        return is_active_phase_member(user, documento.fase)
    return is_active_team_member(user, documento.commessa)
