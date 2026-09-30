from django.core.exceptions import (
    PermissionDenied,
    ValidationError,
)
from django.db import transaction
from django.utils import timezone

from apps.projects.models import Assegnazione, Commessa
from apps.projects.permissions import is_active_phase_member, is_active_pm
from apps.projects.workflow import fase_permette_nuovo_lavoro

from .models import Task, TaskComment
from .permissions import (
    can_comment_task,
    can_create_task,
    can_delete_task,
    can_edit_task,
    can_update_task_status,
)

from apps.notifications.services import (
    notify_task_assigned,
    notify_task_commented,
    notify_task_created,
    notify_task_updated,
    notify_task_deleted,
    notify_task_reassigned,
    notify_task_status_changed,
)

def _validate_title(titolo: str) -> str:
    titolo = (titolo or "").strip()

    if not titolo:
        raise ValidationError(
            "Il titolo dell'attività è obbligatorio."
        )

    if len(titolo) > 255:
        raise ValidationError(
            "Il titolo non può superare 255 caratteri."
        )

    return titolo


def _validate_description(
    descrizione: str | None,
) -> str:
    return (descrizione or "").strip()


def _validate_priority(priorita: str) -> str:
    valori_validi = {
        valore
        for valore, _ in Task.Priorita.choices
    }

    if priorita not in valori_validi:
        raise ValidationError(
            "Priorità non valida."
        )

    return priorita


def _validate_status(stato: str) -> str:
    valori_validi = {
        valore
        for valore, _ in Task.Stato.choices
    }

    if stato not in valori_validi:
        raise ValidationError(
            "Stato attività non valido."
        )

    return stato


def _validate_dates(
    *,
    data_inizio=None,
    data_scadenza=None,
    commessa=None,
    fase=None,
) -> None:
    if (
        data_inizio
        and data_scadenza
        and data_scadenza < data_inizio
    ):
        raise ValidationError(
            "La data di scadenza non può precedere "
            "la data di inizio."
        )

    for valore, etichetta in (
        (data_inizio, "inizio"),
        (data_scadenza, "scadenza"),
    ):
        if not valore:
            continue
        if commessa and valore < commessa.data_inizio:
            raise ValidationError(
                f"La data di {etichetta} non può precedere l'inizio della commessa."
            )
        if commessa and commessa.data_fine_prevista and valore > commessa.data_fine_prevista:
            raise ValidationError(
                f"La data di {etichetta} non può superare la fine prevista della commessa."
            )
        if fase and valore < fase.data_inizio:
            raise ValidationError(
                f"La data di {etichetta} non può precedere l'inizio della fase."
            )
        if fase and fase.data_fine_prevista and valore > fase.data_fine_prevista:
            raise ValidationError(
                f"La data di {etichetta} non può superare la fine prevista della fase."
            )


def _validate_open_project(
    commessa,
) -> None:
    if commessa.stato != Commessa.Stato.APERTA:
        raise ValidationError(
            "Non è possibile operare su una commessa chiusa."
        )


def _validate_assignee(
    *,
    commessa,
    fase=None,
    assegnato_a,
) -> None:
    """
    Un task può essere assegnato:

    - a un Admin LEF attivo;
    - a un utente con assegnazione attiva sulla commessa.
    """

    if not assegnato_a:
        raise ValidationError(
            "È necessario selezionare un assegnatario."
        )

    if not assegnato_a.is_active:
        raise ValidationError(
            "L'utente selezionato non è attivo."
        )

    # Chi gestisce la commessa (Admin, Amministrazione, Resp. BU) può
    # ricevere task indipendentemente dall'assegnazione sulla commessa.
    if assegnato_a.puo_gestire_commessa(commessa):
        return

    assegnazione_esistente = (
        Assegnazione.objects
        .filter(
            consulente=assegnato_a,
            fase=fase,
            commessa=commessa,
            stato=Assegnazione.Stato.ATTIVA,
        )
        .exists()
    )

    if not assegnazione_esistente:
        raise ValidationError(
            "L'utente selezionato non possiede "
            "un'assegnazione attiva sulla fase."
        )

def _resolve_phase(commessa, fase=None):
    if fase is None:
        raise ValidationError(
            "La fase è obbligatoria per ogni attività."
        )

    if fase.commessa_id != commessa.id:
        raise ValidationError(
            "La fase non appartiene alla commessa selezionata."
        )

    return fase


