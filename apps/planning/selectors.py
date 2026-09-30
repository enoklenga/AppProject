from datetime import timedelta

from django.db.models import Q, Sum

from apps.projects.models import Assegnazione
from apps.accounts.access import (
    has_org_role,
    is_global_manager,
    managed_business_unit_ids,
)
from apps.accounts.models import User

from .models import GiornoPianificato

from django.utils import timezone

from apps.timesheets.models import RigaOre


CAPACITA_SETTIMANALE_DEFAULT = 40


CAPACITA_GIORNALIERA_DEFAULT = 8


def daily_availability(*, consulente, giorno, exclude_planning_id=None):
    """Disponibilità V1: agenda giornaliera, capacità standard 8 ore."""
    queryset = GiornoPianificato.objects.filter(
        assegnazione__consulente=consulente,
        data=giorno,
    )
    if exclude_planning_id:
        queryset = queryset.exclude(pk=exclude_planning_id)
    occupate = queryset.aggregate(totale=Sum("ore_pianificate"))["totale"] or 0
    disponibili = max(CAPACITA_GIORNALIERA_DEFAULT - occupate, 0)
    return {
        "giorno": giorno,
        "ore_occupate": occupate,
        "ore_disponibili": disponibili,
        "capacita": CAPACITA_GIORNALIERA_DEFAULT,
        "disponibile": disponibili > 0,
    }


def is_consultant_available(*, consulente, giorno, ore_richieste=1, exclude_planning_id=None):
    if not getattr(consulente, "is_risorsa_ingaggiabile", False):
        return False
    disponibilita = daily_availability(
        consulente=consulente,
        giorno=giorno,
        exclude_planning_id=exclude_planning_id,
    )
    return disponibilita["ore_disponibili"] >= ore_richieste


def _vista_globale(user) -> bool:
    """Admin, Amministrazione e Direzione Generale leggono tutto il planning."""
    return is_global_manager(user) or has_org_role(user, User.Ruolo.DIREZIONE_GENERALE)


def visible_assignments_for_user(user):
    """
    Assegnazioni appartenenti al perimetro visibile dall'utente.

    Admin:
        tutte.

    PM:
        tutte le assegnazioni (di qualunque fase) delle commesse dove
        è PM attivo — supervisione trasversale su tutto il progetto.

    Consulente:
        le proprie assegnazioni, più quelle degli altri membri della
        STESSA fase dove ha un'assegnazione attiva — squadre separate
        per fase, non più l'intera commessa (il consulente lavora per
        fase, non per commessa intera).
    """

    queryset = (
        Assegnazione.objects
        .select_related(
            "consulente",
            "commessa",
            "commessa__cliente",
        )
    )

    if not user.is_authenticated:
        return queryset.none()

    if _vista_globale(user):
        return queryset

    commesse_pm = Assegnazione.objects.filter(
        consulente=user,
        ruolo_commessa=Assegnazione.Ruolo.PROJECT_MANAGER,
        stato=Assegnazione.Stato.ATTIVA,
    ).values_list("commessa_id", flat=True)

    fasi_del_team = Assegnazione.objects.filter(
        consulente=user,
        ruolo_commessa=Assegnazione.Ruolo.CONSULENTE,
        stato=Assegnazione.Stato.ATTIVA,
    ).values_list("fase_id", flat=True)

    filtro = (
        Q(commessa_id__in=commesse_pm)
        | Q(fase_id__in=fasi_del_team)
        | Q(consulente=user)
    )
    bu_gestite = managed_business_unit_ids(user)
    if bu_gestite:
        filtro |= Q(commessa__business_unit_id__in=bu_gestite)
    return queryset.filter(filtro).distinct()


def plannable_assignments_for_user(user):
    """Assegnazioni che l'utente può realmente selezionare in creazione.

    La vista di portafoglio (Responsabile consulenza/DG) non deve trasformarsi
    automaticamente in potere di pianificazione: PM, consulente e Responsabile
    selezionano solo commesse/fasi di cui fanno parte. L'Admin mantiene il
    perimetro globale.
    """
    queryset = Assegnazione.objects.select_related(
        "consulente", "commessa", "commessa__cliente", "fase"
    )
    if not getattr(user, "is_authenticated", False):
        return queryset.none()
    if is_global_manager(user):
        return queryset

    commesse_pm = Assegnazione.objects.filter(
        consulente=user,
        ruolo_commessa=Assegnazione.Ruolo.PROJECT_MANAGER,
        stato=Assegnazione.Stato.ATTIVA,
    ).values_list("commessa_id", flat=True)
    fasi_membro = Assegnazione.objects.filter(
        consulente=user,
        stato=Assegnazione.Stato.ATTIVA,
    ).values_list("fase_id", flat=True)
    filtro = (
        Q(commessa_id__in=commesse_pm)
        | Q(fase_id__in=fasi_membro)
        | Q(consulente=user)
    )
    # Il Responsabile BU pianifica le risorse di tutte le commesse della BU.
    bu_gestite = managed_business_unit_ids(user)
    if bu_gestite:
        filtro |= Q(commessa__business_unit_id__in=bu_gestite)
    return queryset.filter(filtro).distinct()


