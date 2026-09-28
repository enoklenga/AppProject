"""
Dashboard riepilogativa per Admin e Project Manager (spec §6, §5bis).

Estratto da apps/operations/services.py: calcolo degli aggregati economici
per Admin (con importi) e per PM (senza importi, mai esposti — spec §5bis.3).
"""
from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal

from django.core.exceptions import PermissionDenied
from django.db.models import Sum

from apps.projects.models import Assegnazione, Commessa
from apps.timesheets.models import RigaOre, SpesaTrasferta

from .periodi import precarica_tariffe, tariffa_vigente


@dataclass(frozen=True)
class AggregatoEconomico:
    chiave: str
    etichetta: str
    ore: int
    valore_ore: Decimal
    spese: Decimal
    totale: Decimal
    righe_senza_tariffa: int


@dataclass(frozen=True)
class AvanzamentoCommessa:
    commessa: Commessa
    ore_previste: int
    ore_consuntivate: int
    ore_residue: int
    ore_periodo: int
    valore_ore_periodo: Decimal
    spese_periodo: Decimal
    totale_periodo: Decimal
    righe_senza_tariffa: int
    superamento: bool


@dataclass(frozen=True)
class DashboardAdminData:
    anno: int
    mese: int
    totale_ore: int
    totale_valore_ore: Decimal
    totale_spese: Decimal
    totale_fatturabile: Decimal
    numero_righe_senza_tariffa: int
    avanzamento_commesse: list[AvanzamentoCommessa]
    per_cliente: list[AggregatoEconomico]
    per_commessa: list[AggregatoEconomico]
    per_fase: list[AggregatoEconomico]
    per_consulente: list[AggregatoEconomico]


@dataclass(frozen=True)
class AvanzamentoConsulentePM:
    assegnazione: Assegnazione
    ore_previste: int
    ore_consuntivate: int
    ore_residue: int
    ore_periodo: int
    superamento: bool


@dataclass(frozen=True)
class DashboardPMData:
    anno: int
    mese: int
    commessa: Commessa
    totale_ore_periodo: int
    totale_ore_consuntivate: int
    totale_ore_previste: int
    totale_ore_residue: int
    team: list[AvanzamentoConsulentePM]
    righe_ore: list[RigaOre]


def _filtra_query_periodo(
    queryset,
    *,
    anno: int,
    mese: int,
    cliente_id=None,
    commessa_id=None,
    consulente_id=None,
    fase_id=None,
):
    queryset = queryset.filter(data__year=anno, data__month=mese)
    if cliente_id:
        queryset = queryset.filter(
            assegnazione__commessa__cliente_id=cliente_id
        )
    if commessa_id:
        queryset = queryset.filter(
            assegnazione__commessa_id=commessa_id
        )
    if consulente_id:
        queryset = queryset.filter(assegnazione__consulente_id=consulente_id)
    if fase_id:
        queryset = queryset.filter(assegnazione__fase_id=fase_id)
    return queryset


def _crea_aggregati_economici(
    *,
    righe: list[RigaOre],
    spese: list[SpesaTrasferta],
    chiave_riga,
    etichetta_riga,
    chiave_spesa,
    etichetta_spesa,
) -> list[AggregatoEconomico]:
    valori = defaultdict(
        lambda: {
            "etichetta": "",
            "ore": 0,
            "valore_ore": Decimal("0.00"),
            "spese": Decimal("0.00"),
            "mancanti": 0,
        }
    )

    for riga in righe:
        chiave = str(chiave_riga(riga))
        voce = valori[chiave]
        voce["etichetta"] = etichetta_riga(riga)
        voce["ore"] += riga.ore

        tariffa = tariffa_vigente(riga)
        if tariffa is None:
            voce["mancanti"] += 1
        else:
            voce["valore_ore"] += (
                Decimal(riga.ore) * tariffa.tariffa_oraria
            )

    for spesa in spese:
        chiave = str(chiave_spesa(spesa))
        voce = valori[chiave]
        voce["etichetta"] = etichetta_spesa(spesa)
        voce["spese"] += spesa.importo

    return sorted(
        [
            AggregatoEconomico(
                chiave=chiave,
                etichetta=dati["etichetta"],
                ore=dati["ore"],
                valore_ore=dati["valore_ore"],
                spese=dati["spese"],
                totale=dati["valore_ore"] + dati["spese"],
                righe_senza_tariffa=dati["mancanti"],
            )
            for chiave, dati in valori.items()
        ],
        key=lambda elemento: elemento.etichetta.lower(),
    )


