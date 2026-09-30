from django.db.models import Q

from apps.accounts.access import managed_business_unit_ids
from apps.projects.models import Assegnazione, Commessa


def commesse_gestite_ids(user):
    """Commesse gestite: PM attivo o commesse delle BU di cui è Responsabile."""
    if not user or not user.is_authenticated:
        return Commessa.objects.none().values_list("id", flat=True)

    filtro = Q(
        assegnazioni__consulente=user,
        assegnazioni__ruolo_commessa=Assegnazione.Ruolo.PROJECT_MANAGER,
        assegnazioni__stato=Assegnazione.Stato.ATTIVA,
    )
    bu_gestite = managed_business_unit_ids(user)
    if bu_gestite:
        filtro |= Q(business_unit_id__in=bu_gestite)
    return Commessa.objects.filter(filtro).values_list("id", flat=True).distinct()


def filtro_visibilita_assegnazioni(user) -> Q:
    return Q(consulente=user) | Q(
        commessa_id__in=commesse_gestite_ids(user)
    )


def filtro_visibilita_timesheet(user) -> Q:
    return Q(assegnazione__consulente=user) | Q(
        assegnazione__commessa_id__in=commesse_gestite_ids(user)
    )
