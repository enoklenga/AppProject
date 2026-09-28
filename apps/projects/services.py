"""Servizi applicativi per operazioni amministrative su progetti/assegnazioni."""
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Count, Q, Sum
from django.utils import timezone

from apps.operations.models import AuditLog

from .models import Assegnazione, Commessa
from .workflow import commessa_permette_nuovo_lavoro, fase_permette_nuovo_lavoro


def _assegnazione_snapshot(assegnazione: Assegnazione) -> dict:
    return {
        "consulente_id": str(assegnazione.consulente_id),
        "commessa_id": str(assegnazione.commessa_id),
        "fase_id": str(assegnazione.fase_id),
        "ore_previste": assegnazione.ore_previste,
        "ruolo_commessa": assegnazione.ruolo_commessa,
        "stato": assegnazione.stato,
        "data_inizio": assegnazione.data_inizio.isoformat(),
        "data_fine": (
            assegnazione.data_fine.isoformat()
            if assegnazione.data_fine
            else None
        ),
    }


def assegnazione_snapshot(assegnazione: Assegnazione) -> dict:
    """Serializzazione stabile usata dagli audit amministrativi."""
    return _assegnazione_snapshot(assegnazione)


def _valida_riattivazione(assegnazione: Assegnazione) -> None:
    if not assegnazione.consulente.is_active:
        raise ValidationError(
            "Non è possibile riattivare l'assegnazione: il consulente è disattivato."
        )

    if not commessa_permette_nuovo_lavoro(assegnazione.commessa):
        raise ValidationError(
            "Non è possibile riattivare l'assegnazione nello stato workflow corrente della commessa."
        )

    if assegnazione.fase.commessa_id != assegnazione.commessa_id:
        raise ValidationError(
            "La fase dell'assegnazione non appartiene alla commessa."
        )

    if not fase_permette_nuovo_lavoro(assegnazione.fase):
        raise ValidationError(
            "Non è possibile riattivare l'assegnazione su una fase completata o sospesa."
        )

    if assegnazione.data_inizio < assegnazione.commessa.data_inizio:
        raise ValidationError(
            "La data di inizio dell'assegnazione precede quella della commessa."
        )

    if (
        assegnazione.commessa.data_fine_prevista
        and assegnazione.data_inizio > assegnazione.commessa.data_fine_prevista
    ):
        raise ValidationError(
            "La data di inizio dell'assegnazione supera la fine prevista della commessa."
        )

    if (
        assegnazione.commessa.data_fine_prevista
        and assegnazione.data_fine
        and assegnazione.data_fine > assegnazione.commessa.data_fine_prevista
    ):
        raise ValidationError(
            "La data di fine dell'assegnazione supera quella della commessa."
        )

    if assegnazione.data_inizio < assegnazione.fase.data_inizio:
        raise ValidationError(
            "La data di inizio dell'assegnazione precede quella della fase."
        )

    if (
        assegnazione.fase.data_fine_prevista
        and assegnazione.data_inizio > assegnazione.fase.data_fine_prevista
    ):
        raise ValidationError(
            "La data di inizio dell'assegnazione supera la fine prevista della fase."
        )

    if (
        assegnazione.fase.data_fine_prevista
        and assegnazione.data_fine
        and assegnazione.data_fine > assegnazione.fase.data_fine_prevista
    ):
        raise ValidationError(
            "La data di fine dell'assegnazione supera quella della fase."
        )

    duplicata = Assegnazione.objects.filter(
        consulente=assegnazione.consulente,
        fase=assegnazione.fase,
        stato=Assegnazione.Stato.ATTIVA,
    ).exclude(pk=assegnazione.pk)
    if duplicata.exists():
        raise ValidationError(
            "Esiste già un'assegnazione attiva per questo consulente e questa fase."
        )