def visible_planning_for_user(user):
    """
    Pianificazioni visibili all'utente.

    Il calendario è lo spazio operativo condiviso della SINGOLA FASE:
    un consulente vede le pianificazioni della propria fase e non quelle
    di altre fasi della stessa commessa.

    Il PM mantiene la supervisione trasversale sulle fasi delle commesse
    dove ha un'assegnazione PM attiva; l'Admin vede tutto.
    """

    queryset = (
        GiornoPianificato.objects
        .select_related(
            "assegnazione",
            "assegnazione__consulente",
            "assegnazione__commessa",
            "assegnazione__commessa__cliente",
            "assegnazione__fase",
            "assegnazione__fase__commessa",
            "inserita_da",
            "ultima_modifica_da",
        )
    )

    if not user.is_authenticated:
        return queryset.none()

    if _vista_globale(user):
        return queryset

    commesse_pm = (
        Assegnazione.objects
        .filter(
            consulente=user,
            ruolo_commessa=Assegnazione.Ruolo.PROJECT_MANAGER,
            stato=Assegnazione.Stato.ATTIVA,
        )
        .values_list("commessa_id", flat=True)
    )

    fasi_del_team = (
        Assegnazione.objects
        .filter(
            consulente=user,
            stato=Assegnazione.Stato.ATTIVA,
        )
        .values_list("fase_id", flat=True)
    )

    filtro = (
        Q(assegnazione__commessa_id__in=commesse_pm)
        | Q(assegnazione__fase_id__in=fasi_del_team)
        | Q(assegnazione__consulente_id=user.id)
    )
    bu_gestite = managed_business_unit_ids(user)
    if bu_gestite:
        filtro |= Q(assegnazione__commessa__business_unit_id__in=bu_gestite)
    return queryset.filter(filtro).distinct()


def planning_for_consultant(
    *,
    user,
    consulente,
    data_inizio=None,
    data_fine=None,
):
    queryset = visible_planning_for_user(
        user
    ).filter(
        assegnazione__consulente=consulente,
    )

    if data_inizio:
        queryset = queryset.filter(
            data__gte=data_inizio,
        )

    if data_fine:
        queryset = queryset.filter(
            data__lte=data_fine,
        )

    return queryset


def planning_for_project(
    *,
    user,
    commessa,
    data_inizio=None,
    data_fine=None,
):
    queryset = visible_planning_for_user(
        user
    ).filter(
        assegnazione__commessa=commessa,
    )

    if data_inizio:
        queryset = queryset.filter(
            data__gte=data_inizio,
        )

    if data_fine:
        queryset = queryset.filter(
            data__lte=data_fine,
        )

    return queryset


def weekly_load(
    *,
    user,
    consulente,
    giorno_settimana,
):
    lunedi = giorno_settimana - timedelta(
        days=giorno_settimana.weekday()
    )

    domenica = lunedi + timedelta(days=6)

    queryset = planning_for_consultant(
        user=user,
        consulente=consulente,
        data_inizio=lunedi,
        data_fine=domenica,
    )

    totale = (
        queryset.aggregate(
            totale=Sum("ore_pianificate")
        )["totale"]
        or 0
    )

    return {
        "data_inizio": lunedi,
        "data_fine": domenica,
        "ore_pianificate": totale,
        "soglia_standard": CAPACITA_SETTIMANALE_DEFAULT,
        "sovraccarico": (
            totale > CAPACITA_SETTIMANALE_DEFAULT
        ),
    }


def planned_hours_for_assignment(
    assegnazione,
):
    return (
        GiornoPianificato.objects
        .filter(
            assegnazione=assegnazione,
        )
        .aggregate(
            totale=Sum("ore_pianificate")
        )["totale"]
        or 0
    )


def remaining_plannable_hours(
    assegnazione,
):
    pianificate = planned_hours_for_assignment(
        assegnazione
    )

    return max(
        assegnazione.ore_previste - pianificate,
        0,
    )


