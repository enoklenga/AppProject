"""Regole centralizzate del lifecycle operativo delle commesse e delle fasi.

Il campo ``workflow_stato`` non è più puramente descrittivo: gli stati di
sospensione/chiusura governano le mutazioni operative in modo coerente tra
planning, task e consuntivi. ``IN_CHIUSURA`` blocca la creazione di nuovo
lavoro ma lascia possibili le operazioni necessarie a completare quanto già
eseguito (es. conferma di una sessione agenda già pianificata).
"""

from apps.phases.models import FaseCommessa
from apps.projects.models import Commessa


WORKFLOW_BLOCCANTI = {
    Commessa.WorkflowStato.SOSPESA,
    Commessa.WorkflowStato.CHIUSA,
}

WORKFLOW_BLOCCANTI_NUOVO_LAVORO = {
    *WORKFLOW_BLOCCANTI,
    Commessa.WorkflowStato.IN_CHIUSURA,
}

FASI_BLOCCANTI_NUOVO_LAVORO = {
    FaseCommessa.Stato.COMPLETATA,
    FaseCommessa.Stato.SOSPESA,
}


def commessa_permette_operativita(commessa: Commessa) -> bool:
    """Operazioni su lavoro già esistente (es. conferme/correzioni)."""
    return (
        commessa.stato == Commessa.Stato.APERTA
        and commessa.workflow_stato not in WORKFLOW_BLOCCANTI
    )


def commessa_permette_nuovo_lavoro(commessa: Commessa) -> bool:
    """Creazione/modifica di planning, task o nuove assegnazioni."""
    return (
        commessa.stato == Commessa.Stato.APERTA
        and commessa.workflow_stato not in WORKFLOW_BLOCCANTI_NUOVO_LAVORO
    )


def fase_permette_nuovo_lavoro(fase: FaseCommessa) -> bool:
    return fase.stato not in FASI_BLOCCANTI_NUOVO_LAVORO
