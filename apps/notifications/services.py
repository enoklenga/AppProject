from __future__ import annotations


from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from apps.projects.models import Assegnazione
from apps.tasks.models import Task, TaskComment

from .models import Notification


from .models import NotificationPreference

User = get_user_model()


def _is_authenticated(user) -> bool:
    return bool(
        user
        and getattr(
            user,
            "is_authenticated",
            False,
        )
    )


def _clean_text(
    value,
    *,
    max_length=None,
) -> str:
    value = (value or "").strip()

    if (
        max_length is not None
        and len(value) > max_length
    ):
        value = value[:max_length]

    return value


def _task_context(task):
    return (
        f"{task.commessa.cliente.ragione_sociale} "
        f"(commessa {task.commessa.codice})"
    )


def _task_recipient_has_current_access(*, task, destinatario) -> bool:
    """
    Verifica che il destinatario possa ancora accedere alla fase del task.

    Gli Admin LEF mantengono accesso globale anche senza una propria
    assegnazione. Per gli altri utenti serve un'assegnazione ATTIVA sulla
    stessa fase del task. Questo controllo viene eseguito anche al momento
    della notifica per evitare leak dopo la conclusione/rimozione di una
    assegnazione.
    """

    if destinatario is None or not destinatario.is_active:
        return False

    # Chi gestisce la commessa (Admin, Amministrazione, Resp. BU) mantiene
    # l'accesso anche senza una propria assegnazione.
    if destinatario.puo_gestire_commessa(task.commessa):
        return True

    if not task.fase_id:
        return False

    return Assegnazione.objects.filter(
        consulente=destinatario,
        fase_id=task.fase_id,
        stato=Assegnazione.Stato.ATTIVA,
    ).exists()


def _create_notification(
    *,
    destinatario,
    tipo,
    titolo,
    messaggio="",
    attore=None,
    task=None,
    pianificazione=None,
    fase=None,
    documento=None,
    data_riferimento=None,
    chiave_evento=None,
):
    """
    Punto unico di creazione notifiche.

    Se chiave_evento è valorizzata utilizza get_or_create
    per impedire duplicati.

    Gli utenti disattivati non ricevono nuove notifiche.
    """

    if destinatario is None:
        return None

    if not destinatario.is_active:
        return None

    titolo = _clean_text(
        titolo,
        max_length=255,
    )

    messaggio = _clean_text(
        messaggio
    )

    if not titolo:
        raise ValidationError(
            "Il titolo della notifica è obbligatorio."
        )

    if tipo not in Notification.Tipo.values:
        raise ValidationError(
            "Tipo di notifica non valido."
        )

    if hasattr(
        destinatario,
        "notification_preferences",
    ):

        preferences = (
            destinatario
            .notification_preferences
        )

        preference_map = {
            Notification.Tipo.TASK_ASSIGNED: preferences.task_assigned,
            Notification.Tipo.TASK_COMMENTED: preferences.task_commented,
            Notification.Tipo.TASK_DUE_SOON: preferences.task_due_soon,
            Notification.Tipo.TASK_OVERDUE: preferences.task_overdue,
            Notification.Tipo.TASK_CREATED: preferences.task_creato,
            Notification.Tipo.TASK_UPDATED: preferences.task_modificato,
            Notification.Tipo.TASK_REASSIGNED: preferences.task_riassegnato,
            Notification.Tipo.TASK_STATUS_CHANGED: preferences.task_cambio_stato,
            Notification.Tipo.TASK_DELETED: preferences.task_eliminato,
            Notification.Tipo.PIANIFICAZIONE_CREATA: preferences.pianificazione_creata,
            Notification.Tipo.PIANIFICAZIONE_AGGIORNATA: preferences.pianificazione_aggiornata,
            Notification.Tipo.FASE_CREATA: preferences.fase_creata,
            Notification.Tipo.FASE_AGGIORNATA: preferences.fase_aggiornata,
            Notification.Tipo.DOCUMENTO_CARICATO: preferences.documento_caricato,
            Notification.Tipo.DOCUMENTO_ELIMINATO: preferences.documento_eliminato,
        }

        enabled = preference_map.get(
            tipo,
            True,
        )

        if not enabled:
            return None

    defaults = {
        "attore": attore,
        "task": task,
        "pianificazione": pianificazione,
        "fase": fase,
        "documento": documento,
        "tipo": tipo,
        "titolo": titolo,
        "messaggio": messaggio,
        "data_riferimento": data_riferimento,
    }

    if chiave_evento:

        notification, _created = (
            Notification.objects.get_or_create(
                chiave_evento=chiave_evento,
                defaults={
                    "destinatario": destinatario,
                    **defaults,
                },
            )
        )

        return notification

    return Notification.objects.create(
        destinatario=destinatario,
        **defaults,
    )


