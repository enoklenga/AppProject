from apps.projects.models import Assegnazione, Commessa
from django.db.models import Q

from apps.accounts.access import (
    can_view_portfolio,
    is_global_manager,
    managed_business_unit_ids,
)

from .models import FaseCommessa


def visible_commesse_for_user(user):
    """Commesse dove l'utente ha accesso al Teamwork (assegnazione attiva, o Admin)."""

    if not user.is_authenticated:
        return Commessa.objects.none()

    if is_global_manager(user) or can_view_portfolio(user):
        return Commessa.objects.all()

    commesse_ids = (
        Assegnazione.objects
        .filter(consulente=user, stato=Assegnazione.Stato.ATTIVA)
        .values_list("commessa_id", flat=True)
    )
    filtro = Q(pk__in=commesse_ids)
    bu_gestite = managed_business_unit_ids(user)
    if bu_gestite:
        filtro |= Q(business_unit_id__in=bu_gestite)
    return Commessa.objects.filter(filtro).distinct()


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

    if is_global_manager(user):
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

    filtro = Q(pk__in=commesse_pm)
    bu_gestite = managed_business_unit_ids(user)
    if bu_gestite:
        filtro |= Q(business_unit_id__in=bu_gestite)
    return Commessa.objects.filter(filtro, stato=Commessa.Stato.APERTA).distinct()
