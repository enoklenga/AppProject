from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db.models import (
    Case,
    Count,
    F,
    IntegerField,
    Q,
    Value,
    When,
)
from django.utils import timezone

from apps.projects.models import Assegnazione, Commessa
from apps.accounts.access import (
    can_manage_fase,
    has_org_role,
    is_global_manager,
    managed_business_unit_ids,
)

from .models import Task


User = get_user_model()


def _base_tasks():
    """
    QuerySet base ottimizzato per le schermate Task.
    """

    return Task.objects.select_related(
        "commessa",
        "commessa__cliente",
        "fase",
        "fase__commessa",
        "assegnato_a",
        "creato_da",
    )


def _ordered_tasks(queryset):
    """
    Ordinamento gestionale:

    1. attività non completate
    2. scadenza più vicina
    3. priorità Alta -> Normale -> Bassa
    4. titolo

    Le attività senza scadenza vengono mostrate dopo
    quelle con una data definita.
    """

    return (
        queryset
        .annotate(
            _stato_order=Case(
                When(
                    stato=Task.Stato.COMPLETATA,
                    then=Value(1),
                ),
                default=Value(0),
                output_field=IntegerField(),
            ),
            _priorita_order=Case(
                When(
                    priorita=Task.Priorita.ALTA,
                    then=Value(0),
                ),
                When(
                    priorita=Task.Priorita.NORMALE,
                    then=Value(1),
                ),
                When(
                    priorita=Task.Priorita.BASSA,
                    then=Value(2),
                ),
                default=Value(3),
                output_field=IntegerField(),
            ),
        )
        .order_by(
            "_stato_order",
            F("data_scadenza").asc(
                nulls_last=True
            ),
            "_priorita_order",
            "titolo",
        )
    )


def visible_tasks_for_user(user):
    """Task visibili: tutti i task delle commesse del Teamwork dell'utente."""
    queryset = _base_tasks()

    if not user or not getattr(user, "is_authenticated", False):
        return queryset.none()

    if is_global_manager(user) or has_org_role(user, User.Ruolo.DIREZIONE_GENERALE):
        return _ordered_tasks(queryset)

    fasi_team = Assegnazione.objects.filter(
        consulente=user, stato=Assegnazione.Stato.ATTIVA
    ).values_list("fase_id", flat=True)
    filtro = Q(fase_id__in=fasi_team)
    bu_gestite = managed_business_unit_ids(user)
    if bu_gestite:
        filtro |= Q(commessa__business_unit_id__in=bu_gestite)
    return _ordered_tasks(queryset.filter(filtro).distinct())

def manageable_projects_for_user(user):
    """
    Commesse sulle quali l'utente può creare/gestire task
    (Teamwork).

    Admin:
        tutte le commesse aperte.

    Chiunque altro:
        le commesse aperte dove ha un'assegnazione attiva — non più
        limitato ai soli Project Manager: qualunque membro del
        Teamwork può creare e gestire le attività della propria
        commessa.
    """

    queryset = (
        Commessa.objects
        .select_related(
            "cliente",
        )
        .filter(
            stato=Commessa.Stato.APERTA,
        )
    )

    if not user or not getattr(
        user,
        "is_authenticated",
        False,
    ):
        return queryset.none()

    if is_global_manager(user):
        return queryset.order_by(
            "codice"
        )

    commesse_assegnate = (
        Assegnazione.objects
        .filter(
            consulente=user,
            stato=Assegnazione.Stato.ATTIVA,
        )
        .values_list(
            "commessa_id",
            flat=True,
        )
    )

    filtro = Q(pk__in=commesse_assegnate)
    bu_gestite = managed_business_unit_ids(user)
    if bu_gestite:
        filtro |= Q(business_unit_id__in=bu_gestite)
    return (
        queryset
        .filter(filtro)
        .distinct()
        .order_by(
            "codice"
        )
    )


def assignable_users_for_project(
    *,
    user,
    commessa,
):
    """
    Persone alle quali Admin/PM può assegnare un task.

    Sono ammesse solamente persone con assegnazione
    ATTIVA sulla commessa.
    """

    if not user or not getattr(
        user,
        "is_authenticated",
        False,
    ):
        return User.objects.none()

    commesse_gestibili = (
        manageable_projects_for_user(
            user
        )
    )

    if not commesse_gestibili.filter(
        pk=commessa.pk
    ).exists():
        return User.objects.none()

    utenti = (
        User.objects
        .filter(
        is_active=True,
        )
        .filter(
            Q(
                assegnazioni__commessa=commessa,
                assegnazioni__stato=Assegnazione.Stato.ATTIVA,
            )
            | Q(
            ruolo=User.Ruolo.ADMIN,
            )
            | Q(
                # Responsabile della BU della commessa.
                ruolo=User.Ruolo.RESPONSABILE_CONSULENZA,
                membership_business_unit__business_unit_id=commessa.business_unit_id,
                membership_business_unit__responsabile=True,
                membership_business_unit__attiva=True,
            )
        )
        .distinct()
        .order_by(
            "last_name",
            "first_name",
            "email",
        )
    )

    return utenti


