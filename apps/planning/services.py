from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from apps.operations.models import AuditLog
from apps.operations.period_lock import verifica_periodi_aperti
from apps.phases.models import FaseCommessa
from apps.projects.models import Assegnazione, Commessa
from apps.timesheets.models import RigaOre
from apps.timesheets.services import inserisci_ore

from .models import GiornoPianificato
from .permissions import (
    can_confirm_planning,
    can_create_planning,
    can_delete_planning,
    can_edit_planning,
)

from apps.notifications.services import (
    notify_pianificazione_aggiornata,
    notify_pianificazione_creata,
)

User = get_user_model()


def _lock_assignment_scope(assegnazione: Assegnazione) -> Assegnazione:
    """Lock stabile del perimetro operativo: Commessa -> Fase -> Assegnazione.

    Il lock del PeriodoMensile, quando necessario, viene acquisito dal
    chiamante *prima* di questo helper, come nella chiusura mensile.
    """
    Commessa.objects.select_for_update().get(pk=assegnazione.commessa_id)
    FaseCommessa.objects.select_for_update().get(pk=assegnazione.fase_id)
    return (
        Assegnazione.objects.select_for_update()
        .select_related("consulente", "commessa", "fase")
        .get(pk=assegnazione.pk)
    )


def _validate_planning_date(assegnazione: Assegnazione, data) -> None:
    """Verifica che la data sia compatibile con assegnazione e commessa."""
    if data < assegnazione.commessa.data_inizio:
        raise ValidationError("La data selezionata precede l'inizio della commessa.")
    if assegnazione.commessa.data_fine_prevista and data > assegnazione.commessa.data_fine_prevista:
        raise ValidationError("La data selezionata supera la fine prevista della commessa.")
    if data < assegnazione.data_inizio:
        raise ValidationError("La data selezionata precede l'inizio dell'assegnazione.")
    if assegnazione.data_fine and data > assegnazione.data_fine:
        raise ValidationError("La data selezionata supera la fine dell'assegnazione.")
    if assegnazione.fase and data < assegnazione.fase.data_inizio:
        raise ValidationError("La data selezionata precede l'inizio della fase.")
    if assegnazione.fase and assegnazione.fase.data_fine_prevista and data > assegnazione.fase.data_fine_prevista:
        raise ValidationError("La data selezionata supera la data di fine prevista della fase.")


def _validate_integer_hours(ore_pianificate: int) -> None:
    """Pianificazione solo in ore intere da 1 a 8."""
    if isinstance(ore_pianificate, bool):
        raise ValidationError("Le ore pianificate devono essere un numero intero.")
    try:
        ore = int(ore_pianificate)
    except (TypeError, ValueError):
        raise ValidationError("Le ore pianificate devono essere un numero intero.")
    if ore != ore_pianificate:
        raise ValidationError("Sono ammesse solo ore intere.")
    if ore < 1 or ore > 8:
        raise ValidationError("Le ore pianificate devono essere comprese tra 1 e 8.")


def _validate_daily_limit(*, consulente, data, ore_pianificate: int, exclude_id=None) -> None:
    queryset = GiornoPianificato.objects.filter(assegnazione__consulente=consulente, data=data)
    if exclude_id:
        queryset = queryset.exclude(pk=exclude_id)
    totale_esistente = queryset.aggregate(totale=Sum("ore_pianificate"))["totale"] or 0
    nuovo_totale = totale_esistente + ore_pianificate
    if nuovo_totale > 8:
        raise ValidationError(
            f"Il totale pianificato per il {data:%d/%m/%Y} sarebbe di {nuovo_totale} ore. "
            "Il limite giornaliero è di 8 ore."
        )


def _validate_assignment_budget(*, assegnazione: Assegnazione, ore_pianificate: int, exclude_id=None) -> None:
    queryset = GiornoPianificato.objects.filter(assegnazione=assegnazione)
    if exclude_id:
        queryset = queryset.exclude(pk=exclude_id)
    totale_esistente = queryset.aggregate(totale=Sum("ore_pianificate"))["totale"] or 0
    nuovo_totale = totale_esistente + ore_pianificate
    if nuovo_totale > assegnazione.ore_previste:
        residuo = max(assegnazione.ore_previste - totale_esistente, 0)
        raise ValidationError(
            "Le ore pianificate supererebbero il monte ore previsto per questa assegnazione. "
            f"Residuo pianificabile: {residuo} ore."
        )


