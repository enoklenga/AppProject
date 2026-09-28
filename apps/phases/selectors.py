from apps.projects.models import Assegnazione, Commessa
from apps.accounts.access import can_view_portfolio

from .models import FaseCommessa


def visible_commesse_for_user(user):
    """Commesse dove l'utente ha accesso al Teamwork (assegnazione attiva, o Admin)."""

    if not user.is_authenticated:
        return Commessa.objects.none()

    if user.is_admin_lef or can_view_portfolio(user):
        return Commessa.objects.all()

    commesse_ids = (
        Assegnazione.objects
        .filter(consulente=user, stato=Assegnazione.Stato.ATTIVA)
        .values_list("commessa_id", flat=True)
    )

    return Commessa.objects.filter(pk__in=commesse_ids)


def fasi_for_commessa(*, user, commessa):
    if not visible_commesse_for_user(user).filter(pk=commessa.pk).exists():
        return FaseCommessa.objects.none()

    return (
        FaseCommessa.objects
        .filter(commessa=commessa)
        .select_related("commessa", "creata_da")
    )


def manageable_commesse_for_phases(user):
    """Commesse su cui l'utente può creare/gestire fasi (PM o Admin)."""

    if not user.is_authenticated:
        return Commessa.objects.none()

    if user.is_admin_lef:
        return Commessa.objects.filter(stato=Commessa.Stato.APERTA)

    commesse_pm = (
        Assegnazione.objects
        .filter(
            consulente=user,
            ruolo_commessa=Assegnazione.Ruolo.PROJECT_MANAGER,
            stato=Assegnazione.Stato.ATTIVA,
        )
        .values_list("commessa_id", flat=True)
    )

    return Commessa.objects.filter(
        pk__in=commesse_pm,
        stato=Commessa.Stato.APERTA,
    )