def tasks_for_project(
    *,
    user,
    commessa,
    include_completed=True,
):
    """
    Task visibili all'utente relativi a una commessa.
    """

    queryset = visible_tasks_for_user(
        user
    ).filter(
        commessa=commessa,
    )

    if not include_completed:
        queryset = queryset.exclude(
            stato=Task.Stato.COMPLETATA,
        )

    return queryset


def my_tasks(
    *,
    user,
    include_completed=False,
):
    """
    Le mie attività.

    Restituisce esclusivamente i task assegnati
    direttamente all'utente.
    """

    if not user or not getattr(
        user,
        "is_authenticated",
        False,
    ):
        return Task.objects.none()

    queryset = visible_tasks_for_user(
        user
    ).filter(
        assegnato_a=user,
    )

    if not include_completed:
        queryset = queryset.exclude(
            stato=Task.Stato.COMPLETATA,
        )

    return queryset


def overdue_tasks(
    *,
    user,
):
    """
    Task assegnati all'utente che hanno superato
    la data di scadenza e non sono completati.
    """

    oggi = timezone.localdate()

    return my_tasks(
        user=user,
        include_completed=False,
    ).filter(
        data_scadenza__lt=oggi,
    )


def due_soon_tasks(
    *,
    user,
    giorni=7,
):
    """
    Task assegnati all'utente in scadenza
    nei prossimi N giorni.
    """

    oggi = timezone.localdate()

    limite = oggi + timedelta(
        days=giorni
    )

    return (
        my_tasks(
            user=user,
            include_completed=False,
        )
        .filter(
            data_scadenza__gte=oggi,
            data_scadenza__lte=limite,
        )
    )


def task_summary(
    *,
    user,
):
    """
    KPI sintetici per la futura pagina
    'Le mie attività'.
    """

    oggi = timezone.localdate()

    queryset = (
        visible_tasks_for_user(
            user
        )
        .filter(
            assegnato_a=user,
        )
    )

    aggregati = queryset.aggregate(
        totale=Count("id"),
        da_fare=Count(
            "id",
            filter=Q(
                stato=Task.Stato.DA_FARE,
            ),
        ),
        in_corso=Count(
            "id",
            filter=Q(
                stato=Task.Stato.IN_CORSO,
            ),
        ),
        completate=Count(
            "id",
            filter=Q(
                stato=Task.Stato.COMPLETATA,
            ),
        ),
        scadute=Count(
            "id",
            filter=Q(
                data_scadenza__lt=oggi,
            )
            & ~Q(
                stato=Task.Stato.COMPLETATA,
            ),
        ),
    )

    return {
        "totale": aggregati["totale"] or 0,
        "da_fare": aggregati["da_fare"] or 0,
        "in_corso": aggregati["in_corso"] or 0,
        "completate": (
            aggregati["completate"]
            or 0
        ),
        "scadute": (
            aggregati["scadute"]
            or 0
        ),
    }


def task_with_comments(
    *,
    user,
    pk,
):
    """
    QuerySet per la futura pagina dettaglio Task.
    Carica anche i commenti e i relativi autori.
    """

    return (
        visible_tasks_for_user(
            user
        )
        .filter(
            pk=pk,
        )
        .prefetch_related(
            "commenti__autore",
        )
    )

def manageable_phases_for_user(user):
    from apps.phases.models import FaseCommessa
    qs = FaseCommessa.objects.select_related("commessa", "commessa__cliente").filter(commessa__stato=Commessa.Stato.APERTA)
    if not user or not getattr(user, "is_authenticated", False):
        return qs.none()
    if is_global_manager(user):
        return qs.order_by("commessa__codice", "ordine", "nome")
    ids = Assegnazione.objects.filter(consulente=user, stato=Assegnazione.Stato.ATTIVA).values_list("fase_id", flat=True)
    filtro = Q(pk__in=ids)
    bu_gestite = managed_business_unit_ids(user)
    if bu_gestite:
        filtro |= Q(commessa__business_unit_id__in=bu_gestite)
    return qs.filter(filtro).distinct().order_by("commessa__codice", "ordine", "nome")

def assignable_users_for_phase(*, user, fase):
    if not user or not getattr(user, "is_authenticated", False):
        return User.objects.none()
    if can_manage_fase(user, fase):
        return User.objects.filter(
            Q(ruolo=User.Ruolo.ADMIN)
            | Q(assegnazioni__fase=fase, assegnazioni__stato=Assegnazione.Stato.ATTIVA),
            is_active=True,
        ).distinct().order_by("last_name", "first_name", "email")
    if not Assegnazione.objects.filter(consulente=user, fase=fase, ruolo_commessa=Assegnazione.Ruolo.PROJECT_MANAGER, stato=Assegnazione.Stato.ATTIVA).exists():
        return User.objects.none()
    return User.objects.filter(is_active=True, assegnazioni__fase=fase, assegnazioni__stato=Assegnazione.Stato.ATTIVA).distinct().order_by("last_name", "first_name", "email")
