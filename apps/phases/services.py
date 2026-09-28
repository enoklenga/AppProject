from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models.deletion import ProtectedError

from apps.notifications.services import notify_fase_aggiornata, notify_fase_creata
from apps.projects.models import Assegnazione, Commessa

from .models import FaseCommessa
from .permissions import can_edit_fase, can_manage_fasi


def _valida_nome(nome: str) -> str:
    nome = (nome or "").strip()

    if not nome:
        raise ValidationError("Il nome della fase è obbligatorio.")

    if len(nome) > 255:
        raise ValidationError("Il nome della fase è troppo lungo.")

    return nome


def _valida_date(commessa, data_inizio, data_fine_prevista) -> None:
    if not data_inizio:
        raise ValidationError("La data di inizio della fase è obbligatoria.")
    if data_inizio < commessa.data_inizio:
        raise ValidationError("La fase non può iniziare prima della commessa.")
    if commessa.data_fine_prevista and data_inizio > commessa.data_fine_prevista:
        raise ValidationError("La fase non può iniziare dopo la fine prevista della commessa.")
    if data_fine_prevista and data_fine_prevista < data_inizio:
        raise ValidationError("La data di fine prevista non può precedere la data di inizio.")
    if commessa.data_fine_prevista and data_fine_prevista and data_fine_prevista > commessa.data_fine_prevista:
        raise ValidationError("La fase non può terminare dopo la fine prevista della commessa.")


@transaction.atomic
def create_fase(
    *,
    user,
    commessa,
    nome,
    descrizione="",
    ordine=0,
    stato=FaseCommessa.Stato.DA_INIZIARE,
    data_inizio=None,
    data_fine_prevista=None,
) -> FaseCommessa:
    # La creazione di una fase condivide il lock della commessa con gli
    # aggiornamenti del suo intervallo temporale. La validazione usa quindi
    # sempre le date correnti della commessa, non una copia potenzialmente stale.
    commessa = Commessa.objects.select_for_update().get(pk=commessa.pk)

    if not can_manage_fasi(user, commessa):
        raise PermissionDenied(
            "Non puoi creare fasi su questa commessa."
        )

    nome = _valida_nome(nome)
    _valida_date(commessa, data_inizio, data_fine_prevista)

    if FaseCommessa.objects.filter(commessa=commessa, nome=nome).exists():
        raise ValidationError(
            "Esiste già una fase con questo nome su questa commessa."
        )

    fase = FaseCommessa.objects.create(
        commessa=commessa,
        nome=nome,
        descrizione=descrizione,
        ordine=ordine,
        stato=stato,
        data_inizio=data_inizio,
        data_fine_prevista=data_fine_prevista,
        creata_da=user,
    )

    notify_fase_creata(fase=fase, actor=user)

    return fase


def _valida_figli_nel_nuovo_intervallo(
    fase: FaseCommessa,
    data_inizio,
    data_fine_prevista,
) -> None:
    """Preserva la coerenza temporale dei dati già collegati alla fase."""
    assegnazioni = fase.assegnazioni.all()

    if assegnazioni.filter(data_inizio__lt=data_inizio).exists():
        raise ValidationError(
            "Non puoi spostare l'inizio della fase: esistono assegnazioni che iniziano prima."
        )

    if data_fine_prevista and (
        assegnazioni.filter(data_inizio__gt=data_fine_prevista).exists()
        or assegnazioni.filter(data_fine__gt=data_fine_prevista).exists()
    ):
        raise ValidationError(
            "Non puoi anticipare la fine della fase: esistono assegnazioni fuori dal nuovo intervallo."
        )

    from apps.planning.models import GiornoPianificato
    from apps.timesheets.models import RigaOre, SpesaTrasferta

    if (
        RigaOre.objects.filter(assegnazione__fase=fase, data__lt=data_inizio).exists()
        or SpesaTrasferta.objects.filter(assegnazione__fase=fase, data__lt=data_inizio).exists()
        or GiornoPianificato.objects.filter(assegnazione__fase=fase, data__lt=data_inizio).exists()
        or fase.tasks.filter(data_inizio__lt=data_inizio).exists()
        or fase.tasks.filter(data_scadenza__lt=data_inizio).exists()
    ):
        raise ValidationError(
            "La nuova data di inizio escluderebbe dati operativi già registrati sulla fase."
        )

    if data_fine_prevista and (
        RigaOre.objects.filter(assegnazione__fase=fase, data__gt=data_fine_prevista).exists()
        or SpesaTrasferta.objects.filter(assegnazione__fase=fase, data__gt=data_fine_prevista).exists()
        or GiornoPianificato.objects.filter(assegnazione__fase=fase, data__gt=data_fine_prevista).exists()
        or fase.tasks.filter(data_inizio__gt=data_fine_prevista).exists()
        or fase.tasks.filter(data_scadenza__gt=data_fine_prevista).exists()
    ):
        raise ValidationError(
            "La nuova data di fine escluderebbe dati operativi già registrati sulla fase."
        )