@transaction.atomic
def create_planning(*, user, assegnazione: Assegnazione, data, ore_pianificate: int, tipo_attivita: str = "CONSULENZA") -> GiornoPianificato:
    # Stesso ordine della chiusura mese: Periodo -> Commessa -> Fase -> Assegnazione.
    # Impedisce di introdurre una sessione in un mese già chiuso e riduce i
    # deadlock tra chiusura periodo e mutazioni dell'agenda.
    verifica_periodi_aperti(data)
    assegnazione = _lock_assignment_scope(assegnazione)
    if not can_create_planning(user, assegnazione):
        raise PermissionDenied("Non puoi pianificare ore per questa assegnazione.")
    if data < timezone.localdate():
        raise ValidationError("Non puoi creare pianificazioni su date già trascorse.")
    _validate_integer_hours(ore_pianificate)
    _validate_planning_date(assegnazione, data)
    User.objects.select_for_update().get(pk=assegnazione.consulente_id)
    if GiornoPianificato.objects.filter(assegnazione=assegnazione, data=data).exists():
        raise ValidationError(
            "Esiste già una pianificazione per questa commessa nella data selezionata. Modifica quella esistente."
        )
    _validate_daily_limit(consulente=assegnazione.consulente, data=data, ore_pianificate=ore_pianificate)
    _validate_assignment_budget(assegnazione=assegnazione, ore_pianificate=ore_pianificate)
    pianificazione = GiornoPianificato.objects.create(
        assegnazione=assegnazione,
        data=data,
        ore_pianificate=ore_pianificate,
        tipo_attivita=tipo_attivita,
        inserita_da=user,
        ultima_modifica_da=user,
    )
    notify_pianificazione_creata(pianificazione=pianificazione, actor=user)
    return pianificazione


@transaction.atomic
def update_planning(*, user, pianificazione: GiornoPianificato, data, ore_pianificate: int, tipo_attivita: str = "CONSULENZA") -> GiornoPianificato:
    # Blocchiamo entrambi i mesi in ordine stabile prima delle righe operative.
    verifica_periodi_aperti(pianificazione.data, data)
    assegnazione = _lock_assignment_scope(pianificazione.assegnazione)
    pianificazione = (
        GiornoPianificato.objects.select_for_update()
        .select_related("assegnazione", "assegnazione__consulente", "assegnazione__commessa", "assegnazione__fase")
        .get(pk=pianificazione.pk)
    )
    pianificazione.assegnazione = assegnazione
    if not can_edit_planning(user, pianificazione):
        raise PermissionDenied("Non puoi modificare questa pianificazione.")
    if data < timezone.localdate():
        raise ValidationError("Le pianificazioni relative a date trascorse sono congelate.")
    _validate_integer_hours(ore_pianificate)
    _validate_planning_date(assegnazione, data)
    User.objects.select_for_update().get(pk=assegnazione.consulente_id)
    if GiornoPianificato.objects.filter(assegnazione=assegnazione, data=data).exclude(pk=pianificazione.pk).exists():
        raise ValidationError("Esiste già una pianificazione per questa commessa nella data selezionata.")
    _validate_daily_limit(
        consulente=assegnazione.consulente,
        data=data,
        ore_pianificate=ore_pianificate,
        exclude_id=pianificazione.pk,
    )
    _validate_assignment_budget(
        assegnazione=assegnazione,
        ore_pianificate=ore_pianificate,
        exclude_id=pianificazione.pk,
    )
    pianificazione.data = data
    pianificazione.ore_pianificate = ore_pianificate
    pianificazione.tipo_attivita = tipo_attivita
    pianificazione.ultima_modifica_da = user
    if user.id != assegnazione.consulente_id and user.puo_gestire_commessa(assegnazione.commessa):
        pianificazione.modificata_da_admin = True
    pianificazione.save(
        update_fields=[
            "data", "ore_pianificate", "tipo_attivita", "ultima_modifica_da",
            "modificata_da_admin", "updated_at",
        ]
    )
    notify_pianificazione_aggiornata(pianificazione=pianificazione, actor=user)
    return pianificazione


@transaction.atomic
def delete_planning(*, user, pianificazione: GiornoPianificato) -> None:
    verifica_periodi_aperti(pianificazione.data)
    assegnazione = _lock_assignment_scope(pianificazione.assegnazione)
    pianificazione = (
        GiornoPianificato.objects.select_for_update()
        .select_related("assegnazione", "assegnazione__consulente", "assegnazione__commessa", "assegnazione__fase")
        .get(pk=pianificazione.pk)
    )
    pianificazione.assegnazione = assegnazione
    if not can_delete_planning(user, pianificazione):
        raise PermissionDenied("Non puoi eliminare questa pianificazione.")
    notify_pianificazione_aggiornata(pianificazione=pianificazione, actor=user, eliminata=True)
    pianificazione.delete()