# =========================================================
# TASK ASSEGNATO
# =========================================================


@transaction.atomic
def notify_task_assigned(
    *,
    task: Task,
    actor,
):
    """
    Notifica il nuovo assegnatario.

    Non genera una notifica quando l'utente assegna
    il task a se stesso.
    """

    destinatario = task.assegnato_a

    if destinatario is None:
        return None

    if (
        actor is not None
        and destinatario.pk == actor.pk
    ):
        return None

    scadenza = ""

    if task.data_scadenza:
        scadenza = (
            " Scadenza: "
            f"{task.data_scadenza.strftime('%d/%m/%Y')}."
        )

    return _create_notification(
        destinatario=destinatario,
        attore=actor,
        task=task,
        tipo=Notification.Tipo.TASK_ASSIGNED,
        titolo="Nuova attività assegnata",
        messaggio=(
            f"Ti è stata assegnata l'attività "
            f"“{task.titolo}” "
            f"per il cliente "
            f"{task.commessa.cliente.ragione_sociale} "
            f"(commessa {task.commessa.codice})."
            f"{scadenza}"
        ),
    )


# =========================================================
# COMMENTO TASK
# =========================================================


def _comment_recipients(*, task, actor):
    """Tutti i membri attivi della fase, escluso l'autore."""
    return _phase_recipients(fase=task.fase, actor=actor)


@transaction.atomic
def notify_task_commented(
    *,
    comment: TaskComment,
):
    """
    Genera le notifiche relative a un nuovo commento.

    La chiave evento contiene commento + destinatario,
    quindi anche se il service venisse richiamato due volte
    non genera notifiche duplicate.
    """

    task = comment.task
    actor = comment.autore

    recipients = _comment_recipients(
        task=task,
        actor=actor,
    )

    nome_autore = (
        actor.get_full_name().strip()
        or actor.email
    )

    notifications = []

    for destinatario in recipients:

        chiave_evento = (
            f"TASK_COMMENTED:"
            f"{comment.pk}:"
            f"{destinatario.pk}"
        )

        notification = _create_notification(
            destinatario=destinatario,
            attore=actor,
            task=task,
            tipo=(
                Notification
                .Tipo
                .TASK_COMMENTED
            ),
            titolo="Nuovo commento sull'attività",
            messaggio=(
                f"{nome_autore} ha aggiunto un commento "
                f"all'attività “{task.titolo}” "
                f"per il cliente "
                f"{task.commessa.cliente.ragione_sociale} "
                f"(commessa {task.commessa.codice})."
            ),
            chiave_evento=chiave_evento,
        )

        if notification is not None:
            notifications.append(
                notification
            )

    return notifications


# =========================================================
# TASK IN SCADENZA
# =========================================================