@transaction.atomic
def update_fase(
    *,
    user,
    fase: FaseCommessa,
    nome,
    descrizione="",
    ordine=0,
    stato,
    data_inizio=None,
    data_fine_prevista=None,
) -> FaseCommessa:
    # Ordine di lock condiviso: Commessa -> Fase -> Assegnazioni.
    # Evita inversioni con l'aggiornamento della commessa e con i task.
    commessa = Commessa.objects.select_for_update().get(pk=fase.commessa_id)
    fase = (
        FaseCommessa.objects
        .select_for_update()
        .select_related("commessa")
        .get(pk=fase.pk)
    )

    # Planning/timesheet bloccano l'assegnazione durante le mutazioni: qui
    # acquisiamo gli stessi lock prima di restringere l'intervallo della fase.
    list(
        Assegnazione.objects.select_for_update()
        .filter(fase=fase)
        .values_list("pk", flat=True)
    )

    if not can_edit_fase(user, fase):
        raise PermissionDenied(
            "Non puoi modificare questa fase."
        )

    nome = _valida_nome(nome)
    _valida_date(commessa, data_inizio, data_fine_prevista)
    _valida_figli_nel_nuovo_intervallo(
        fase,
        data_inizio,
        data_fine_prevista,
    )

    duplicata = (
        FaseCommessa.objects
        .filter(commessa=fase.commessa, nome=nome)
        .exclude(pk=fase.pk)
        .exists()
    )

    if duplicata:
        raise ValidationError(
            "Esiste già una fase con questo nome su questa commessa."
        )

    era_conclusa = fase.conclusa

    fase.nome = nome
    fase.descrizione = descrizione
    fase.ordine = ordine
    fase.stato = stato
    fase.data_inizio = data_inizio
    fase.data_fine_prevista = data_fine_prevista

    fase.save(
        update_fields=[
            "nome",
            "descrizione",
            "ordine",
            "stato",
            "data_inizio",
            "data_fine_prevista",
            "updated_at",
        ]
    )

    azione = "riaperta" if era_conclusa and not fase.conclusa else "aggiornata"

    notify_fase_aggiornata(fase=fase, actor=user, azione=azione)

    return fase


@transaction.atomic
def delete_fase(*, user, fase: FaseCommessa) -> None:
    Commessa.objects.select_for_update().get(pk=fase.commessa_id)
    fase = (
        FaseCommessa.objects
        .select_for_update()
        .select_related("commessa")
        .get(pk=fase.pk)
    )

    if not can_manage_fasi(user, fase.commessa):
        raise PermissionDenied(
            "Non puoi eliminare questa fase."
        )

    if fase.sistema:
        raise ValidationError(
            "La fase Generale è la fase predefinita della commessa e non può essere eliminata."
        )

    dipendenze = {
        "assegnazioni": fase.assegnazioni.count(),
        "attività": fase.tasks.count(),
        "documenti": fase.documenti.count(),
    }
    presenti = [
        f"{numero} {nome}"
        for nome, numero in dipendenze.items()
        if numero
    ]
    if presenti:
        raise ValidationError(
            "Non puoi eliminare questa fase: sono ancora collegati "
            + ", ".join(presenti)
            + ". Rimuovi o rialloca prima le dipendenze."
        )

    # La notifica va generata prima della cancellazione: dopo, i dati
    # della fase non sarebbero più disponibili.
    notify_fase_aggiornata(fase=fase, actor=user, eliminata=True, azione="eliminata")

    try:
        fase.delete()
    except ProtectedError as exc:
        # Difesa finale: se in futuro viene aggiunta una nuova FK PROTECT,
        # la UI continua a ricevere un errore business invece di un HTTP 500.
        raise ValidationError(
            "Non puoi eliminare questa fase perché contiene ancora dati collegati."
        ) from exc
