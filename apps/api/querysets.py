from django.db.models import Q

from apps.projects.models import Assegnazione


def commesse_gestite_ids(user):
    if not user or not user.is_authenticated:
        return Assegnazione.objects.none().values_list(
            "commessa_id",
            flat=True,
        )

    return Assegnazione.objects.filter(
        consulente=user,
        ruolo_commessa=Assegnazione.Ruolo.PROJECT_MANAGER,
        stato=Assegnazione.Stato.ATTIVA,
    ).values_list("commessa_id", flat=True)


def filtro_visibilita_assegnazioni(user) -> Q:
    return Q(consulente=user) | Q(
        commessa_id__in=commesse_gestite_ids(user)
    )


def filtro_visibilita_timesheet(user) -> Q:
    return Q(assegnazione__consulente=user) | Q(
        assegnazione__commessa_id__in=commesse_gestite_ids(user)
    )
