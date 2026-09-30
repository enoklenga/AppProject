"""Riepiloghi della Business Unit (pagina BU e home del Responsabile BU).

Tutte le metriche sono calcolate con poche query aggregate, indipendenti dal
numero di membri o commesse della BU.
"""
from __future__ import annotations

from collections import defaultdict

from django.db.models import Count, Exists, OuterRef, Q, Sum

from .access import membership_current_q, membership_is_current
from .models import BusinessUnit, User, UserBusinessUnit


def capacita_mensile(anno: int, mese: int, ore_giornaliere: int = 8) -> int:
    """Capacità standard di una risorsa: giorni lavorativi (lun-ven) × 8 ore."""
    import calendar

    giorni = calendar.monthrange(anno, mese)[1]
    lavorativi = sum(
        1 for giorno in range(1, giorni + 1) if calendar.weekday(anno, mese, giorno) < 5
    )
    return lavorativi * ore_giornaliere


def _commesse_bu(business_unit_ids):
    from apps.projects.models import Commessa

    return Commessa.objects.filter(business_unit_id__in=list(business_unit_ids))


def indicatori_business_unit(business_unit_ids, anno: int, mese: int) -> dict:
    """KPI aggregati su una o più BU (le BU gestite da un Responsabile)."""
    from apps.planning.models import GiornoPianificato
    from apps.projects.models import Assegnazione, Commessa
    from apps.timesheets.models import RigaOre, SpesaTrasferta, StatoApprovazione

    ids = list(business_unit_ids)
    commesse = _commesse_bu(ids)
    aperte = commesse.filter(stato=Commessa.Stato.APERTA)
    pm_attivo = Assegnazione.objects.filter(
        commessa_id=OuterRef("pk"),
        ruolo_commessa=Assegnazione.Ruolo.PROJECT_MANAGER,
        stato=Assegnazione.Stato.ATTIVA,
    )
    membri = UserBusinessUnit.objects.filter(
        membership_current_q(),
        business_unit_id__in=ids,
        utente__is_active=True,
    )
    return {
        "membri_attivi": membri.values("utente_id").distinct().count(),
        "pm_abilitati": membri.filter(puo_essere_pm=True).values("utente_id").distinct().count(),
        "commesse_aperte": aperte.count(),
        "commesse_senza_pm": aperte.annotate(ha_pm=Exists(pm_attivo)).filter(ha_pm=False).count(),
        "handover_da_completare": aperte.filter(handover_completato=False).count(),
        "ore_budget_aperte": aperte.aggregate(t=Sum("ore_budget"))["t"] or 0,
        "ore_pianificate_mese": GiornoPianificato.objects.filter(
            assegnazione__commessa__business_unit_id__in=ids,
            data__year=anno,
            data__month=mese,
        ).aggregate(t=Sum("ore_pianificate"))["t"] or 0,
        "ore_consuntivate_mese": RigaOre.objects.filter(
            assegnazione__commessa__business_unit_id__in=ids,
            data__year=anno,
            data__month=mese,
        ).aggregate(t=Sum("ore"))["t"] or 0,
        # Stesso perimetro della pagina di approvazione: il mese selezionato.
        "ore_da_approvare": RigaOre.objects.filter(
            assegnazione__commessa__business_unit_id__in=ids,
            stato_approvazione=StatoApprovazione.IN_ATTESA,
            data__year=anno,
            data__month=mese,
        ).count(),
        "spese_da_approvare": SpesaTrasferta.objects.filter(
            assegnazione__commessa__business_unit_id__in=ids,
            stato_approvazione=StatoApprovazione.IN_ATTESA,
            data__year=anno,
            data__month=mese,
        ).count(),
    }


