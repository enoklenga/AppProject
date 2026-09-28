from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from apps.operations.models import AuditLog, PeriodoMensile
from apps.operations.period_lock import verifica_periodi_aperti
from apps.projects.models import Assegnazione, Commessa, TariffaAssegnazione
from apps.projects.workflow import commessa_permette_operativita
from .models import RigaOre, SpesaTrasferta, StatoApprovazione

User = get_user_model()


@dataclass(frozen=True)
class EsitoOre:
    riga: RigaOre
    monte_ore_superato: bool
    limite_giornaliero_superato: bool


def periodo_chiuso(giorno: date) -> bool:
    return PeriodoMensile.objects.filter(
        anno=giorno.year,
        mese=giorno.month,
        stato=PeriodoMensile.Stato.CHIUSO,
    ).exists()


def tariffa_vigente(
    assegnazione: Assegnazione,
    tipo_attivita: str,
    giorno: date,
) -> TariffaAssegnazione | None:
    return (
        TariffaAssegnazione.objects.filter(
            assegnazione=assegnazione,
            tipo_attivita=tipo_attivita,
            valida_dal__lte=giorno,
        )
        .order_by("-valida_dal")
        .first()
    )


def importo_riga(riga: RigaOre) -> Decimal | None:
    tariffa = tariffa_vigente(
        riga.assegnazione,
        riga.tipo_attivita,
        riga.data,
    )
    if tariffa is None:
        return None
    return Decimal(riga.ore) * tariffa.tariffa_oraria


def _is_admin(attore: User) -> bool:
    return bool(getattr(attore, "is_admin_lef", False))


def _valida_assegnazione(
    *,
    attore: User,
    assegnazione: Assegnazione,
    giorno: date,
) -> None:
    if not _is_admin(attore) and assegnazione.consulente_id != attore.id:
        raise PermissionDenied(
            "Non puoi registrare dati per un altro consulente."
        )

    if assegnazione.stato != Assegnazione.Stato.ATTIVA:
        raise ValidationError("L'assegnazione non è attiva.")

    if not commessa_permette_operativita(assegnazione.commessa):
        raise ValidationError(
            "La commessa non è operativa: è chiusa o sospesa nel workflow."
        )

    if giorno < assegnazione.commessa.data_inizio:
        raise ValidationError(
            {"data": "La data precede l'inizio della commessa."}
        )

    if (
        assegnazione.commessa.data_fine_prevista
        and giorno > assegnazione.commessa.data_fine_prevista
    ):
        raise ValidationError(
            {"data": "La data supera la fine prevista della commessa."}
        )

    if giorno < assegnazione.data_inizio:
        raise ValidationError(
            {"data": "La data precede l'inizio dell'assegnazione."}
        )

    if assegnazione.data_fine and giorno > assegnazione.data_fine:
        raise ValidationError(
            {"data": "La data supera la fine dell'assegnazione."}
        )

    if assegnazione.fase_id:
        if giorno < assegnazione.fase.data_inizio:
            raise ValidationError(
                {"data": "La data precede l'inizio della fase."}
            )
        if (
            assegnazione.fase.data_fine_prevista
            and giorno > assegnazione.fase.data_fine_prevista
        ):
            raise ValidationError(
                {"data": "La data supera la fine prevista della fase."}
            )

    if periodo_chiuso(giorno):
        raise ValidationError(
            "Il mese selezionato è chiuso. Deve essere riaperto da un Admin."
        )


def _valida_modifica_consulente(attore: User, oggetto: Any) -> None:
    if _is_admin(attore):
        return

    if oggetto.assegnazione.consulente_id != attore.id:
        raise PermissionDenied("Il dato non appartiene al consulente.")

    if oggetto.bloccata_per_consulente:
        raise PermissionDenied(
            "Il dato è stato modificato da un Admin ed è ora bloccato."
        )


def _valida_riga_non_generata_da_agenda(riga: RigaOre) -> None:
    # Import locale per evitare dipendenze circolari tra planning e timesheet.
    from apps.planning.models import GiornoPianificato

    if GiornoPianificato.objects.filter(riga_ore_generata_id=riga.id).exists():
        raise ValidationError(
            "Questa riga è stata generata dalla conferma di una sessione in agenda "
            "e non può essere modificata o eliminata dal timesheet."
        )