@transaction.atomic
def notify_task_due_soon(
    *,
    task: Task,
):
    """
    Genera una notifica di prossima scadenza.

    Una sola notifica per:
    task + destinatario + data scadenza.
    """

    if task.stato == Task.Stato.COMPLETATA:
        return None

    if not task.data_scadenza:
        return None

    destinatario = task.assegnato_a

    if destinatario is None:
        return None

    if not _task_recipient_has_current_access(
        task=task,
        destinatario=destinatario,
    ):
        return None

    chiave_evento = (
        f"TASK_DUE_SOON:"
        f"{task.pk}:"
        f"{destinatario.pk}:"
        f"{task.data_scadenza.isoformat()}"
    )

    return _create_notification(
        destinatario=destinatario,
        task=task,
        tipo=Notification.Tipo.TASK_DUE_SOON,
        titolo="Attività in scadenza",
        messaggio=(
            f"L'attività “{task.titolo}” "
            f"per il cliente "
            f"{task.commessa.cliente.ragione_sociale} "
            f"(commessa {task.commessa.codice}) "
            f"scade il "
            f"{task.data_scadenza.strftime('%d/%m/%Y')}."
        ),
        data_riferimento=task.data_scadenza,
        chiave_evento=chiave_evento,
    )


# =========================================================
# TASK SCADUTO
# =========================================================


@transaction.atomic
def notify_task_overdue(
    *,
    task: Task,
):
    """
    Genera una notifica di attività scaduta.

    Una sola notifica per:
    task + destinatario + data scadenza.
    """

    if task.stato == Task.Stato.COMPLETATA:
        return None

    if not task.data_scadenza:
        return None

    destinatario = task.assegnato_a

    if destinatario is None:
        return None

    if not _task_recipient_has_current_access(
        task=task,
        destinatario=destinatario,
    ):
        return None

    chiave_evento = (
        f"TASK_OVERDUE:"
        f"{task.pk}:"
        f"{destinatario.pk}:"
        f"{task.data_scadenza.isoformat()}"
    )

    return _create_notification(
        destinatario=destinatario,
        task=task,
        tipo=Notification.Tipo.TASK_OVERDUE,
        titolo="Attività scaduta",
        messaggio=(
            f"L'attività “{task.titolo}” "
            f"per il cliente "
            f"{task.commessa.cliente.ragione_sociale} "
            f"(commessa {task.commessa.codice}) "
            f"è scaduta il "
            f"{task.data_scadenza.strftime('%d/%m/%Y')}."
        ),
        data_riferimento=task.data_scadenza,
        chiave_evento=chiave_evento,
    )


# =========================================================
# LETTURA NOTIFICHE
# =========================================================


@transaction.atomic
def mark_notification_read(
    *,
    user,
    notification: Notification,
):
    """
    Un utente può segnare come letta solamente
    una propria notifica.
    """

    if not _is_authenticated(
        user
    ):
        raise PermissionDenied

    notification = (
        Notification.objects
        .select_for_update()
        .get(
            pk=notification.pk
        )
    )

    if (
        notification.destinatario_id
        != user.pk
    ):
        raise PermissionDenied(
            "Non puoi modificare questa notifica."
        )

    if notification.letta_il is None:

        notification.letta_il = (
            timezone.now()
        )

        notification.save(
            update_fields=[
                "letta_il",
                "updated_at",
            ]
        )

    return notification


@transaction.atomic
def mark_notification_unread(
    *,
    user,
    notification: Notification,
):
    """
    Permette di riportare una propria notifica
    allo stato non letto.
    """

    if not _is_authenticated(
        user
    ):
        raise PermissionDenied

    notification = (
        Notification.objects
        .select_for_update()
        .get(
            pk=notification.pk
        )
    )

    if (
        notification.destinatario_id
        != user.pk
    ):
        raise PermissionDenied(
            "Non puoi modificare questa notifica."
        )

    if notification.letta_il is not None:

        notification.letta_il = None

        notification.save(
            update_fields=[
                "letta_il",
                "updated_at",
            ]
        )

    return notification


@transaction.atomic
def mark_all_notifications_read(
    *,
    user,
) -> int:
    """
    Segna come lette tutte le notifiche non lette
    dell'utente.

    Restituisce il numero di notifiche aggiornate.
    """

    if not _is_authenticated(
        user
    ):
        raise PermissionDenied

    now = timezone.now()

    return (
        Notification.objects
        .filter(
            destinatario=user,
            letta_il__isnull=True,
        )
        .update(
            letta_il=now,
            updated_at=now,
        )
    )