def dashboard_admin(
    *,
    anno: int,
    mese: int,
    cliente_id=None,
    commessa_id=None,
    consulente_id=None,
    fase_id=None,
) -> DashboardAdminData:
    righe_qs = RigaOre.objects.select_related(
        "assegnazione",
        "assegnazione__consulente",
        "assegnazione__commessa",
        "assegnazione__commessa__cliente",
        "assegnazione__fase",
    )
    righe_qs = _filtra_query_periodo(
        righe_qs,
        anno=anno,
        mese=mese,
        cliente_id=cliente_id,
        commessa_id=commessa_id,
        consulente_id=consulente_id,
        fase_id=fase_id,
    )
    righe = list(righe_qs.order_by("data", "created_at"))
    precarica_tariffe(righe)

    spese_qs = SpesaTrasferta.objects.select_related(
        "assegnazione",
        "assegnazione__consulente",
        "assegnazione__commessa",
        "assegnazione__commessa__cliente",
        "assegnazione__fase",
    )
    spese_qs = _filtra_query_periodo(
        spese_qs,
        anno=anno,
        mese=mese,
        cliente_id=cliente_id,
        commessa_id=commessa_id,
        consulente_id=consulente_id,
        fase_id=fase_id,
    )
    spese = list(spese_qs.order_by("data", "created_at"))

    totale_ore = sum(riga.ore for riga in righe)
    totale_valore_ore = Decimal("0.00")
    mancanti = 0

    for riga in righe:
        tariffa = tariffa_vigente(riga)
        if tariffa is None:
            mancanti += 1
        else:
            totale_valore_ore += (
                Decimal(riga.ore) * tariffa.tariffa_oraria
            )

    totale_spese = sum(
        (spesa.importo for spesa in spese),
        Decimal("0.00"),
    )

    assegnazioni = Assegnazione.objects.select_related(
        "commessa",
        "commessa__cliente",
        "consulente",
    )
    if cliente_id:
        assegnazioni = assegnazioni.filter(
            commessa__cliente_id=cliente_id
        )
    if commessa_id:
        assegnazioni = assegnazioni.filter(commessa_id=commessa_id)
    if consulente_id:
        assegnazioni = assegnazioni.filter(consulente_id=consulente_id)
    if fase_id:
        assegnazioni = assegnazioni.filter(fase_id=fase_id)

    assegnazioni = list(assegnazioni)

    ore_totali_per_assegnazione = {
        elemento["assegnazione_id"]: elemento["totale"] or 0
        for elemento in (
            RigaOre.objects.filter(
                assegnazione_id__in=[
                    assegnazione.id
                    for assegnazione in assegnazioni
                ]
            )
            .values("assegnazione_id")
            .annotate(totale=Sum("ore"))
        )
    }

    dati_commessa = defaultdict(
        lambda: {
            "commessa": None,
            "previste": 0,
            "consuntivate": 0,
            "periodo": 0,
            "valore": Decimal("0.00"),
            "spese": Decimal("0.00"),
            "mancanti": 0,
        }
    )

    for assegnazione in assegnazioni:
        dati = dati_commessa[assegnazione.commessa_id]
        dati["commessa"] = assegnazione.commessa
        dati["previste"] += assegnazione.ore_previste
        dati["consuntivate"] += ore_totali_per_assegnazione.get(
            assegnazione.id,
            0,
        )

    for riga in righe:
        dati = dati_commessa[riga.assegnazione.commessa_id]
        dati["commessa"] = riga.assegnazione.commessa
        dati["periodo"] += riga.ore
        tariffa = tariffa_vigente(riga)
        if tariffa is None:
            dati["mancanti"] += 1
        else:
            dati["valore"] += (
                Decimal(riga.ore) * tariffa.tariffa_oraria
            )

    for spesa in spese:
        dati = dati_commessa[spesa.assegnazione.commessa_id]
        dati["commessa"] = spesa.assegnazione.commessa
        dati["spese"] += spesa.importo

    avanzamento_commesse = sorted(
        [
            AvanzamentoCommessa(
                commessa=dati["commessa"],
                ore_previste=dati["previste"],
                ore_consuntivate=dati["consuntivate"],
                ore_residue=max(
                    dati["previste"] - dati["consuntivate"],
                    0,
                ),
                ore_periodo=dati["periodo"],
                valore_ore_periodo=dati["valore"],
                spese_periodo=dati["spese"],
                totale_periodo=dati["valore"] + dati["spese"],
                righe_senza_tariffa=dati["mancanti"],
                superamento=(
                    dati["consuntivate"] > dati["previste"]
                ),
            )
            for dati in dati_commessa.values()
            if dati["commessa"] is not None
        ],
        key=lambda elemento: elemento.commessa.codice.lower(),
    )

    per_cliente = _crea_aggregati_economici(
        righe=righe,
        spese=spese,
        chiave_riga=lambda riga: (
            riga.assegnazione.commessa.cliente_id
        ),
        etichetta_riga=lambda riga: (
            riga.assegnazione.commessa.cliente.ragione_sociale
        ),
        chiave_spesa=lambda spesa: (
            spesa.assegnazione.commessa.cliente_id
        ),
        etichetta_spesa=lambda spesa: (
            spesa.assegnazione.commessa.cliente.ragione_sociale
        ),
    )

    per_commessa = _crea_aggregati_economici(
        righe=righe,
        spese=spese,
        chiave_riga=lambda riga: riga.assegnazione.commessa_id,
        etichetta_riga=lambda riga: (
            f"{riga.assegnazione.commessa.codice} – "
            f"{riga.assegnazione.commessa.cliente.ragione_sociale}"
        ),
        chiave_spesa=lambda spesa: spesa.assegnazione.commessa_id,
        etichetta_spesa=lambda spesa: (
            f"{spesa.assegnazione.commessa.codice} – "
            f"{spesa.assegnazione.commessa.cliente.ragione_sociale}"
        ),
    )

    # Ogni assegnazione appartiene obbligatoriamente a una fase:
    # il dettaglio economico viene quindi sempre letto nel contesto
    # commessa + fase.
    per_fase = _crea_aggregati_economici(
        righe=righe,
        spese=spese,
        chiave_riga=lambda riga: (
            riga.assegnazione.fase_id
        ),
        etichetta_riga=lambda riga: (
            f"{riga.assegnazione.commessa.codice} – {riga.assegnazione.fase.nome}"
        ),
        chiave_spesa=lambda spesa: (
            spesa.assegnazione.fase_id
        ),
        etichetta_spesa=lambda spesa: (
            f"{spesa.assegnazione.commessa.codice} – {spesa.assegnazione.fase.nome}"
        ),
    )

    per_consulente = _crea_aggregati_economici(
        righe=righe,
        spese=spese,
        chiave_riga=lambda riga: riga.assegnazione.consulente_id,
        etichetta_riga=lambda riga: str(
            riga.assegnazione.consulente
        ),
        chiave_spesa=lambda spesa: (
            spesa.assegnazione.consulente_id
        ),
        etichetta_spesa=lambda spesa: str(
            spesa.assegnazione.consulente
        ),
    )

    return DashboardAdminData(
        anno=anno,
        mese=mese,
        totale_ore=totale_ore,
        totale_valore_ore=totale_valore_ore,
        totale_spese=totale_spese,
        totale_fatturabile=totale_valore_ore + totale_spese,
        numero_righe_senza_tariffa=mancanti,
        avanzamento_commesse=avanzamento_commesse,
        per_cliente=per_cliente,
        per_commessa=per_commessa,
        per_fase=per_fase,
        per_consulente=per_consulente,
    )