def _registra_audit(
    *,
    attore: User,
    entita: str,
    entita_id,
    azione: str,
    precedente: dict | None,
    nuovo: dict | None,
    motivazione: str = "",
) -> None:
    AuditLog.objects.create(
        utente=attore,
        entita=entita,
        entita_id=entita_id,
        azione=azione,
        valore_precedente=precedente,
        valore_nuovo=nuovo,
        motivazione=motivazione.strip(),
    )


def _riga_ore_dict(riga: RigaOre) -> dict:
    return {
        "assegnazione_id": str(riga.assegnazione_id),
        "data": riga.data.isoformat(),
        "tipo_attivita": riga.tipo_attivita,
        "ore": riga.ore,
        "nota": riga.nota,
        "versione": riga.versione,
        "bloccata_per_consulente": riga.bloccata_per_consulente,
    }


def _spesa_dict(spesa: SpesaTrasferta) -> dict:
    return {
        "assegnazione_id": str(spesa.assegnazione_id),
        "data": spesa.data.isoformat(),
        "categoria": spesa.categoria,
        "importo": str(spesa.importo),
        "nota": spesa.nota,
        "versione": spesa.versione,
        "bloccata_per_consulente": spesa.bloccata_per_consulente,
    }


def _totale_giornaliero(
    *,
    consulente_id,
    giorno: date,
    escludi_riga_id=None,
) -> int:
    queryset = RigaOre.objects.filter(
        assegnazione__consulente_id=consulente_id,
        data=giorno,
    )
    if escludi_riga_id:
        queryset = queryset.exclude(pk=escludi_riga_id)
    return queryset.aggregate(totale=Sum("ore"))["totale"] or 0


def _esito_ore(
    riga: RigaOre,
    *,
    limite_giornaliero_superato: bool,
) -> EsitoOre:
    totale_assegnazione = (
        RigaOre.objects.filter(
            assegnazione=riga.assegnazione,
        ).aggregate(totale=Sum("ore"))["totale"]
        or 0
    )
    return EsitoOre(
        riga=riga,
        monte_ore_superato=(
            totale_assegnazione > riga.assegnazione.ore_previste
        ),
        limite_giornaliero_superato=limite_giornaliero_superato,
    )


@transaction.atomic
def inserisci_ore(
    *,
    attore: User,
    assegnazione_id,
    giorno: date,
    tipo_attivita: str,
    ore: int,
    nota: str = "",
    motivazione: str = "",
) -> EsitoOre:
    if ore <= 0:
        raise ValidationError(
            {"ore": "Le ore devono essere maggiori di zero."}
        )

    # Serializza la scrittura rispetto alla chiusura del mese.
    verifica_periodi_aperti(giorno)

    assegnazione = (
        Assegnazione.objects.select_related("commessa", "consulente", "fase")
        .select_for_update()
        .get(pk=assegnazione_id)
    )
    _valida_assegnazione(
        attore=attore,
        assegnazione=assegnazione,
        giorno=giorno,
    )

    User.objects.select_for_update().get(pk=assegnazione.consulente_id)
    nuovo_totale = _totale_giornaliero(
        consulente_id=assegnazione.consulente_id,
        giorno=giorno,
    ) + ore

    admin = _is_admin(attore)
    if not admin and nuovo_totale > 8:
        raise ValidationError(
            {"ore": "Il totale giornaliero supererebbe il limite di 8 ore."}
        )
    motivazione = (motivazione or "").strip()
    if admin and nuovo_totale > 8 and not motivazione:
        raise ValidationError(
            {"motivazione": "Per superare il limite giornaliero di 8 ore l'Admin deve indicare una motivazione."}
        )

    riga = RigaOre.objects.create(
        assegnazione=assegnazione,
        data=giorno,
        tipo_attivita=tipo_attivita,
        ore=ore,
        nota=nota.strip(),
        inserita_da=attore,
        ultima_modifica_da=attore,
        modificata_da_admin=admin,
        bloccata_per_consulente=admin,
    )

    if admin:
        _registra_audit(
            attore=attore,
            entita="RigaOre",
            entita_id=riga.id,
            azione="INSERIMENTO_ADMIN",
            precedente=None,
            nuovo=_riga_ore_dict(riga),
            motivazione=motivazione,
        )

    return _esito_ore(
        riga,
        limite_giornaliero_superato=nuovo_totale > 8,
    )