@transaction.atomic
def set_assegnazione_stato(
    *,
    attore,
    assegnazione: Assegnazione,
    nuovo_stato: str,
) -> Assegnazione:
    """Conclude/riattiva un'assegnazione applicando tutte le invarianti."""
    if not getattr(attore, "is_admin_lef", False):
        raise PermissionDenied(
            "Questa operazione è riservata agli Admin LEF."
        )

    if nuovo_stato not in {
        Assegnazione.Stato.ATTIVA,
        Assegnazione.Stato.CONCLUSA,
    }:
        raise ValidationError("Stato assegnazione non valido.")

    # Lock coerente con gli altri flussi di dominio: Commessa -> Fase -> Assegnazione.
    # In questo modo una riattivazione non può correre in parallelo con la
    # chiusura/modifica della commessa o con l'aggiornamento della fase.
    Commessa.objects.select_for_update().get(pk=assegnazione.commessa_id)
    from apps.phases.models import FaseCommessa
    FaseCommessa.objects.select_for_update().get(pk=assegnazione.fase_id)
    assegnazione = (
        Assegnazione.objects.select_for_update()
        .select_related("consulente", "commessa", "fase")
        .get(pk=assegnazione.pk)
    )

    if assegnazione.stato == nuovo_stato:
        return assegnazione

    precedente = _assegnazione_snapshot(assegnazione)

    if nuovo_stato == Assegnazione.Stato.ATTIVA:
        _valida_riattivazione(assegnazione)
    else:
        from apps.planning.models import GiornoPianificato

        sessioni_bloccanti = GiornoPianificato.objects.select_for_update().filter(
            assegnazione=assegnazione
        ).filter(
            Q(stato_sessione=GiornoPianificato.StatoSessione.PIANIFICATA)
            | Q(
                stato_sessione=GiornoPianificato.StatoSessione.CONFERMATA,
                riga_ore_generata__isnull=True,
            )
            | Q(
                stato_sessione=GiornoPianificato.StatoSessione.STORICO_ALLINEATO,
                riga_ore_generata__isnull=True,
            )
        )
        if sessioni_bloccanti.exists():
            raise ValidationError(
                "Non puoi concludere l'assegnazione: esistono sessioni agenda "
                "ancora da confermare o non correttamente collegate al timesheet."
            )

    assegnazione.stato = nuovo_stato
    assegnazione.save(update_fields=("stato", "updated_at"))

    AuditLog.objects.create(
        utente=attore,
        entita="Assegnazione",
        entita_id=assegnazione.id,
        azione=(
            "RIATTIVAZIONE"
            if nuovo_stato == Assegnazione.Stato.ATTIVA
            else "CONCLUSIONE"
        ),
        valore_precedente=precedente,
        valore_nuovo=_assegnazione_snapshot(assegnazione),
        motivazione="Cambio stato assegnazione da interfaccia amministrativa.",
    )

    return assegnazione


def sync_general_phase_dates(commessa) -> None:
    """Allinea la fase tecnica Generale alle date della commessa.

    Le altre fasi non vengono toccate: la validazione del form impedisce che
    risultino fuori dal nuovo intervallo della commessa.
    """
    from apps.phases.models import FaseCommessa

    fase = (
        FaseCommessa.objects.select_for_update()
        .filter(commessa=commessa, sistema=True)
        .first()
    )
    if fase is None:
        return

    campi = []
    if fase.data_inizio != commessa.data_inizio:
        fase.data_inizio = commessa.data_inizio
        campi.append("data_inizio")
    if fase.data_fine_prevista != commessa.data_fine_prevista:
        fase.data_fine_prevista = commessa.data_fine_prevista
        campi.append("data_fine_prevista")

    if campi:
        fase.save(update_fields=[*campi, "updated_at"])


def periodi_impattati_da_tariffa(*, assegnazione, tipo_attivita, valida_dal):
    """Restituisce le date di righe ore la cui tariffa cambierebbe."""
    from apps.timesheets.models import RigaOre
    from .models import TariffaAssegnazione

    prossima = (
        TariffaAssegnazione.objects.filter(
            assegnazione=assegnazione,
            tipo_attivita=tipo_attivita,
            valida_dal__gt=valida_dal,
        )
        .order_by("valida_dal")
        .values_list("valida_dal", flat=True)
        .first()
    )
    righe = RigaOre.objects.filter(
        assegnazione=assegnazione,
        tipo_attivita=tipo_attivita,
        data__gte=valida_dal,
    )
    if prossima:
        righe = righe.filter(data__lt=prossima)
    return list(righe.values_list("data", flat=True).distinct())


def verifica_tariffa_periodi_aperti(
    *,
    assegnazione,
    tipo_attivita,
    valida_dal,
    lock: bool = False,
) -> None:
    """Impedisce che una nuova decorrenza ricalcoli mesi già chiusi."""
    from apps.operations.models import PeriodoMensile
    from apps.operations.period_lock import lock_periodi_per_date

    date_impattate = periodi_impattati_da_tariffa(
        assegnazione=assegnazione,
        tipo_attivita=tipo_attivita,
        valida_dal=valida_dal,
    )
    if not date_impattate:
        return

    if lock:
        periodi = lock_periodi_per_date(*date_impattate)
        chiusi = [p for p in periodi if p.stato == PeriodoMensile.Stato.CHIUSO]
        impattati = sorted((p.anno, p.mese) for p in chiusi)
    else:
        mesi_righe = {(d.year, d.month) for d in date_impattate}
        mesi_chiusi = set(
            PeriodoMensile.objects.filter(
                stato=PeriodoMensile.Stato.CHIUSO,
            ).values_list("anno", "mese")
        )
        impattati = sorted(mesi_righe & mesi_chiusi)

    if impattati:
        elenco = ", ".join(f"{mese:02d}/{anno}" for anno, mese in impattati)
        raise ValidationError(
            "La nuova tariffa modificherebbe la valorizzazione di periodi già chiusi "
            f"({elenco}). Riapri prima i periodi interessati."
        )