@transaction.atomic
def confirm_planning(*, user, pianificazione: GiornoPianificato) -> GiornoPianificato:
    """Conferma la conclusione della sessione e alimenta il timesheet.

    La conferma è intenzionalmente personale: nessun Admin/PM può dichiarare
    conclusa una sessione al posto della risorsa pianificata.
    """
    # Retry idempotente: una conferma già consolidata dalla stessa risorsa non
    # è una nuova mutazione e resta leggibile anche se il mese è stato chiuso
    # successivamente. Verifichiamo sul DB per non dipendere da un oggetto stale.
    gia_confermata = (
        GiornoPianificato.objects.filter(
            pk=pianificazione.pk,
            stato_sessione=GiornoPianificato.StatoSessione.CONFERMATA,
            confermata_da_id=user.id,
            riga_ore_generata__isnull=False,
        )
        .select_related(
            "assegnazione",
            "assegnazione__consulente",
            "assegnazione__commessa",
            "assegnazione__fase",
        )
        .first()
    )
    if gia_confermata is not None:
        return gia_confermata

    # Periodo prima della sessione: è lo stesso ordine usato da chiudi_periodo.
    verifica_periodi_aperti(pianificazione.data)
    assegnazione = _lock_assignment_scope(pianificazione.assegnazione)
    pianificazione = (
        GiornoPianificato.objects.select_for_update()
        .select_related("assegnazione", "assegnazione__consulente", "assegnazione__commessa", "assegnazione__fase")
        .get(pk=pianificazione.pk)
    )
    pianificazione.assegnazione = assegnazione
    # Idempotenza/concorrenza: dopo il lock, una seconda conferma della stessa
    # risorsa restituisce lo stato già consolidato senza creare una seconda riga.
    if (
        pianificazione.stato_sessione == GiornoPianificato.StatoSessione.CONFERMATA
        and pianificazione.confermata_da_id == user.id
        and pianificazione.riga_ore_generata_id
    ):
        return pianificazione

    if not can_confirm_planning(user, pianificazione):
        if pianificazione.confermata:
            raise ValidationError(
                "La sessione risulta già risolta e non richiede una nuova conferma."
            )
        raise PermissionDenied("Solo la risorsa pianificata può confermare la conclusione della sessione.")

    righe_esistenti = list(
        RigaOre.objects.select_for_update().filter(
            assegnazione_id=pianificazione.assegnazione_id,
            data=pianificazione.data,
        ).order_by("created_at")
    )

    if righe_esistenti:
        if len(righe_esistenti) != 1:
            raise ValidationError(
                "Per questa sessione esistono già più righe timesheet. "
                "Allineale prima di confermare l'agenda."
            )
        riga = righe_esistenti[0]
        if riga.ore != pianificazione.ore_pianificate or riga.tipo_attivita != pianificazione.tipo_attivita:
            raise ValidationError(
                "Esiste già una riga timesheet per questa data con ore o tipologia diverse. "
                "Allineala alla sessione di agenda prima della conferma."
            )
    else:
        esito = inserisci_ore(
            attore=user,
            assegnazione_id=pianificazione.assegnazione_id,
            giorno=pianificazione.data,
            tipo_attivita=pianificazione.tipo_attivita,
            ore=pianificazione.ore_pianificate,
            nota="Generata automaticamente dalla conferma della sessione in agenda.",
        )
        riga = esito.riga

    pianificazione.stato_sessione = GiornoPianificato.StatoSessione.CONFERMATA
    pianificazione.confermata_il = timezone.now()
    pianificazione.confermata_da = user
    pianificazione.riga_ore_generata = riga
    pianificazione.ultima_modifica_da = user
    pianificazione.save(
        update_fields=[
            "stato_sessione", "confermata_il", "confermata_da",
            "riga_ore_generata", "ultima_modifica_da", "updated_at",
        ]
    )

    AuditLog.objects.create(
        utente=user,
        entita="SessioneAgenda",
        entita_id=pianificazione.id,
        azione="CONFERMA_SESSIONE",
        valore_precedente={"stato_sessione": GiornoPianificato.StatoSessione.PIANIFICATA},
        valore_nuovo={
            "stato_sessione": GiornoPianificato.StatoSessione.CONFERMATA,
            "riga_ore_id": str(riga.id),
            "ore": pianificazione.ore_pianificate,
            "data": pianificazione.data.isoformat(),
        },
        motivazione="Conferma conclusione sessione agenda e alimentazione timesheet.",
    )
    return pianificazione