@transaction.atomic
def modifica_ore(
    *,
    attore: User,
    riga_id,
    versione: int,
    assegnazione_id,
    giorno: date,
    tipo_attivita: str,
    ore: int,
    nota: str = "",
    motivazione: str = "",
) -> EsitoOre:
    riga = (
        RigaOre.objects.select_related(
            "assegnazione",
            "assegnazione__commessa",
            "assegnazione__consulente",
            "assegnazione__fase",
        )
        .select_for_update()
        .get(pk=riga_id)
    )
    _valida_riga_non_generata_da_agenda(riga)
    _valida_modifica_consulente(attore, riga)

    if riga.versione != versione:
        raise ValidationError(
            "Il dato è stato modificato da un altro utente. Ricarica la pagina."
        )

    # Difesa anche a livello di servizio/API: il form web già impedisce
    # valori non positivi, ma la stessa regola deve valere per ogni canale.
    if ore <= 0:
        raise ValidationError({"ore": "Le ore devono essere maggiori di zero."})

    # Se la riga viene spostata tra mesi, blocchiamo entrambi i periodi
    # in ordine stabile prima di verificare/apportare la modifica.
    verifica_periodi_aperti(riga.data, giorno)

    nuova_assegnazione = (
        Assegnazione.objects.select_related("commessa", "consulente", "fase")
        .select_for_update()
        .get(pk=assegnazione_id)
    )
    _valida_assegnazione(
        attore=attore,
        assegnazione=nuova_assegnazione,
        giorno=giorno,
    )

    User.objects.select_for_update().get(
        pk=nuova_assegnazione.consulente_id
    )
    nuovo_totale = _totale_giornaliero(
        consulente_id=nuova_assegnazione.consulente_id,
        giorno=giorno,
        escludi_riga_id=riga.id,
    ) + ore

    admin = _is_admin(attore)
    if not admin and nuovo_totale > 8:
        raise ValidationError(
            {"ore": "Il totale giornaliero supererebbe il limite di 8 ore."}
        )
    motivazione = (motivazione or "").strip()
    if admin and nuovo_totale > 8 and not motivazione:
        raise ValidationError(
            {"motivazione": "Per superare il limite giornaliero di 8 ore l'Admin deve indicare una motivazione."}
        )

    precedente = _riga_ore_dict(riga)

    riga.assegnazione = nuova_assegnazione
    riga.data = giorno
    riga.tipo_attivita = tipo_attivita
    riga.ore = ore
    riga.nota = nota.strip()
    riga.ultima_modifica_da = attore
    riga.versione += 1

    if admin:
        riga.modificata_da_admin = True
        riga.bloccata_per_consulente = True
    elif riga.stato_approvazione == StatoApprovazione.RIFIUTATA:
        # Il consulente ha corretto una riga rifiutata: torna "da approvare"
        # cosi' l'Admin la ricontrolla.
        riga.stato_approvazione = StatoApprovazione.IN_ATTESA
        riga.nota_approvazione = ""

    riga.save()

    if admin:
        _registra_audit(
            attore=attore,
            entita="RigaOre",
            entita_id=riga.id,
            azione="MODIFICA_ADMIN",
            precedente=precedente,
            nuovo=_riga_ore_dict(riga),
            motivazione=motivazione,
        )

    return _esito_ore(
        riga,
        limite_giornaliero_superato=nuovo_totale > 8,
    )


@transaction.atomic
def elimina_ore(
    *,
    attore: User,
    riga_id,
    versione: int,
    motivazione: str = "",
) -> None:
    riga = (
        RigaOre.objects.select_related(
            "assegnazione",
            "assegnazione__commessa",
        )
        .select_for_update()
        .get(pk=riga_id)
    )
    _valida_riga_non_generata_da_agenda(riga)
    _valida_modifica_consulente(attore, riga)

    if riga.versione != versione:
        raise ValidationError(
            "Il dato è stato modificato. Ricarica la pagina."
        )

    verifica_periodi_aperti(riga.data)

    precedente = _riga_ore_dict(riga)
    riga_id_salvato = riga.id
    riga.delete()

    if _is_admin(attore):
        _registra_audit(
            attore=attore,
            entita="RigaOre",
            entita_id=riga_id_salvato,
            azione="CANCELLAZIONE_ADMIN",
            precedente=precedente,
            nuovo=None,
            motivazione=motivazione,
        )