@transaction.atomic
def create_task(
    *,
    user,
    commessa,
    fase=None,
    assegnato_a,
    titolo,
    descrizione="",
    priorita=Task.Priorita.NORMALE,
    data_inizio=None,
    data_scadenza=None,
):
    commessa = (
        Commessa.objects
        .select_for_update()
        .get(
            pk=commessa.pk
        )
    )

    fase = _resolve_phase(commessa, fase)
    from apps.phases.models import FaseCommessa
    fase = FaseCommessa.objects.select_for_update().get(pk=fase.pk)

    if not can_create_task(
        user,
        commessa,
        fase,
    ):
        raise PermissionDenied(
            "Non puoi creare attività su questa commessa."
        )

    _validate_open_project(
        commessa
    )

    titolo = _validate_title(
        titolo
    )

    descrizione = (
        _validate_description(
            descrizione
        )
    )

    priorita = (
        _validate_priority(
            priorita
        )
    )

    _validate_dates(
        data_inizio=data_inizio,
        data_scadenza=data_scadenza,
        commessa=commessa,
        fase=fase,
    )

    if fase.commessa_id != commessa.id:
        raise ValidationError("La fase non appartiene alla commessa.")
    # is_active_pm include la supervisione di chi gestisce la commessa.
    if (
        not is_active_pm(user, commessa)
        and not is_active_phase_member(user, fase)
    ):
        raise PermissionDenied("Non puoi creare attività su questa fase.")

    _validate_assignee(
        commessa=commessa,
        fase=fase,
        assegnato_a=assegnato_a,
    )

    task = Task.objects.create(
        commessa=commessa,
        fase=fase,
        titolo=titolo,
        descrizione=descrizione,
        assegnato_a=assegnato_a,
        creato_da=user,
        stato=Task.Stato.DA_FARE,
        priorita=priorita,
        data_inizio=data_inizio,
        data_scadenza=data_scadenza,
    )

    # =====================================================
    # NOTIFICA ASSEGNAZIONE
    # =====================================================

    notify_task_assigned(
        task=task,
        actor=user,
    )

    # =====================================================
    # NOTIFICA CREAZIONE (a tutto il Teamwork)
    # =====================================================

    notify_task_created(
        task=task,
        actor=user,
    )

    return task

@transaction.atomic
def update_task(
    *,
    user,
    task,
    titolo,
    descrizione="",
    fase,
    assegnato_a,
    priorita=Task.Priorita.NORMALE,
    data_inizio=None,
    data_scadenza=None,
):
    # Stesso ordine di lock usato dall'aggiornamento fase:
    # Commessa -> Fasi coinvolte -> Task. Così una modifica del task non può
    # introdurre date fuori intervallo mentre la fase viene ristretta.
    commessa = Commessa.objects.select_for_update().get(pk=task.commessa_id)
    fase_richiesta = _resolve_phase(commessa, fase or task.fase)

    from apps.phases.models import FaseCommessa
    fase_ids = {task.fase_id, fase_richiesta.pk}
    list(
        FaseCommessa.objects.select_for_update()
        .filter(pk__in=fase_ids)
        .order_by("pk")
        .values_list("pk", flat=True)
    )

    task = (
        Task.objects
        .select_for_update()
        .select_related(
            "commessa",
            "fase",
            "assegnato_a",
            "creato_da",
        )
        .get(
            pk=task.pk
        )
    )

    fase = FaseCommessa.objects.get(pk=fase_richiesta.pk)

    if not can_edit_task(
        user,
        task,
    ):
        raise PermissionDenied(
            "Non puoi modificare questa attività."
        )

    # Conserviamo il vecchio assegnatario
    # prima della modifica.
    vecchio_assegnato_a_id = (
        task.assegnato_a_id
    )

    valori_precedenti = {
        "titolo": task.titolo,
        "descrizione": task.descrizione,
        "priorita": task.priorita,
        "data_inizio": task.data_inizio,
        "data_scadenza": task.data_scadenza,
    }

    titolo = _validate_title(
        titolo
    )

    descrizione = (
        _validate_description(
            descrizione
        )
    )

    priorita = (
        _validate_priority(
            priorita
        )
    )

    _validate_dates(
        data_inizio=data_inizio,
        data_scadenza=data_scadenza,
        commessa=task.commessa,
        fase=fase,
    )

    if fase.commessa_id != task.commessa_id:
        raise ValidationError("La fase non appartiene alla commessa del task.")
    if not fase_permette_nuovo_lavoro(fase):
        raise ValidationError(
            "Non puoi spostare o modificare un'attività su una fase completata o sospesa."
        )
    if (
        not is_active_pm(user, commessa)
        and not is_active_phase_member(user, fase)
    ):
        raise PermissionDenied("Non puoi spostare l'attività su questa fase.")

    _validate_assignee(
        commessa=task.commessa,
        fase=fase,
        assegnato_a=assegnato_a,
    )

    task.fase = fase
    task.titolo = titolo
    task.descrizione = descrizione
    task.assegnato_a = assegnato_a
    task.priorita = priorita
    task.data_inizio = data_inizio
    task.data_scadenza = data_scadenza

    task.save(
        update_fields=[
            "fase",
            "titolo",
            "descrizione",
            "assegnato_a",
            "priorita",
            "data_inizio",
            "data_scadenza",
            "updated_at",
        ]
    )

    # =====================================================
    # NUOVO ASSEGNATARIO
    # =====================================================

    modificato = any(
        getattr(task, campo) != valore
        for campo, valore in valori_precedenti.items()
    )

    if modificato:
        notify_task_updated(
            task=task,
            actor=user,
        )

    if (
        vecchio_assegnato_a_id
        != task.assegnato_a_id
    ):
        notify_task_assigned(
            task=task,
            actor=user,
        )

        notify_task_reassigned(
            task=task,
            actor=user,
            precedente_assegnatario=vecchio_assegnato_a_id,
        )

    return task