def _can_manage_commessa_lifecycle(attore, commessa: Commessa) -> bool:
    if getattr(attore, "is_admin_lef", False):
        return True
    from .permissions import is_active_pm
    return is_active_pm(attore, commessa)


@transaction.atomic
def update_handover(
    *,
    attore,
    commessa: Commessa,
    completato: bool,
    note: str = "",
) -> Commessa:
    """Unico punto di mutazione dell'handover commerciale, con lock e audit."""
    commessa = Commessa.objects.select_for_update().get(pk=commessa.pk)
    if not _can_manage_commessa_lifecycle(attore, commessa):
        raise PermissionDenied(
            "La presa in carico dell'handover è riservata al PM della commessa o a un Admin LEF."
        )
    if commessa.stato == Commessa.Stato.CHIUSA:
        raise ValidationError("La commessa è chiusa e l'handover non è modificabile.")

    completato = bool(completato)
    note = (note or "").strip()
    precedente = {
        "handover_completato": commessa.handover_completato,
        "handover_note": commessa.handover_note,
        "workflow_stato": commessa.workflow_stato,
    }

    if not completato and commessa.handover_completato and commessa.workflow_stato in {
        Commessa.WorkflowStato.IN_ESECUZIONE,
        Commessa.WorkflowStato.IN_CHIUSURA,
        Commessa.WorkflowStato.SOSPESA,
    }:
        raise ValidationError(
            "L'handover non può essere annullato dopo l'avvio operativo della commessa."
        )

    commessa.handover_note = note
    commessa.handover_completato = completato
    if completato:
        if not commessa.handover_completato_il:
            commessa.handover_completato_il = timezone.now()
            commessa.handover_completato_da = attore
        if commessa.workflow_stato in {
            Commessa.WorkflowStato.DA_PRENDERE_IN_CARICO,
            Commessa.WorkflowStato.HANDOVER,
        }:
            commessa.workflow_stato = Commessa.WorkflowStato.PIANIFICAZIONE
    else:
        commessa.handover_completato_il = None
        commessa.handover_completato_da = None
        if commessa.workflow_stato == Commessa.WorkflowStato.PIANIFICAZIONE:
            commessa.workflow_stato = Commessa.WorkflowStato.HANDOVER

    commessa.save(
        update_fields=(
            "handover_note",
            "handover_completato",
            "handover_completato_il",
            "handover_completato_da",
            "workflow_stato",
            "updated_at",
        )
    )

    AuditLog.objects.create(
        utente=attore,
        entita="CommessaHandover",
        entita_id=commessa.id,
        azione="AGGIORNAMENTO_HANDOVER",
        valore_precedente=precedente,
        valore_nuovo={
            "handover_completato": commessa.handover_completato,
            "handover_note": commessa.handover_note,
            "workflow_stato": commessa.workflow_stato,
        },
        motivazione="Aggiornamento presa in carico handover commerciale.",
    )
    return commessa


