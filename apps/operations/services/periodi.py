"""
Chiusura/riapertura periodo mensile e valorizzazione economica delle ore.

Estratto da apps/operations/services.py (era un unico file da 1069 righe):
questa parte gestisce tutto ciò che riguarda i periodi mensili — calcolo del
valore economico di un periodo, chiusura e riapertura (spec §7bis).
"""
from dataclasses import dataclass
from decimal import Decimal

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from apps.projects.models import TariffaAssegnazione
from apps.timesheets.models import RigaOre, SpesaTrasferta, StatoApprovazione

from ..models import AuditLog, PeriodoMensile
from ..period_lock import lock_periodo


@dataclass(frozen=True)
class RigaValorizzata:
    riga: RigaOre
    tariffa: TariffaAssegnazione | None
    importo: Decimal | None


@dataclass(frozen=True)
class ConteggioApprovazione:
    approvate: int
    da_approvare: int
    rifiutate: int

    @property
    def totale(self) -> int:
        return self.approvate + self.da_approvare + self.rifiutate

    @property
    def bloccante(self) -> bool:
        """True se ci sono righe non ancora approvate: blocca la chiusura
        ordinaria del periodo (spec richiesta lato Admin)."""
        return (self.da_approvare + self.rifiutate) > 0


@dataclass(frozen=True)
class RiepilogoPeriodo:
    anno: int
    mese: int
    righe_valorizzate: list[RigaValorizzata]
    righe_senza_tariffa: list[RigaOre]
    spese: list[SpesaTrasferta]
    totale_ore: int
    totale_importo_ore: Decimal
    totale_spese: Decimal
    totale_fatturabile: Decimal
    numero_righe_ore: int
    numero_spese: int
    approvazione_ore: ConteggioApprovazione
    approvazione_spese: ConteggioApprovazione


def _verifica_admin(attore) -> None:
    if not (
        getattr(attore, "is_admin_lef", False)
        or getattr(attore, "is_amministrazione", False)
    ):
        raise PermissionDenied(
            "Questa operazione è riservata ad Admin LEF e Amministrazione."
        )


_CACHE_TARIFFA = "_lef_tariffa_vigente"


def precarica_tariffe(righe) -> None:
    """Risolve in blocco la tariffa vigente di ogni riga ore.

    Evita una query per riga (N+1) su dashboard, report e chiusura mensile:
    tutte le tariffe delle assegnazioni coinvolte vengono lette con una sola
    query e abbinate in memoria. Il risultato viene memorizzato sull'istanza
    e riutilizzato da ``tariffa_vigente``.
    """
    da_risolvere = [r for r in righe if not hasattr(r, _CACHE_TARIFFA)]
    if not da_risolvere:
        return

    per_chiave: dict[tuple, list[TariffaAssegnazione]] = {}
    tariffe = TariffaAssegnazione.objects.filter(
        assegnazione_id__in={r.assegnazione_id for r in da_risolvere},
    ).order_by("-valida_dal")
    for tariffa in tariffe:
        per_chiave.setdefault(
            (tariffa.assegnazione_id, tariffa.tipo_attivita), []
        ).append(tariffa)

    for riga in da_risolvere:
        trovata = None
        for tariffa in per_chiave.get((riga.assegnazione_id, riga.tipo_attivita), ()):
            if tariffa.valida_dal <= riga.data:
                trovata = tariffa
                break
        setattr(riga, _CACHE_TARIFFA, trovata)


def tariffa_vigente(riga: RigaOre) -> TariffaAssegnazione | None:
    if hasattr(riga, _CACHE_TARIFFA):
        return getattr(riga, _CACHE_TARIFFA)
    tariffa = (
        TariffaAssegnazione.objects.filter(
            assegnazione=riga.assegnazione,
            tipo_attivita=riga.tipo_attivita,
            valida_dal__lte=riga.data,
        )
        .order_by("-valida_dal")
        .first()
    )
    setattr(riga, _CACHE_TARIFFA, tariffa)
    return tariffa