@transaction.atomic
def update_task_status(
    *,
    user,
    task,
    stato,
) -> Task:
    """
    Aggiorna esclusivamente lo stato.

    Quando il task viene completato valorizza completato_il.
    Se viene riaperto, completato_il viene azzerato.
    """

    task = (
        Task.objects
        .select_for_update()
        .select_related(
            "commessa",
            "assegnato_a",
        )
        .get(pk=task.pk)
    )

    if not can_update_task_status(
        user,
        task,
    ):
        raise PermissionDenied(
            "Non puoi modificare lo stato di questa attività."
        )

    stato = _validate_status(
        stato
    )

    if task.stato == stato:
        return task

    stato_precedente = task.get_stato_display()

    task.stato = stato

    if stato == Task.Stato.COMPLETATA:
        task.completato_il = timezone.now()
    else:
        task.completato_il = None

    task.save(
        update_fields=[
            "stato",
            "completato_il",
            "updated_at",
        ]
    )

    # =====================================================
    # NOTIFICA CAMBIO STATO
    # =====================================================

    notify_task_status_changed(
        task=task,
        actor=user,
        stato_precedente=stato_precedente,
    )

    return task


@transaction.atomic
def add_task_comment(
    *,
    user,
    task,
    testo,
):
    task = (
        Task.objects
        .select_for_update()
        .select_related(
            "commessa",
            "assegnato_a",
            "creato_da",
        )
        .get(
            pk=task.pk
        )
    )

    if not can_comment_task(
        user,
        task,
    ):
        raise PermissionDenied(
            "Non puoi commentare questa attività."
        )

    testo = (
        testo
        or ""
    ).strip()

    if not testo:
        raise ValidationError(
            "Il commento non può essere vuoto."
        )

    commento = TaskComment.objects.create(
        task=task,
        autore=user,
        testo=testo,
    )

    # =====================================================
    # NOTIFICHE COMMENTO
    # =====================================================

    notify_task_commented(
        comment=commento,
    )

    return commento


@transaction.atomic
def delete_task(
    *,
    user,
    task,
) -> None:
    """
    Elimina il task e i relativi commenti.

    Consentito solamente ad Admin e PM autorizzati.
    """

    task = (
        Task.objects
        .select_for_update()
        .select_related(
            "commessa",
        )
        .get(pk=task.pk)
    )

    if not can_delete_task(
        user,
        task,
    ):
        raise PermissionDenied(
            "Non puoi eliminare questa attività."
        )

    # =====================================================
    # NOTIFICA ELIMINAZIONE
    # (va generata prima di task.delete(): dopo, i dati
    # del task non sarebbero più disponibili)
    # =====================================================

    notify_task_deleted(
        titolo_task=task.titolo,
        commessa=task.commessa,
        fase=task.fase,
        actor=user,
    )

    task.delete()