@transaction.atomic
def set_commessa_workflow(
    *,
    attore,
    commessa: Commessa,
    nuovo_stato: str,
    motivazione: str = "",
) -> Commessa:
    """Transizione auditata del lifecycle; CHIUSA resta riservata a chiudi_commessa()."""
    commessa = Commessa.objects.select_for_update().get(pk=commessa.pk)
    if not _can_manage_commessa_lifecycle(attore, commessa):
        raise PermissionDenied("Non puoi modificare il workflow di questa commessa.")
    if commessa.stato == Commessa.Stato.CHIUSA:
        raise ValidationError("La commessa è chiusa. Usa la riapertura amministrativa.")

    validi = {value for value, _ in Commessa.WorkflowStato.choices}
    if nuovo_stato not in validi or nuovo_stato == Commessa.WorkflowStato.CHIUSA:
        raise ValidationError("Stato workflow non valido per una transizione manuale.")
    motivazione = (motivazione or "").strip()
    if not motivazione:
        raise ValidationError("La transizione workflow richiede una motivazione esplicita.")
    if nuovo_stato == commessa.workflow_stato:
        return commessa

    transizioni = {
        Commessa.WorkflowStato.DA_PRENDERE_IN_CARICO: {
            Commessa.WorkflowStato.HANDOVER,
            Commessa.WorkflowStato.SOSPESA,
        },
        Commessa.WorkflowStato.HANDOVER: {
            Commessa.WorkflowStato.DA_PRENDERE_IN_CARICO,
            Commessa.WorkflowStato.PIANIFICAZIONE,
            Commessa.WorkflowStato.SOSPESA,
        },
        Commessa.WorkflowStato.PIANIFICAZIONE: {
            Commessa.WorkflowStato.HANDOVER,
            Commessa.WorkflowStato.IN_ESECUZIONE,
            Commessa.WorkflowStato.SOSPESA,
        },
        Commessa.WorkflowStato.IN_ESECUZIONE: {
            Commessa.WorkflowStato.IN_CHIUSURA,
            Commessa.WorkflowStato.SOSPESA,
        },
        Commessa.WorkflowStato.IN_CHIUSURA: {
            Commessa.WorkflowStato.IN_ESECUZIONE,
            Commessa.WorkflowStato.SOSPESA,
        },
        Commessa.WorkflowStato.SOSPESA: {
            Commessa.WorkflowStato.DA_PRENDERE_IN_CARICO,
            Commessa.WorkflowStato.HANDOVER,
            Commessa.WorkflowStato.PIANIFICAZIONE,
            Commessa.WorkflowStato.IN_ESECUZIONE,
            Commessa.WorkflowStato.IN_CHIUSURA,
        },
    }
    if nuovo_stato not in transizioni.get(commessa.workflow_stato, set()):
        raise ValidationError(
            f"Transizione non consentita da {commessa.get_workflow_stato_display()} "
            f"a {dict(Commessa.WorkflowStato.choices).get(nuovo_stato, nuovo_stato)}."
        )

    stati_post_handover = {
        Commessa.WorkflowStato.PIANIFICAZIONE,
        Commessa.WorkflowStato.IN_ESECUZIONE,
        Commessa.WorkflowStato.IN_CHIUSURA,
    }
    if (
        commessa.workflow_stato in {
            Commessa.WorkflowStato.DA_PRENDERE_IN_CARICO,
            Commessa.WorkflowStato.HANDOVER,
        }
        and nuovo_stato in stati_post_handover
        and not commessa.handover_completato
    ):
        raise ValidationError("Completa prima l'handover commerciale della commessa.")

    precedente = _commessa_snapshot(commessa)
    commessa.workflow_stato = nuovo_stato
    commessa.save(update_fields=("workflow_stato", "updated_at"))
    AuditLog.objects.create(
        utente=attore,
        entita="Commessa",
        entita_id=commessa.id,
        azione="CAMBIO_WORKFLOW",
        valore_precedente=precedente,
        valore_nuovo=_commessa_snapshot(commessa),
        motivazione=motivazione,
    )
    return commessa

def agenda_progress(commessa: Commessa) -> dict:
    """Avanzamento operativo derivato dall'agenda senza falsificare lo storico.

    Le percentuali operative usano le sessioni *risolte*: confermate dalla
    risorsa, allineate in modo univoco a una riga timesheet storica oppure
    esplicitamente esenti perché precedenti al go-live. Le conferme utente
    restano conteggiate separatamente.
    """
    from apps.planning.models import GiornoPianificato

    qs = GiornoPianificato.objects.filter(assegnazione__commessa=commessa)
    stati_risolti = GiornoPianificato.stati_risolti()
    aggregati = qs.aggregate(
        sessioni_totali=Count("id"),
        sessioni_risolte=Count(
            "id",
            filter=Q(stato_sessione__in=stati_risolti),
        ),
        sessioni_confermate=Count(
            "id",
            filter=Q(stato_sessione=GiornoPianificato.StatoSessione.CONFERMATA),
        ),
        sessioni_storico_allineato=Count(
            "id",
            filter=Q(stato_sessione=GiornoPianificato.StatoSessione.STORICO_ALLINEATO),
        ),
        sessioni_storico_esente=Count(
            "id",
            filter=Q(stato_sessione=GiornoPianificato.StatoSessione.STORICO_ESENTE),
        ),
        ore_pianificate_totali=Sum("ore_pianificate"),
        ore_risolte=Sum(
            "ore_pianificate",
            filter=Q(stato_sessione__in=stati_risolti),
        ),
        ore_confermate=Sum(
            "ore_pianificate",
            filter=Q(stato_sessione=GiornoPianificato.StatoSessione.CONFERMATA),
        ),
    )
    sessioni_totali = aggregati["sessioni_totali"] or 0
    sessioni_risolte = aggregati["sessioni_risolte"] or 0
    sessioni_confermate = aggregati["sessioni_confermate"] or 0
    ore_pianificate = aggregati["ore_pianificate_totali"] or 0
    ore_risolte = aggregati["ore_risolte"] or 0
    ore_confermate = aggregati["ore_confermate"] or 0

    return {
        "sessioni_totali": sessioni_totali,
        "sessioni_risolte": sessioni_risolte,
        "sessioni_confermate": sessioni_confermate,
        "sessioni_storico_allineato": aggregati["sessioni_storico_allineato"] or 0,
        "sessioni_storico_esente": aggregati["sessioni_storico_esente"] or 0,
        "sessioni_da_confermare": max(sessioni_totali - sessioni_risolte, 0),
        "ore_pianificate": ore_pianificate,
        "ore_risolte": ore_risolte,
        "ore_confermate": ore_confermate,
        "ore_da_confermare": max(ore_pianificate - ore_risolte, 0),
        "percentuale_sessioni": (
            round((sessioni_risolte / sessioni_totali) * 100, 1)
            if sessioni_totali
            else 0
        ),
        "percentuale_ore": (
            round((ore_risolte / ore_pianificate) * 100, 1)
            if ore_pianificate
            else 0
        ),
        "completa": sessioni_risolte == sessioni_totali,
    }


