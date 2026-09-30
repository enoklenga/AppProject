from __future__ import annotations

from calendar import monthrange
from collections import defaultdict
from decimal import Decimal

from django.db.models import Sum

from apps.projects.models import Assegnazione
from apps.timesheets.models import RigaOre, SpesaTrasferta

from .models import PeriodoMensile


def _serie_giornaliera(*, anno: int, mese: int, righe) -> dict:
    giorni_mese = monthrange(anno, mese)[1]
    valori = {giorno: 0 for giorno in range(1, giorni_mese + 1)}

    for elemento in righe:
        if isinstance(elemento, dict):
            giorno = elemento["data"].day
            valore = elemento.get("totale") or 0
        else:
            giorno = elemento.data.day
            valore = elemento.ore
        valori[giorno] += int(valore)

    return {
        "labels": [str(giorno) for giorno in range(1, giorni_mese + 1)],
        "series": [
            {
                "label": "Ore",
                "values": [valori[giorno] for giorno in range(1, giorni_mese + 1)],
            }
        ],
    }


def admin_visuals(
    *,
    dashboard,
    anno: int,
    mese: int,
    cliente_id=None,
    commessa_id=None,
    consulente_id=None,
    fase_id=None,
    business_unit_ids=None,
) -> dict:
    righe = RigaOre.objects.filter(data__year=anno, data__month=mese)
    if business_unit_ids is not None:
        righe = righe.filter(
            assegnazione__commessa__business_unit_id__in=list(business_unit_ids)
        )
    if cliente_id:
        righe = righe.filter(assegnazione__commessa__cliente_id=cliente_id)
    if commessa_id:
        righe = righe.filter(assegnazione__commessa_id=commessa_id)
    if consulente_id:
        righe = righe.filter(assegnazione__consulente_id=consulente_id)
    if fase_id:
        righe = righe.filter(assegnazione__fase_id=fase_id)

    giornaliere = (
        righe.values("data")
        .annotate(totale=Sum("ore"))
        .order_by("data")
    )

    per_cliente = sorted(
        dashboard.per_cliente,
        key=lambda voce: voce.ore,
        reverse=True,
    )[:8]
    per_consulente = sorted(
        dashboard.per_consulente,
        key=lambda voce: voce.ore,
        reverse=True,
    )[:8]

    return {
        "ore_giornaliere": _serie_giornaliera(
            anno=anno,
            mese=mese,
            righe=giornaliere,
        ),
        "ore_per_cliente": {
            "labels": [voce.etichetta for voce in per_cliente],
            "series": [
                {
                    "label": "Ore",
                    "values": [voce.ore for voce in per_cliente],
                }
            ],
        },
        "ore_per_consulente": {
            "labels": [voce.etichetta for voce in per_consulente],
            "series": [
                {
                    "label": "Ore",
                    "values": [voce.ore for voce in per_consulente],
                }
            ],
        },
        "avanzamento_commesse": {
            "labels": [
                voce.commessa.codice
                for voce in dashboard.avanzamento_commesse[:10]
            ],
            "series": [
                {
                    "label": "Previste",
                    "values": [
                        voce.ore_previste
                        for voce in dashboard.avanzamento_commesse[:10]
                    ],
                },
                {
                    "label": "Consuntivate",
                    "values": [
                        voce.ore_consuntivate
                        for voce in dashboard.avanzamento_commesse[:10]
                    ],
                },
            ],
        },
    }


def pm_visuals(*, dashboard) -> dict:
    team = list(dashboard.team)
    return {
        "ore_giornaliere": _serie_giornaliera(
            anno=dashboard.anno,
            mese=dashboard.mese,
            righe=dashboard.righe_ore,
        ),
        "team": {
            "labels": [str(voce.assegnazione.consulente) for voce in team],
            "series": [
                {
                    "label": "Previste",
                    "values": [voce.ore_previste for voce in team],
                },
                {
                    "label": "Consuntivate",
                    "values": [voce.ore_consuntivate for voce in team],
                },
                {
                    "label": "Mese",
                    "values": [voce.ore_periodo for voce in team],
                },
            ],
        },
    }