def valorizza_periodo(anno: int, mese: int) -> RiepilogoPeriodo:
    righe = list(
        RigaOre.objects.filter(
            data__year=anno,
            data__month=mese,
        )
        .select_related(
            "assegnazione",
            "assegnazione__consulente",
            "assegnazione__commessa",
            "assegnazione__commessa__cliente",
            "assegnazione__fase",
        )
        .order_by(
            "data",
            "assegnazione__commessa__codice",
            "assegnazione__consulente__last_name",
        )
    )

    valorizzate: list[RigaValorizzata] = []
    mancanti: list[RigaOre] = []
    totale_ore = 0
    totale_importo_ore = Decimal("0.00")

    precarica_tariffe(righe)
    for riga in righe:
        totale_ore += riga.ore
        tariffa = tariffa_vigente(riga)
        if tariffa is None:
            mancanti.append(riga)
            valorizzate.append(
                RigaValorizzata(
                    riga=riga,
                    tariffa=None,
                    importo=None,
                )
            )
            continue

        importo = Decimal(riga.ore) * tariffa.tariffa_oraria
        totale_importo_ore += importo
        valorizzate.append(
            RigaValorizzata(
                riga=riga,
                tariffa=tariffa,
                importo=importo,
            )
        )

    spese = list(
        SpesaTrasferta.objects.filter(
            data__year=anno,
            data__month=mese,
        )
        .select_related(
            "assegnazione",
            "assegnazione__consulente",
            "assegnazione__commessa",
            "assegnazione__commessa__cliente",
            "assegnazione__fase",
        )
        .order_by("-data", "assegnazione__commessa__codice")
    )
    totale_spese = sum(
        (spesa.importo for spesa in spese), Decimal("0.00")
    )

    approvazione_ore = _conta_approvazioni(riga.stato_approvazione for riga in righe)
    approvazione_spese = _conta_approvazioni(
        spesa.stato_approvazione for spesa in spese
    )

    return RiepilogoPeriodo(
        anno=anno,
        mese=mese,
        righe_valorizzate=valorizzate,
        righe_senza_tariffa=mancanti,
        spese=spese,
        totale_ore=totale_ore,
        totale_importo_ore=totale_importo_ore,
        totale_spese=totale_spese,
        totale_fatturabile=totale_importo_ore + totale_spese,
        numero_righe_ore=len(righe),
        numero_spese=len(spese),
        approvazione_ore=approvazione_ore,
        approvazione_spese=approvazione_spese,
    )


def _conta_approvazioni(stati) -> ConteggioApprovazione:
    approvate = da_approvare = rifiutate = 0
    for stato in stati:
        if stato == StatoApprovazione.APPROVATA:
            approvate += 1
        elif stato == StatoApprovazione.RIFIUTATA:
            rifiutate += 1
        else:
            da_approvare += 1
    return ConteggioApprovazione(
        approvate=approvate,
        da_approvare=da_approvare,
        rifiutate=rifiutate,
    )


def righe_senza_tariffa(anno: int, mese: int) -> list[RigaOre]:
    return valorizza_periodo(anno, mese).righe_senza_tariffa