@transaction.atomic
def inserisci_spesa(
    *,
    attore: User,
    assegnazione_id,
    giorno: date,
    categoria: str,
    importo: Decimal,
    nota: str = "",
) -> SpesaTrasferta:
    # Serializza la scrittura rispetto alla chiusura del mese.
    verifica_periodi_aperti(giorno)

    assegnazione = (
        Assegnazione.objects.select_related("commessa", "consulente", "fase")
        .select_for_update()
        .get(pk=assegnazione_id)
    )
    _valida_assegnazione(
        attore=attore,
        assegnazione=assegnazione,
        giorno=giorno,
    )

    if importo <= 0:
        raise ValidationError(
            {"importo": "L'importo deve essere maggiore di zero."}
        )

    admin = _is_admin(attore)
    spesa = SpesaTrasferta.objects.create(
        assegnazione=assegnazione,
        data=giorno,
        categoria=categoria,
        importo=importo,
        nota=nota.strip(),
        inserita_da=attore,
        ultima_modifica_da=attore,
        modificata_da_admin=admin,
        bloccata_per_consulente=admin,
    )

    if admin:
        _registra_audit(
            attore=attore,
            entita="SpesaTrasferta",
            entita_id=spesa.id,
            azione="INSERIMENTO_ADMIN",
            precedente=None,
            nuovo=_spesa_dict(spesa),
        )

    return spesa


@transaction.atomic
def modifica_spesa(
    *,
    attore: User,
    spesa_id,
    versione: int,
    assegnazione_id,
    giorno: date,
    categoria: str,
    importo: Decimal,
    nota: str = "",
    motivazione: str = "",
) -> SpesaTrasferta:
    spesa = (
        SpesaTrasferta.objects.select_related(
            "assegnazione",
            "assegnazione__commessa",
            "assegnazione__consulente",
            "assegnazione__fase",
        )
        .select_for_update()
        .get(pk=spesa_id)
    )
    _valida_modifica_consulente(attore, spesa)

    if spesa.versione != versione:
        raise ValidationError(
            "Il dato è stato modificato da un altro utente. Ricarica la pagina."
        )

    verifica_periodi_aperti(spesa.data, giorno)

    nuova_assegnazione = (
        Assegnazione.objects.select_related("commessa", "consulente", "fase")
        .select_for_update()
        .get(pk=assegnazione_id)
    )
    _valida_assegnazione(
        attore=attore,
        assegnazione=nuova_assegnazione,
        giorno=giorno,
    )

    if importo <= 0:
        raise ValidationError(
            {"importo": "L'importo deve essere maggiore di zero."}
        )

    precedente = _spesa_dict(spesa)
    admin = _is_admin(attore)

    spesa.assegnazione = nuova_assegnazione
    spesa.data = giorno
    spesa.categoria = categoria
    spesa.importo = importo
    spesa.nota = nota.strip()
    spesa.ultima_modifica_da = attore
    spesa.versione += 1

    if admin:
        spesa.modificata_da_admin = True
        spesa.bloccata_per_consulente = True
    elif spesa.stato_approvazione == StatoApprovazione.RIFIUTATA:
        spesa.stato_approvazione = StatoApprovazione.IN_ATTESA
        spesa.nota_approvazione = ""

    spesa.save()

    if admin:
        _registra_audit(
            attore=attore,
            entita="SpesaTrasferta",
            entita_id=spesa.id,
            azione="MODIFICA_ADMIN",
            precedente=precedente,
            nuovo=_spesa_dict(spesa),
            motivazione=motivazione,
        )

    return spesa


@transaction.atomic
def elimina_spesa(
    *,
    attore: User,
    spesa_id,
    versione: int,
    motivazione: str = "",
) -> None:
    spesa = (
        SpesaTrasferta.objects.select_related(
            "assegnazione",
            "assegnazione__commessa",
        )
        .select_for_update()
        .get(pk=spesa_id)
    )
    _valida_modifica_consulente(attore, spesa)

    if spesa.versione != versione:
        raise ValidationError(
            "Il dato è stato modificato. Ricarica la pagina."
        )

    verifica_periodi_aperti(spesa.data)

    precedente = _spesa_dict(spesa)
    spesa_id_salvato = spesa.id
    spesa.delete()

    if _is_admin(attore):
        _registra_audit(
            attore=attore,
            entita="SpesaTrasferta",
            entita_id=spesa_id_salvato,
            azione="CANCELLAZIONE_ADMIN",
            precedente=precedente,
            nuovo=None,
            motivazione=motivazione,
        )


def _verifica_admin(attore: User) -> None:
    if not (
        _is_admin(attore)
        or getattr(attore, "is_amministrazione", False)
    ):
        raise PermissionDenied(
            "L'approvazione di ore e spese è riservata ad Admin LEF e Amministrazione."
        )


