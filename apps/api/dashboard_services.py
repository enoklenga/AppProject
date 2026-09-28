from collections import defaultdict
from decimal import Decimal

from django.db.models import Sum

from apps.operations.models import PeriodoMensile
from apps.projects.models import Assegnazione
from apps.timesheets.models import RigaOre, SpesaTrasferta


def dashboard_personale(*, utente, anno: int, mese: int) -> dict:
    assegnazioni = list(
        Assegnazione.objects.filter(consulente=utente)
        .select_related("commessa", "commessa__cliente")
        .order_by("commessa__codice")
    )

    assegnazione_ids = [assegnazione.id for assegnazione in assegnazioni]

    ore_totali = {
        elemento["assegnazione_id"]: elemento["totale"] or 0
        for elemento in (
            RigaOre.objects.filter(
                assegnazione_id__in=assegnazione_ids
            )
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
        .select_related(
            "assegnazione",
            "assegnazione__commessa",
            "assegnazione__commessa__cliente",
        )
        .order_by("-data", "-created_at")
    )

    spese_periodo = list(
        SpesaTrasferta.objects.filter(
            assegnazione__consulente=utente,
            data__year=anno,
            data__month=mese,
        )
        .select_related(
            "assegnazione",
            "assegnazione__commessa",
            "assegnazione__commessa__cliente",
        )
        .order_by("-data", "-created_at")
    )

    dati_commesse = defaultdict(
        lambda: {
            "commessa": None,
            "ore_previste": 0,
            "ore_consuntivate_totali": 0,
            "ore_periodo": 0,
            "spese_periodo": Decimal("0.00"),
            "numero_righe_ore": 0,
            "numero_spese": 0,
        }
    )

    for assegnazione in assegnazioni:
        dati = dati_commesse[assegnazione.commessa_id]
        dati["commessa"] = assegnazione.commessa
        dati["ore_previste"] += assegnazione.ore_previste
        dati["ore_consuntivate_totali"] += ore_totali.get(
            assegnazione.id,
            0,
        )

    for riga in righe_periodo:
        dati = dati_commesse[riga.assegnazione.commessa_id]
        dati["commessa"] = riga.assegnazione.commessa
        dati["ore_periodo"] += riga.ore
        dati["numero_righe_ore"] += 1

    for spesa in spese_periodo:
        dati = dati_commesse[spesa.assegnazione.commessa_id]
        dati["commessa"] = spesa.assegnazione.commessa
        dati["spese_periodo"] += spesa.importo
        dati["numero_spese"] += 1

    commesse = []
    for dati in dati_commesse.values():
        if dati["commessa"] is None:
            continue

        ore_residue = max(
            dati["ore_previste"] - dati["ore_consuntivate_totali"],
            0,
        )
        commesse.append(
            {
                "commessa_id": dati["commessa"].id,
                "codice": dati["commessa"].codice,
                "descrizione": dati["commessa"].descrizione,
                "cliente": (
                    dati["commessa"].cliente.ragione_sociale
                ),
                "stato": dati["commessa"].stato,
                "ore_previste": dati["ore_previste"],
                "ore_consuntivate_totali": (
                    dati["ore_consuntivate_totali"]
                ),
                "ore_residue": ore_residue,
                "ore_periodo": dati["ore_periodo"],
                "spese_periodo": dati["spese_periodo"],
                "numero_righe_ore": dati["numero_righe_ore"],
                "numero_spese": dati["numero_spese"],
                "superamento": (
                    dati["ore_consuntivate_totali"]
                    > dati["ore_previste"]
                ),
            }
        )

    commesse.sort(key=lambda elemento: elemento["codice"].lower())

    periodo = PeriodoMensile.objects.filter(
        anno=anno,
        mese=mese,
    ).first()

    stato_periodo = (
        periodo.stato
        if periodo is not None
        else PeriodoMensile.Stato.APERTO
    )

    totale_spese = sum(
        (spesa.importo for spesa in spese_periodo),
        Decimal("0.00"),
    )

    return {
        "anno": anno,
        "mese": mese,
        "stato_periodo": stato_periodo,
        "modificabile": stato_periodo == PeriodoMensile.Stato.APERTO,
        "totale_ore_periodo": sum(
            riga.ore for riga in righe_periodo
        ),
        "totale_spese_periodo": totale_spese,
        "numero_righe_ore": len(righe_periodo),
        "numero_spese": len(spese_periodo),
        "commesse": commesse,
    }