# =========================================================
# GENERAZIONE AUTOMATICA SCADENZE
# =========================================================


@transaction.atomic
def generate_due_soon_notifications(
    *,
    tasks,
):
    """
    Riceve un queryset/lista di task in scadenza
    e genera le notifiche idempotenti.
    """

    notifications = []

    for task in tasks:

        notification = (
            notify_task_due_soon(
                task=task
            )
        )

        if notification is not None:
            notifications.append(
                notification
            )

    return notifications


@transaction.atomic
def generate_overdue_notifications(
    *,
    tasks,
):
    """
    Riceve un queryset/lista di task scaduti
    e genera le notifiche idempotenti.
    """

    notifications = []

    for task in tasks:

        notification = (
            notify_task_overdue(
                task=task
            )
        )

        if notification is not None:
            notifications.append(
                notification
            )

    return notifications


@transaction.atomic
def notify_documento_caricato(*, documento, actor):
    # I documenti privati sono riservati agli Admin LEF: non generiamo
    # notifiche di Teamwork che ne rivelerebbero nome o esistenza.
    if documento.privato:
        return []

    commessa = documento.commessa
    risultati = []

    for destinatario in (_phase_recipients(fase=documento.fase, actor=actor) if documento.fase_id else _team_recipients(commessa=commessa, actor=actor)):
        risultati.append(
            _create_notification(
                destinatario=destinatario,
                attore=actor,
                documento=documento,
                tipo=Notification.Tipo.DOCUMENTO_CARICATO,
                titolo="Nuovo documento",
                messaggio=(
                    f"{actor} ha caricato il documento “{documento.nome_originale}” "
                    f"sulla commessa {commessa.codice}."
                ),
            )
        )

    return risultati


@transaction.atomic
def notify_documento_eliminato(*, documento, actor):
    # Stessa policy dell'upload: un documento privato non deve lasciare
    # metadati visibili ai membri ordinari del Teamwork.
    if documento.privato:
        return []

    commessa = documento.commessa
    risultati = []

    for destinatario in (_phase_recipients(fase=documento.fase, actor=actor) if documento.fase_id else _team_recipients(commessa=commessa, actor=actor)):
        risultati.append(
            _create_notification(
                destinatario=destinatario,
                attore=actor,
                documento=documento,
                tipo=Notification.Tipo.DOCUMENTO_ELIMINATO,
                titolo="Documento eliminato",
                messaggio=(
                    f"{actor} ha eliminato il documento “{documento.nome_originale}” "
                    f"dalla commessa {commessa.codice}."
                ),
            )
        )

    return risultati


def ensure_notification_preferences():
    """
    Crea le preferenze notifiche mancanti
    per gli utenti già presenti.
    """

    users_without_preferences = (
        User.objects
        .filter(
            notification_preferences__isnull=True
        )
    )

    created = 0

    for user in users_without_preferences:
        NotificationPreference.objects.create(
            user=user
        )
        created += 1

    return created

# =========================================================
# TEAMWORK — DESTINATARI DI SQUADRA
# =========================================================


def _team_recipients(*, commessa, actor=None):
    """
    Tutti i membri con assegnazione attiva sulla commessa (Admin esclusi:
    ricevono comunque le notifiche solo se hanno anche loro
    un'assegnazione, coerente con la definizione di "membro del
    Teamwork" — §4 specifica funzionale).

    L'autore dell'azione viene sempre escluso.
    """

    user_ids = set(
        Assegnazione.objects
        .filter(
            commessa=commessa,
            stato=Assegnazione.Stato.ATTIVA,
            consulente__is_active=True,
        )
        .values_list("consulente_id", flat=True)
    )

    if actor is not None:
        user_ids.discard(actor.pk)

    return (
        User.objects
        .filter(pk__in=user_ids, is_active=True)
        .order_by("last_name", "first_name", "email")
    )