def carichi_membri(
    business_unit_ids,
    anno: int,
    mese: int,
    *,
    deduplica_utenti: bool = False,
) -> list[dict]:
    """Membri BU con abilitazioni e carico del mese.

    Se ``deduplica_utenti`` e vero (home di un Responsabile con piu BU), una
    persona presente in piu BU compare una sola volta con l'elenco delle
    appartenenze correnti. Nel dettaglio di una singola BU si conserva invece
    la riga di membership, utile per le azioni di modifica.
    """
    from apps.planning.models import GiornoPianificato
    from apps.projects.models import Assegnazione
    from apps.timesheets.models import RigaOre

    ids = list(business_unit_ids)
    membership_qs = UserBusinessUnit.objects.filter(
        business_unit_id__in=ids,
        utente__is_active=True,
    )
    # La home multi-BU rappresenta la capacita corrente e quindi considera
    # soltanto membership valide oggi. Il dettaglio di una singola BU mantiene
    # anche lo storico, marcandolo come concluso nella UI.
    if deduplica_utenti:
        membership_qs = membership_qs.filter(membership_current_q())
    appartenenze = list(
        membership_qs.select_related("utente", "business_unit")
        .order_by("utente__last_name", "utente__first_name", "business_unit__nome")
    )
    utenti_ids = {a.utente_id for a in appartenenze}

    def _per_utente(queryset, campo_utente, campo_somma):
        return {
            riga[campo_utente]: riga["totale"] or 0
            for riga in queryset.values(campo_utente).annotate(totale=Sum(campo_somma))
        }

    pianificate = _per_utente(
        GiornoPianificato.objects.filter(
            assegnazione__consulente_id__in=utenti_ids,
            data__year=anno,
            data__month=mese,
        ),
        "assegnazione__consulente_id",
        "ore_pianificate",
    )
    consuntivate = _per_utente(
        RigaOre.objects.filter(
            assegnazione__consulente_id__in=utenti_ids,
            data__year=anno,
            data__month=mese,
        ),
        "assegnazione__consulente_id",
        "ore",
    )
    assegnazioni = {
        riga["consulente_id"]: riga["totale"]
        for riga in Assegnazione.objects.filter(
            consulente_id__in=utenti_ids,
            stato=Assegnazione.Stato.ATTIVA,
        )
        .values("consulente_id")
        .annotate(totale=Count("id"))
    }
    pm_su = {
        riga["consulente_id"]: riga["totale"]
        for riga in Assegnazione.objects.filter(
            consulente_id__in=utenti_ids,
            stato=Assegnazione.Stato.ATTIVA,
            ruolo_commessa=Assegnazione.Ruolo.PROJECT_MANAGER,
        )
        .values("consulente_id")
        .annotate(totale=Count("commessa_id", distinct=True))
    }

    if not deduplica_utenti:
        return [
            {
                "appartenenza": a,
                "appartenenze": [a],
                "utente": a.utente,
                "business_units_label": a.business_unit.nome,
                "responsabile": a.responsabile,
                "puo_essere_pm": a.puo_essere_pm,
                "corrente": membership_is_current(a),
                "ore_pianificate": pianificate.get(a.utente_id, 0),
                "ore_consuntivate": consuntivate.get(a.utente_id, 0),
                "assegnazioni_attive": assegnazioni.get(a.utente_id, 0),
                "commesse_come_pm": pm_su.get(a.utente_id, 0),
            }
            for a in appartenenze
        ]

    per_utente = defaultdict(list)
    for appartenenza in appartenenze:
        per_utente[appartenenza.utente_id].append(appartenenza)

    risultato = []
    for uid, memberships in per_utente.items():
        memberships.sort(key=lambda a: a.business_unit.nome.lower())
        utente = memberships[0].utente
        risultato.append(
            {
                "appartenenza": memberships[0],  # compatibilita template legacy
                "appartenenze": memberships,
                "utente": utente,
                "business_units_label": " · ".join(a.business_unit.nome for a in memberships),
                "responsabile": any(a.responsabile for a in memberships),
                "puo_essere_pm": any(a.puo_essere_pm for a in memberships),
                "corrente": True,
                "ore_pianificate": pianificate.get(uid, 0),
                "ore_consuntivate": consuntivate.get(uid, 0),
                "assegnazioni_attive": assegnazioni.get(uid, 0),
                "commesse_come_pm": pm_su.get(uid, 0),
            }
        )
    risultato.sort(key=lambda x: ((x["utente"].last_name or "").lower(), (x["utente"].first_name or "").lower(), x["utente"].email.lower()))
    return risultato


def commesse_business_unit(business_unit_ids, solo_aperte: bool = False):
    from apps.projects.models import Assegnazione, Commessa

    queryset = _commesse_bu(business_unit_ids).select_related("cliente", "business_unit")
    if solo_aperte:
        queryset = queryset.filter(stato=Commessa.Stato.APERTA)
    pm_attivo = Assegnazione.objects.filter(
        commessa_id=OuterRef("pk"),
        ruolo_commessa=Assegnazione.Ruolo.PROJECT_MANAGER,
        stato=Assegnazione.Stato.ATTIVA,
    )
    return queryset.annotate(
        membri_attivi=Count(
            "assegnazioni__consulente",
            filter=Q(assegnazioni__stato=Assegnazione.Stato.ATTIVA),
            distinct=True,
        ),
        ore_assegnate=Sum(
            "assegnazioni__ore_previste",
            filter=Q(assegnazioni__stato=Assegnazione.Stato.ATTIVA),
        ),
        ha_pm=Exists(pm_attivo),
    ).order_by("stato", "-data_inizio", "codice")


def responsabili_business_unit(business_unit: BusinessUnit):
    return User.objects.filter(
        membership_current_q("membership_business_unit__"),
        membership_business_unit__business_unit=business_unit,
        membership_business_unit__responsabile=True,
        ruolo=User.Ruolo.RESPONSABILE_CONSULENZA,
        is_active=True,
    ).distinct().order_by("last_name", "first_name")


def schede_business_unit(business_units, anno: int, mese: int) -> list[dict]:
    """Una scheda sintetica per BU (elenco BU e home della gestione)."""
    schede = []
    responsabili_per_bu = defaultdict(list)
    for voce in UserBusinessUnit.objects.filter(
        membership_current_q(),
        business_unit__in=business_units,
        responsabile=True,
        utente__ruolo=User.Ruolo.RESPONSABILE_CONSULENZA,
        utente__is_active=True,
    ).select_related("utente"):
        responsabili_per_bu[voce.business_unit_id].append(voce.utente)
    for bu in business_units:
        schede.append(
            {
                "business_unit": bu,
                "responsabili": responsabili_per_bu.get(bu.pk, []),
                "indicatori": indicatori_business_unit([bu.pk], anno, mese),
            }
        )
    return schede