def dashboard_consulente(*, utente, anno: int, mese: int) -> dict:
    assegnazioni = list(
        Assegnazione.objects.filter(consulente=utente)
        .select_related("commessa", "commessa__cliente", "fase")
        .order_by(
            "commessa__codice",
            "fase__ordine",
            "fase__nome",
            "consulente__last_name",
            "consulente__first_name",
        )
    )
    ids = [assegnazione.id for assegnazione in assegnazioni]

    ore_cumulative = {
        elemento["assegnazione_id"]: elemento["totale"] or 0
        for elemento in (
            RigaOre.objects.filter(assegnazione_id__in=ids)
            .values("assegnazione_id")
            .annotate(totale=Sum("ore"))
        )
    }

    righe_periodo = list(
        RigaOre.objects.filter(
            assegnazione__consulente=utente,
            data__year=anno,
            data__month=mese,
        )
        .select_related("assegnazione", "assegnazione__commessa")
        .order_by("data", "created_at")
    )
    spese_periodo = list(
        SpesaTrasferta.objects.filter(
            assegnazione__consulente=utente,
            data__year=anno,
            data__month=mese,
        )
        .select_related("assegnazione", "assegnazione__commessa")
        .order_by("data", "created_at")
    )

    ore_mese_per_assegnazione = defaultdict(int)
    for riga in righe_periodo:
        ore_mese_per_assegnazione[riga.assegnazione_id] += riga.ore

    spese_mese_per_assegnazione = defaultdict(lambda: Decimal("0.00"))
    for spesa in spese_periodo:
        spese_mese_per_assegnazione[spesa.assegnazione_id] += spesa.importo

    commesse = []
    for assegnazione in assegnazioni:
        consuntivate = ore_cumulative.get(assegnazione.id, 0)
        previste = assegnazione.ore_previste
        residue = max(previste - consuntivate, 0)
        percentuale = 0
        if previste:
            percentuale = min(round((consuntivate / previste) * 100), 100)

        commesse.append(
            {
                "assegnazione": assegnazione,
                "ore_previste": previste,
                "ore_consuntivate": consuntivate,
                "ore_residue": residue,
                "ore_periodo": ore_mese_per_assegnazione[assegnazione.id],
                "spese_periodo": spese_mese_per_assegnazione[assegnazione.id],
                "percentuale": percentuale,
                "superamento": consuntivate > previste,
            }
        )

    periodo = PeriodoMensile.objects.filter(anno=anno, mese=mese).first()
    stato_periodo = (
        periodo.stato
        if periodo is not None
        else PeriodoMensile.Stato.APERTO
    )

    giorni_compilati = len({riga.data for riga in righe_periodo})
    totale_spese = sum(
        (spesa.importo for spesa in spese_periodo),
        Decimal("0.00"),
    )

    top_commesse = sorted(
        commesse,
        key=lambda voce: voce["ore_periodo"],
        reverse=True,
    )[:8]

    return {
        "anno": anno,
        "mese": mese,
        "stato_periodo": stato_periodo,
        "modificabile": stato_periodo == PeriodoMensile.Stato.APERTO,
        "totale_ore_periodo": sum(riga.ore for riga in righe_periodo),
        "totale_spese_periodo": totale_spese,
        "numero_righe_ore": len(righe_periodo),
        "numero_spese": len(spese_periodo),
        "giorni_compilati": giorni_compilati,
        "assegnazioni_attive": [
            voce
            for voce in commesse
            if voce["assegnazione"].stato == Assegnazione.Stato.ATTIVA
        ],
        "commesse": commesse,
        "chart_ore_giornaliere": _serie_giornaliera(
            anno=anno,
            mese=mese,
            righe=righe_periodo,
        ),
        "chart_ore_commessa": {
            "labels": [
                voce["assegnazione"].commessa.codice
                for voce in top_commesse
            ],
            "series": [
                {
                    "label": "Ore mese",
                    "values": [voce["ore_periodo"] for voce in top_commesse],
                }
            ],
        },
    }