def _phase_recipients(*, fase, actor=None):
    """Membri attivi della sola squadra della fase, escluso l'autore."""
    user_ids = set(
        Assegnazione.objects.filter(
            fase=fase,
            stato=Assegnazione.Stato.ATTIVA,
            consulente__is_active=True,
        ).values_list("consulente_id", flat=True)
    )
    if actor is not None:
        user_ids.discard(actor.pk)
    return User.objects.filter(pk__in=user_ids, is_active=True).order_by("last_name", "first_name", "email")


# =========================================================
# PIANIFICAZIONE (TEAMWORK)
# =========================================================


@transaction.atomic
def notify_pianificazione_creata(*, pianificazione, actor):
    consulente = pianificazione.assegnazione.consulente
    commessa = pianificazione.assegnazione.commessa
    fase = pianificazione.assegnazione.fase

    risultati = []

    for destinatario in _phase_recipients(fase=fase, actor=actor):
        risultati.append(
            _create_notification(
                destinatario=destinatario,
                attore=actor,
                pianificazione=pianificazione,
                tipo=Notification.Tipo.PIANIFICAZIONE_CREATA,
                titolo="Nuova pianificazione",
                messaggio=(
                    f"{consulente} ha pianificato "
                    f"{pianificazione.ore_pianificate}h il "
                    f"{pianificazione.data.strftime('%d/%m/%Y')} "
                    f"sulla commessa {commessa.codice}."
                ),
                data_riferimento=pianificazione.data,
            )
        )

    return risultati


@transaction.atomic
def notify_pianificazione_aggiornata(*, pianificazione, actor, eliminata=False):
    """
    Copre sia la modifica sia l'eliminazione (stesso tipo di notifica,
    Teamwork le raggruppa sotto un'unica categoria di preferenza).

    Se eliminata=True, la pianificazione sta per essere cancellata:
    non colleghiamo la FK (CASCADE la cancellerebbe insieme
    all'oggetto), i dettagli restano nel testo del messaggio.
    """

    consulente = pianificazione.assegnazione.consulente
    commessa = pianificazione.assegnazione.commessa
    verbo = "eliminato" if eliminata else "aggiornato"

    risultati = []

    for destinatario in _phase_recipients(fase=pianificazione.assegnazione.fase, actor=actor):
        risultati.append(
            _create_notification(
                destinatario=destinatario,
                attore=actor,
                pianificazione=None if eliminata else pianificazione,
                tipo=Notification.Tipo.PIANIFICAZIONE_AGGIORNATA,
                titolo=f"Pianificazione {verbo}",
                messaggio=(
                    f"La pianificazione di {consulente} del "
                    f"{pianificazione.data.strftime('%d/%m/%Y')} "
                    f"sulla commessa {commessa.codice} è stata {verbo}."
                ),
                data_riferimento=pianificazione.data,
            )
        )

    return risultati


# =========================================================
# ATTIVITÀ (TEAMWORK) — eventi collaborativi aggiuntivi
# =========================================================


@transaction.atomic
def notify_task_updated(*, task, actor):
    risultati = []

    for destinatario in _phase_recipients(fase=task.fase, actor=actor):
        risultati.append(
            _create_notification(
                destinatario=destinatario,
                attore=actor,
                task=task,
                tipo=Notification.Tipo.TASK_UPDATED,
                titolo="Attività modificata",
                messaggio=(
                    f"L'attività “{task.titolo}” della commessa "
                    f"{task.commessa.codice} è stata modificata."
                ),
            )
        )

    return risultati


@transaction.atomic
def notify_task_created(*, task, actor):
    risultati = []

    for destinatario in _phase_recipients(fase=task.fase, actor=actor):
        risultati.append(
            _create_notification(
                destinatario=destinatario,
                attore=actor,
                task=task,
                tipo=Notification.Tipo.TASK_CREATED,
                titolo="Nuova attività",
                messaggio=(
                    f"È stata creata l'attività “{task.titolo}” "
                    f"sulla commessa {task.commessa.codice}."
                ),
            )
        )

    return risultati