def planned_vs_actual(
    *,
    user,
    data_inizio,
    data_fine,
    consulente_id=None,
    commessa_id=None,
):
    """
    Confronta pianificato e consuntivato nel periodo.

    Il confronto si ferma alla data odierna, perché le giornate
    future non sono ancora consuntivabili.
    """

    oggi = timezone.localdate()

    data_fine_confronto = min(
        data_fine,
        oggi,
    )

    if data_inizio > data_fine_confronto:
        return {
            "data_inizio": data_inizio,
            "data_fine": data_fine_confronto,
            "ore_pianificate": 0,
            "ore_consuntivate": 0,
            "scostamento": 0,
            "percentuale_consuntivata": None,
            "percentuale_scostamento": None,
            "valutabile": False,
        }

    pianificate = (
        visible_planning_for_user(user)
        .filter(
            data__gte=data_inizio,
            data__lte=data_fine_confronto,
        )
    )

    assegnazioni = visible_assignments_for_user(
        user
    )

    consuntivate = (
        RigaOre.objects
        .filter(
            assegnazione__in=assegnazioni,
            data__gte=data_inizio,
            data__lte=data_fine_confronto,
        )
    )

    if consulente_id:
        pianificate = pianificate.filter(
            assegnazione__consulente_id=consulente_id,
        )

        consuntivate = consuntivate.filter(
            assegnazione__consulente_id=consulente_id,
        )

    if commessa_id:
        pianificate = pianificate.filter(
            assegnazione__commessa_id=commessa_id,
        )

        consuntivate = consuntivate.filter(
            assegnazione__commessa_id=commessa_id,
        )

    ore_pianificate = (
        pianificate.aggregate(
            totale=Sum("ore_pianificate")
        )["totale"]
        or 0
    )

    ore_consuntivate = (
        consuntivate.aggregate(
            totale=Sum("ore")
        )["totale"]
        or 0
    )

    scostamento = (
        ore_consuntivate
        - ore_pianificate
    )

    if ore_pianificate:
        percentuale_consuntivata = round(
            (
                ore_consuntivate
                / ore_pianificate
            )
            * 100,
            1,
        )
        percentuale_scostamento = round(
            (
                scostamento
                / ore_pianificate
            )
            * 100,
            1,
        )
    else:
        percentuale_consuntivata = None
        percentuale_scostamento = None

    return {
        "data_inizio": data_inizio,
        "data_fine": data_fine_confronto,
        "ore_pianificate": ore_pianificate,
        "ore_consuntivate": ore_consuntivate,
        "scostamento": scostamento,
        "percentuale_consuntivata": (
            percentuale_consuntivata
        ),
        "percentuale_scostamento": (
            percentuale_scostamento
        ),
        "valutabile": True,
    }



def planned_vs_actual_by_consultant(
    *,
    user,
    data_inizio,
    data_fine,
    commessa_id=None,
):
    oggi = timezone.localdate()

    data_fine_confronto = min(
        data_fine,
        oggi,
    )

    if data_inizio > data_fine_confronto:
        return []

    assegnazioni = visible_assignments_for_user(
        user
    )

    if commessa_id:
        assegnazioni = assegnazioni.filter(
            commessa_id=commessa_id,
        )

    persone = (
        assegnazioni
        .values(
            "consulente_id",
            "consulente__first_name",
            "consulente__last_name",
            "consulente__email",
        )
        .distinct()
        .order_by(
            "consulente__last_name",
            "consulente__first_name",
            "consulente__email",
        )
    )

    risultato = []

    for persona in persone:
        confronto = planned_vs_actual(
            user=user,
            data_inizio=data_inizio,
            data_fine=data_fine_confronto,
            consulente_id=persona["consulente_id"],
            commessa_id=commessa_id,
        )

        risultato.append(
            {
                **persona,
                **confronto,
            }
        )

    return risultato


def planned_vs_actual_by_project(
    *,
    user,
    data_inizio,
    data_fine,
    consulente_id=None,
):
    oggi = timezone.localdate()

    data_fine_confronto = min(
        data_fine,
        oggi,
    )

    if data_inizio > data_fine_confronto:
        return []

    assegnazioni = visible_assignments_for_user(
        user
    )

    if consulente_id:
        assegnazioni = assegnazioni.filter(
            consulente_id=consulente_id,
        )

    commesse = (
        assegnazioni
        .values(
            "commessa_id",
            "commessa__codice",
            "commessa__cliente__ragione_sociale",
        )
        .distinct()
        .order_by(
            "commessa__codice",
        )
    )

    risultato = []

    for commessa in commesse:
        confronto = planned_vs_actual(
            user=user,
            data_inizio=data_inizio,
            data_fine=data_fine_confronto,
            consulente_id=consulente_id,
            commessa_id=commessa["commessa_id"],
        )

        risultato.append(
            {
                **commessa,
                **confronto,
            }
        )

    return risultato