@transaction.atomic
def approva_riga_ore(*, attore: User, riga_id, motivazione: str = "") -> RigaOre:
    riga = (
        RigaOre.objects.select_related("assegnazione")
        .select_for_update()
        .get(pk=riga_id)
    )
    _verifica_admin(attore)

    verifica_periodi_aperti(riga.data)

    precedente = _riga_ore_dict(riga)

    riga.stato_approvazione = StatoApprovazione.APPROVATA
    riga.nota_approvazione = motivazione.strip()
    riga.approvata_da = attore
    riga.data_approvazione = timezone.now()
    riga.save(
        update_fields=[
            "stato_approvazione",
            "nota_approvazione",
            "approvata_da",
            "data_approvazione",
        ]
    )

    _registra_audit(
        attore=attore,
        entita="RigaOre",
        entita_id=riga.id,
        azione="APPROVAZIONE_ORE",
        precedente=precedente,
        nuovo=_riga_ore_dict(riga),
        motivazione=motivazione,
    )
    return riga


@transaction.atomic
def rifiuta_riga_ore(*, attore: User, riga_id, motivazione: str) -> RigaOre:
    riga = (
        RigaOre.objects.select_related("assegnazione")
        .select_for_update()
        .get(pk=riga_id)
    )
    _verifica_admin(attore)

    motivazione = motivazione.strip()
    if not motivazione:
        raise ValidationError(
            "Il rifiuto richiede una motivazione, così il consulente sa cosa correggere."
        )

    verifica_periodi_aperti(riga.data)

    precedente = _riga_ore_dict(riga)

    riga.stato_approvazione = StatoApprovazione.RIFIUTATA
    riga.nota_approvazione = motivazione
    riga.approvata_da = attore
    riga.data_approvazione = timezone.now()
    # La riga torna modificabile dal consulente, cosi' puo' correggerla.
    riga.bloccata_per_consulente = False
    riga.save(
        update_fields=[
            "stato_approvazione",
            "nota_approvazione",
            "approvata_da",
            "data_approvazione",
            "bloccata_per_consulente",
        ]
    )

    _registra_audit(
        attore=attore,
        entita="RigaOre",
        entita_id=riga.id,
        azione="RIFIUTO_ORE",
        precedente=precedente,
        nuovo=_riga_ore_dict(riga),
        motivazione=motivazione,
    )
    return riga


@transaction.atomic
def approva_spesa(*, attore: User, spesa_id, motivazione: str = "") -> SpesaTrasferta:
    spesa = (
        SpesaTrasferta.objects.select_related("assegnazione")
        .select_for_update()
        .get(pk=spesa_id)
    )
    _verifica_admin(attore)

    verifica_periodi_aperti(spesa.data)

    precedente = _spesa_dict(spesa)

    spesa.stato_approvazione = StatoApprovazione.APPROVATA
    spesa.nota_approvazione = motivazione.strip()
    spesa.approvata_da = attore
    spesa.data_approvazione = timezone.now()
    spesa.save(
        update_fields=[
            "stato_approvazione",
            "nota_approvazione",
            "approvata_da",
            "data_approvazione",
        ]
    )

    _registra_audit(
        attore=attore,
        entita="SpesaTrasferta",
        entita_id=spesa.id,
        azione="APPROVAZIONE_SPESA",
        precedente=precedente,
        nuovo=_spesa_dict(spesa),
        motivazione=motivazione,
    )
    return spesa


@transaction.atomic
def rifiuta_spesa(*, attore: User, spesa_id, motivazione: str) -> SpesaTrasferta:
    spesa = (
        SpesaTrasferta.objects.select_related("assegnazione")
        .select_for_update()
        .get(pk=spesa_id)
    )
    _verifica_admin(attore)

    motivazione = motivazione.strip()
    if not motivazione:
        raise ValidationError(
            "Il rifiuto richiede una motivazione, così il consulente sa cosa correggere."
        )

    verifica_periodi_aperti(spesa.data)

    precedente = _spesa_dict(spesa)

    spesa.stato_approvazione = StatoApprovazione.RIFIUTATA
    spesa.nota_approvazione = motivazione
    spesa.approvata_da = attore
    spesa.data_approvazione = timezone.now()
    spesa.bloccata_per_consulente = False
    spesa.save(
        update_fields=[
            "stato_approvazione",
            "nota_approvazione",
            "approvata_da",
            "data_approvazione",
            "bloccata_per_consulente",
        ]
    )

    _registra_audit(
        attore=attore,
        entita="SpesaTrasferta",
        entita_id=spesa.id,
        azione="RIFIUTO_SPESA",
        precedente=precedente,
        nuovo=_spesa_dict(spesa),
        motivazione=motivazione,
    )
    return spesa
