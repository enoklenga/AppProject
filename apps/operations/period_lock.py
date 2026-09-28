"""Locking condiviso per i periodi mensili.

Tutte le mutazioni che possono cambiare ore/spese del mese devono acquisire
lo stesso lock usato dalla chiusura del periodo. In questo modo il controllo
"periodo aperto" e la scrittura fanno parte della stessa sezione critica.
"""
from datetime import date

from django.core.exceptions import ValidationError

from .models import PeriodoMensile


class PeriodoChiusoError(ValidationError):
    """Operazione bloccata perché uno dei periodi mensili è chiuso."""


def lock_periodo(*, anno: int, mese: int) -> PeriodoMensile:
    """Crea se necessario e blocca la riga mensile per la transazione corrente.

    La funzione va chiamata all'interno di ``transaction.atomic()``.
    """
    if not 1 <= mese <= 12:
        raise ValidationError("Il mese indicato non è valido.")

    periodo, _ = PeriodoMensile.objects.get_or_create(
        anno=anno,
        mese=mese,
    )
    return PeriodoMensile.objects.select_for_update().get(pk=periodo.pk)


def lock_periodi_per_date(*giorni: date) -> list[PeriodoMensile]:
    """Blocca tutti i mesi coinvolti in ordine stabile per ridurre i deadlock."""
    chiavi = sorted({(giorno.year, giorno.month) for giorno in giorni if giorno})
    return [lock_periodo(anno=anno, mese=mese) for anno, mese in chiavi]


def verifica_periodi_aperti(*giorni: date) -> list[PeriodoMensile]:
    """Blocca i mesi e solleva errore se almeno uno è già chiuso."""
    periodi = lock_periodi_per_date(*giorni)
    chiusi = [p for p in periodi if p.stato == PeriodoMensile.Stato.CHIUSO]
    if chiusi:
        elenco = ", ".join(f"{p.mese:02d}/{p.anno}" for p in chiusi)
        raise PeriodoChiusoError(
            f"Il periodo {elenco} è chiuso. Deve essere riaperto da un Admin."
        )
    return periodi