def _commessa_snapshot(commessa: Commessa) -> dict:
    return {
        "stato": commessa.stato,
        "workflow_stato": commessa.workflow_stato,
        "handover_completato": commessa.handover_completato,
    }


@transaction.atomic
def chiudi_commessa(*, attore, commessa: Commessa) -> Commessa:
    """Chiude la commessa solo quando tutte le sessioni agenda sono confermate."""
    if not getattr(attore, "is_admin_lef", False):
        raise PermissionDenied("Questa operazione è riservata agli Admin LEF.")

    commessa = Commessa.objects.select_for_update().get(pk=commessa.pk)
    if commessa.stato == Commessa.Stato.CHIUSA:
        return commessa

    from apps.planning.models import GiornoPianificato

    # Blocca le righe agenda per evitare conferme/modifiche concorrenti mentre
    # viene valutato il gate di chiusura.
    sessioni = GiornoPianificato.objects.select_for_update().filter(
        assegnazione__commessa=commessa
    )
    non_confermate = sessioni.exclude(
        stato_sessione__in=GiornoPianificato.stati_risolti(),
    )
    if non_confermate.exists():
        conteggio = non_confermate.count()
        ore = non_confermate.aggregate(totale=Sum("ore_pianificate"))["totale"] or 0
        raise ValidationError(
            f"Impossibile chiudere la commessa: {conteggio} sessioni agenda "
            f"({ore} ore) non risultano ancora concluse/confermate dalla risorsa."
        )

    precedente = _commessa_snapshot(commessa)
    commessa.stato = Commessa.Stato.CHIUSA
    commessa.workflow_stato = Commessa.WorkflowStato.CHIUSA
    commessa.save(update_fields=("stato", "workflow_stato", "updated_at"))

    AuditLog.objects.create(
        utente=attore,
        entita="Commessa",
        entita_id=commessa.id,
        azione="CHIUSURA",
        valore_precedente=precedente,
        valore_nuovo=_commessa_snapshot(commessa),
        motivazione="Chiusura consentita dopo conferma completa delle sessioni agenda.",
    )
    return commessa


@transaction.atomic
def riapri_commessa(*, attore, commessa: Commessa) -> Commessa:
    if not getattr(attore, "is_admin_lef", False):
        raise PermissionDenied("Questa operazione è riservata agli Admin LEF.")

    commessa = Commessa.objects.select_for_update().get(pk=commessa.pk)
    if commessa.stato == Commessa.Stato.APERTA:
        return commessa

    precedente = _commessa_snapshot(commessa)
    commessa.stato = Commessa.Stato.APERTA
    commessa.workflow_stato = Commessa.WorkflowStato.IN_ESECUZIONE
    commessa.save(update_fields=("stato", "workflow_stato", "updated_at"))

    AuditLog.objects.create(
        utente=attore,
        entita="Commessa",
        entita_id=commessa.id,
        azione="RIAPERTURA",
        valore_precedente=precedente,
        valore_nuovo=_commessa_snapshot(commessa),
        motivazione="Riapertura commessa da interfaccia amministrativa.",
    )
    return commessa