def commesse_gestite_da_pm(utente):
    return (
        Commessa.objects.filter(
            assegnazioni__consulente=utente,
            assegnazioni__ruolo_commessa=(
                Assegnazione.Ruolo.PROJECT_MANAGER
            ),
            assegnazioni__stato=Assegnazione.Stato.ATTIVA,
        )
        .select_related("cliente")
        .distinct()
        .order_by("codice")
    )


def dashboard_pm(
    *,
    utente,
    commessa_id,
    anno: int,
    mese: int,
) -> DashboardPMData:
    if getattr(utente, "is_admin_lef", False):
        raise PermissionDenied(
            "La dashboard PM è riservata ai consulenti con ruolo PM."
        )

    autorizzata = Assegnazione.objects.filter(
        consulente=utente,
        commessa_id=commessa_id,
        ruolo_commessa=Assegnazione.Ruolo.PROJECT_MANAGER,
        stato=Assegnazione.Stato.ATTIVA,
    ).exists()

    if not autorizzata:
        raise PermissionDenied(
            "Non hai un'assegnazione PM attiva su questa commessa."
        )

    commessa = Commessa.objects.select_related("cliente").get(
        pk=commessa_id
    )

    assegnazioni = list(
        Assegnazione.objects.filter(commessa=commessa)
        .select_related("consulente", "fase")
        .order_by(
            "consulente__last_name",
            "consulente__first_name",
            "consulente__email",
        )
    )

    ore_totali = {
        elemento["assegnazione_id"]: elemento["totale"] or 0
        for elemento in (
            RigaOre.objects.filter(
                assegnazione_id__in=[
                    assegnazione.id
                    for assegnazione in assegnazioni
                ]
            )
            .values("assegnazione_id")
            .annotate(totale=Sum("ore"))
        )
    }

    ore_periodo = {
        elemento["assegnazione_id"]: elemento["totale"] or 0
        for elemento in (
            RigaOre.objects.filter(
                assegnazione_id__in=[
                    assegnazione.id
                    for assegnazione in assegnazioni
                ],
                data__year=anno,
                data__month=mese,
            )
            .values("assegnazione_id")
            .annotate(totale=Sum("ore"))
        )
    }

    team = []
    for assegnazione in assegnazioni:
        consuntivate = ore_totali.get(assegnazione.id, 0)
        team.append(
            AvanzamentoConsulentePM(
                assegnazione=assegnazione,
                ore_previste=assegnazione.ore_previste,
                ore_consuntivate=consuntivate,
                ore_residue=max(
                    assegnazione.ore_previste - consuntivate,
                    0,
                ),
                ore_periodo=ore_periodo.get(
                    assegnazione.id,
                    0,
                ),
                superamento=(
                    consuntivate > assegnazione.ore_previste
                ),
            )
        )

    righe = list(
        RigaOre.objects.filter(
            assegnazione__commessa=commessa,
            data__year=anno,
            data__month=mese,
        )
        .select_related(
            "assegnazione",
            "assegnazione__consulente",
            "assegnazione__fase",
        )
        .order_by(
            "-data",
            "assegnazione__consulente__last_name",
        )
    )

    totale_previste = sum(
        elemento.ore_previste for elemento in team
    )
    totale_consuntivate = sum(
        elemento.ore_consuntivate for elemento in team
    )

    return DashboardPMData(
        anno=anno,
        mese=mese,
        commessa=commessa,
        totale_ore_periodo=sum(
            elemento.ore_periodo for elemento in team
        ),
        totale_ore_consuntivate=totale_consuntivate,
        totale_ore_previste=totale_previste,
        totale_ore_residue=max(
            totale_previste - totale_consuntivate,
            0,
        ),
        team=team,
        righe_ore=righe,
    )



