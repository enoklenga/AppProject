from django.db.models import Q

from apps.projects.models import Assegnazione, Commessa
from apps.accounts.access import (
    can_view_all_documents,
    is_global_manager,
    managed_business_unit_ids,
)

from .models import DocumentoCommessa


def _base_documents():
    return DocumentoCommessa.objects.select_related(
        "commessa",
        "commessa__cliente",
        "fase",
        "fase__commessa",
        "caricato_da",
    )


def visible_documents_for_user(user):
    """
    Documenti visibili all'utente, sulle stesse regole di
    apps.documents.permissions.can_view_documents.
    """

    queryset = _base_documents()

    if not user.is_authenticated:
        return queryset.none()

    if is_global_manager(user):
        return queryset

    # Il Responsabile BU vede tutti i documenti (anche privati) della BU.
    bu_gestite = managed_business_unit_ids(user)
    gestiti = Q(commessa__business_unit_id__in=bu_gestite) if bu_gestite else Q(pk__in=[])

    if can_view_all_documents(user):
        return queryset.filter(Q(privato=False) | gestiti)

    fasi_visibili = Assegnazione.objects.filter(
        consulente=user, stato=Assegnazione.Stato.ATTIVA
    ).values_list("fase_id", flat=True)
    del_team = (
        Q(fase_id__in=fasi_visibili)
        | Q(
            fase__isnull=True,
            commessa_id__in=Assegnazione.objects.filter(
                consulente=user, stato=Assegnazione.Stato.ATTIVA
            ).values_list("commessa_id", flat=True),
        )
    )
    # Un documento privato resta riservato alla gestione, anche per chi ha
    # un'assegnazione attiva sulla fase/commessa.
    return queryset.filter((del_team & Q(privato=False)) | gestiti).distinct()


def documents_for_commessa(*, user, commessa):
    return visible_documents_for_user(user).filter(
        commessa=commessa,
    )


def manageable_projects_for_upload(user):
    """
    Commesse su cui l'utente può caricare almeno un documento
    (usato per popolare il selettore commessa nel form di upload).
    """

    if not user.is_authenticated:
        return Commessa.objects.none()

    if is_global_manager(user):
        return Commessa.objects.all()

    commesse_team = (
        Assegnazione.objects
        .filter(
            consulente=user,
            stato=Assegnazione.Stato.ATTIVA,
        )
        .values_list("commessa_id", flat=True)
    )

    filtro = Q(pk__in=commesse_team)
    bu_gestite = managed_business_unit_ids(user)
    if bu_gestite:
        filtro |= Q(business_unit_id__in=bu_gestite)
    return Commessa.objects.filter(filtro, stato=Commessa.Stato.APERTA).distinct()


def visible_projects_for_documents(user):
    """Commesse disponibili nei filtri della pagina Documenti.

    Per i profili di portafoglio (Commerciale/DG) comprende tutte le
    commesse, pur mantenendo il caricamento documenti disabilitato.
    """
    if not user.is_authenticated:
        return Commessa.objects.none()
    if is_global_manager(user) or can_view_all_documents(user):
        return Commessa.objects.all()
    filtro = Q(
        pk__in=Assegnazione.objects.filter(
            consulente=user,
            stato=Assegnazione.Stato.ATTIVA,
        ).values_list("commessa_id", flat=True)
    )
    bu_gestite = managed_business_unit_ids(user)
    if bu_gestite:
        filtro |= Q(business_unit_id__in=bu_gestite)
    return Commessa.objects.filter(filtro).distinct()