@transaction.atomic
def notify_task_reassigned(*, task, actor, precedente_assegnatario=None):
    destinatari = list(_phase_recipients(fase=task.fase, actor=actor))

    # Il nuovo assegnatario riceve già TASK_ASSIGNED separatamente
    # (notify_task_assigned): qui evitiamo di duplicargli la notifica.
    destinatari = [
        u for u in destinatari
        if u.pk != task.assegnato_a_id
    ]

    risultati = []

    for destinatario in destinatari:
        risultati.append(
            _create_notification(
                destinatario=destinatario,
                attore=actor,
                task=task,
                tipo=Notification.Tipo.TASK_REASSIGNED,
                titolo="Attività riassegnata",
                messaggio=(
                    f"L'attività “{task.titolo}” è stata riassegnata "
                    f"a {task.assegnato_a}."
                ),
            )
        )

    return risultati


@transaction.atomic
def notify_task_status_changed(*, task, actor, stato_precedente):
    risultati = []

    for destinatario in _phase_recipients(fase=task.fase, actor=actor):
        risultati.append(
            _create_notification(
                destinatario=destinatario,
                attore=actor,
                task=task,
                tipo=Notification.Tipo.TASK_STATUS_CHANGED,
                titolo="Cambio stato attività",
                messaggio=(
                    f"L'attività “{task.titolo}” è passata da "
                    f"{stato_precedente} a {task.get_stato_display()}."
                ),
            )
        )

    return risultati


@transaction.atomic
def notify_task_deleted(*, titolo_task, commessa, fase, actor):
    """
    Il task viene passato già eliminato: nessuna FK collegata
    (CASCADE la cancellerebbe insieme all'oggetto), i dettagli restano
    nel testo del messaggio.
    """

    risultati = []

    for destinatario in _phase_recipients(fase=fase, actor=actor):
        risultati.append(
            _create_notification(
                destinatario=destinatario,
                attore=actor,
                tipo=Notification.Tipo.TASK_DELETED,
                titolo="Attività eliminata",
                messaggio=(
                    f"L'attività “{titolo_task}” della commessa "
                    f"{commessa.codice} è stata eliminata."
                ),
            )
        )

    return risultati


# =========================================================
# FASI (TEAMWORK)
# =========================================================


@transaction.atomic
def notify_fase_creata(*, fase, actor):
    risultati = []

    for destinatario in _team_recipients(commessa=fase.commessa, actor=actor):
        risultati.append(
            _create_notification(
                destinatario=destinatario,
                attore=actor,
                fase=fase,
                tipo=Notification.Tipo.FASE_CREATA,
                titolo="Nuova fase",
                messaggio=(
                    f"È stata creata la fase “{fase.nome}” "
                    f"sulla commessa {fase.commessa.codice}."
                ),
            )
        )

    return risultati


@transaction.atomic
def notify_fase_aggiornata(*, fase, actor, eliminata=False, azione="aggiornata"):
    """
    Copre modifica, eliminazione e riapertura (Teamwork le raggruppa in
    un'unica categoria di preferenza). Se eliminata=True, nessuna FK
    collegata per lo stesso motivo delle altre notifiche di eliminazione.
    """

    risultati = []

    for destinatario in _team_recipients(commessa=fase.commessa, actor=actor):
        risultati.append(
            _create_notification(
                destinatario=destinatario,
                attore=actor,
                fase=None if eliminata else fase,
                tipo=Notification.Tipo.FASE_AGGIORNATA,
                titolo="Fase aggiornata",
                messaggio=(
                    f"La fase “{fase.nome}” della commessa "
                    f"{fase.commessa.codice} è stata {azione}."
                ),
            )
        )

    return risultati


# =========================================================
# DOCUMENTI (TEAMWORK)
# =========================================================