@transaction.atomic
def chiudi_periodo(
    *,
    attore,
    anno: int,
    mese: int,
    forza_tariffe_mancanti: bool = False,
    forza_approvazioni_mancanti: bool = False,
    motivazione: str = "",
) -> PeriodoMensile:
    _verifica_admin(attore)

    if not 1 <= mese <= 12:
        raise ValidationError("Il mese indicato non è valido.")

    # Il lock va acquisito PRIMA di valorizzare il mese. Tutte le mutazioni
    # di ore/spese usano lo stesso lock: non possono quindi inserirsi tra
    # il controllo del riepilogo e la chiusura effettiva.
    periodo = lock_periodo(anno=anno, mese=mese)
    if periodo.stato == PeriodoMensile.Stato.CHIUSO:
        raise ValidationError("Il periodo è già chiuso.")

    # Gate agenda: il mese non può essere chiuso se contiene sessioni che
    # richiedono ancora una conferma/collegamento al timesheet. In questo modo
    # non si crea il dead-lock "mese chiuso -> sessione non più confermabile".
    from apps.planning.models import GiornoPianificato

    sessioni_mese = GiornoPianificato.objects.select_for_update().filter(
        data__year=anno,
        data__month=mese,
    )
    sessioni_bloccanti = sessioni_mese.exclude(
        stato_sessione__in=GiornoPianificato.stati_risolti(),
    )
    if sessioni_bloccanti.exists():
        numero = sessioni_bloccanti.count()
        ore = sessioni_bloccanti.aggregate(totale=Sum("ore_pianificate"))["totale"] or 0
        raise ValidationError(
            f"Il periodo contiene {numero} sessioni agenda ({ore} ore) ancora da "
            "confermare/allineare e non può essere chiuso."
        )

    # Difesa aggiuntiva su stati che dichiarano un link obbligatorio.
    sessioni_link_incoerente = sessioni_mese.filter(
        stato_sessione__in=(
            GiornoPianificato.StatoSessione.CONFERMATA,
            GiornoPianificato.StatoSessione.STORICO_ALLINEATO,
        ),
        riga_ore_generata__isnull=True,
    )
    if sessioni_link_incoerente.exists():
        raise ValidationError(
            "Il periodo contiene sessioni agenda risolte ma non collegate al timesheet. "
            "Correggi l'integrità dei dati prima della chiusura."
        )

    riepilogo = valorizza_periodo(anno, mese)
    if riepilogo.righe_senza_tariffa and not forza_tariffe_mancanti:
        raise ValidationError(
            "Il periodo contiene righe senza tariffa e non può essere chiuso."
        )

    approvazioni_bloccanti = (
        riepilogo.approvazione_ore.bloccante
        or riepilogo.approvazione_spese.bloccante
    )
    if approvazioni_bloccanti and not forza_approvazioni_mancanti:
        raise ValidationError(
            "Ci sono ore o spese non ancora approvate (o rifiutate) e il "
            "periodo non può essere chiuso."
        )

    motivazione = motivazione.strip()
    richiede_motivazione = (
        riepilogo.righe_senza_tariffa or approvazioni_bloccanti
    )
    if richiede_motivazione and not motivazione:
        raise ValidationError(
            "La forzatura richiede una motivazione esplicita."
        )

    precedente = {
        "stato": periodo.stato,
        "data_chiusura": (
            periodo.data_chiusura.isoformat()
            if periodo.data_chiusura
            else None
        ),
        "forzatura_tariffe_mancanti": (
            periodo.forzatura_tariffe_mancanti
        ),
        "forzatura_approvazioni_mancanti": (
            periodo.forzatura_approvazioni_mancanti
        ),
    }

    periodo.stato = PeriodoMensile.Stato.CHIUSO
    periodo.chiuso_da = attore
    periodo.data_chiusura = timezone.now()
    periodo.forzatura_tariffe_mancanti = (
        bool(riepilogo.righe_senza_tariffa)
        and forza_tariffe_mancanti
    )
    periodo.forzatura_approvazioni_mancanti = (
        approvazioni_bloccanti and forza_approvazioni_mancanti
    )
    periodo.motivazione_forzatura = motivazione
    periodo.save()

    AuditLog.objects.create(
        utente=attore,
        entita="PeriodoMensile",
        entita_id=periodo.id,
        azione="CHIUSURA",
        valore_precedente=precedente,
        valore_nuovo={
            "stato": periodo.stato,
            "data_chiusura": periodo.data_chiusura.isoformat(),
            "forzatura_tariffe_mancanti": (
                periodo.forzatura_tariffe_mancanti
            ),
            "forzatura_approvazioni_mancanti": (
                periodo.forzatura_approvazioni_mancanti
            ),
            "numero_righe_senza_tariffa": len(
                riepilogo.righe_senza_tariffa
            ),
            "ore_da_approvare": riepilogo.approvazione_ore.da_approvare,
            "ore_rifiutate": riepilogo.approvazione_ore.rifiutate,
            "spese_da_approvare": riepilogo.approvazione_spese.da_approvare,
            "spese_rifiutate": riepilogo.approvazione_spese.rifiutate,
        },
        motivazione=motivazione,
    )
    return periodo


@transaction.atomic
def riapri_periodo(
    *,
    attore,
    anno: int,
    mese: int,
    motivazione: str,
) -> PeriodoMensile:
    _verifica_admin(attore)

    motivazione = motivazione.strip()
    if not motivazione:
        raise ValidationError(
            "La riapertura richiede una motivazione esplicita."
        )

    try:
        periodo = PeriodoMensile.objects.select_for_update().get(
            anno=anno,
            mese=mese,
        )
    except PeriodoMensile.DoesNotExist as exc:
        raise ValidationError(
            "Il periodo non risulta chiuso."
        ) from exc

    if periodo.stato != PeriodoMensile.Stato.CHIUSO:
        raise ValidationError("Il periodo è già aperto.")

    precedente = {
        "stato": periodo.stato,
        "data_chiusura": (
            periodo.data_chiusura.isoformat()
            if periodo.data_chiusura
            else None
        ),
        "forzatura_tariffe_mancanti": (
            periodo.forzatura_tariffe_mancanti
        ),
    }

    periodo.stato = PeriodoMensile.Stato.APERTO
    periodo.riaperto_da = attore
    periodo.data_riapertura = timezone.now()
    periodo.save()

    AuditLog.objects.create(
        utente=attore,
        entita="PeriodoMensile",
        entita_id=periodo.id,
        azione="RIAPERTURA",
        valore_precedente=precedente,
        valore_nuovo={
            "stato": periodo.stato,
            "data_riapertura": periodo.data_riapertura.isoformat(),
        },
        motivazione=motivazione,
    )
    return periodo



