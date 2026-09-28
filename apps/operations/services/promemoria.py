"""
Promemoria automatici per i consulenti senza ore inserite (spec §7ter).

Estratto da apps/operations/services.py: individuazione dei destinatari,
composizione e invio delle email di promemoria.
"""
import calendar
from dataclasses import dataclass
from datetime import date, datetime, time
from typing import Iterable

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.mail import EmailMultiAlternatives
from django.db.models import Q
from django.template.loader import render_to_string
from django.utils import timezone

from apps.accounts.models import User
from apps.projects.models import Assegnazione

from ..models import ConfigurazionePromemoria, InvioPromemoria, PeriodoMensile


@dataclass(frozen=True)
class DestinatarioPromemoria:
    consulente: User
    gia_inviato: bool
    ultimo_stato: str | None


@dataclass(frozen=True)
class EsitoInvioPromemoria:
    anno: int
    mese: int
    destinatari: int
    inviati: int
    saltati: int
    errori: int
    motivo_salto: str = ""


def estremi_mese(anno: int, mese: int) -> tuple[date, date]:
    if not 1 <= mese <= 12:
        raise ValidationError("Il mese deve essere compreso tra 1 e 12.")
    ultimo_giorno = calendar.monthrange(anno, mese)[1]
    return (
        date(anno, mese, 1),
        date(anno, mese, ultimo_giorno),
    )


def configurazione_promemoria_corrente():
    return ConfigurazionePromemoria.objects.order_by("id").first()


def inizializza_configurazione_promemoria(*, attore):
    configurazione = configurazione_promemoria_corrente()
    if configurazione is not None:
        return configurazione

    return ConfigurazionePromemoria.objects.create(
        giorno_invio=25,
        ora_invio=time(9, 0),
        attiva=True,
        solo_assenza_totale_ore=True,
        aggiornata_da=attore,
    )


def consulenti_senza_ore(
    *,
    anno: int,
    mese: int,
) -> list[DestinatarioPromemoria]:
    inizio, fine = estremi_mese(anno, mese)

    consulenti = (
        User.objects.filter(
            ruolo__in=(User.Ruolo.CONSULENTE, User.Ruolo.RESPONSABILE_CONSULENZA),
            is_active=True,
            assegnazioni__stato=Assegnazione.Stato.ATTIVA,
            assegnazioni__data_inizio__lte=fine,
        )
        .filter(
            Q(assegnazioni__data_fine__isnull=True)
            | Q(assegnazioni__data_fine__gte=inizio)
        )
        .exclude(
            assegnazioni__righe_ore__data__year=anno,
            assegnazioni__righe_ore__data__month=mese,
        )
        .distinct()
        .order_by("last_name", "first_name", "email")
    )

    invii = {
        invio.consulente_id: invio
        for invio in InvioPromemoria.objects.filter(
            consulente__in=consulenti,
            anno=anno,
            mese=mese,
        )
    }

    return [
        DestinatarioPromemoria(
            consulente=consulente,
            gia_inviato=(
                consulente.id in invii
                and invii[consulente.id].stato
                == InvioPromemoria.Stato.INVIATO
            ),
            ultimo_stato=(
                invii[consulente.id].stato
                if consulente.id in invii
                else None
            ),
        )
        for consulente in consulenti
    ]


def periodo_promemoria_chiuso(*, anno: int, mese: int) -> bool:
    return PeriodoMensile.objects.filter(
        anno=anno,
        mese=mese,
        stato=PeriodoMensile.Stato.CHIUSO,
    ).exists()


def promemoria_programmato_dovuto(
    *,
    configurazione: ConfigurazionePromemoria,
    momento=None,
) -> bool:
    momento = momento or timezone.now()
    locale = timezone.localtime(momento)

    if not configurazione.attiva:
        return False

    if locale.day > configurazione.giorno_invio:
        return True

    if locale.day < configurazione.giorno_invio:
        return False

    ora_corrente = locale.time().replace(tzinfo=None)
    return ora_corrente >= configurazione.ora_invio


def _email_promemoria(
    *,
    consulente: User,
    anno: int,
    mese: int,
) -> EmailMultiAlternatives:
    fasi = (
        Assegnazione.objects
        .filter(consulente=consulente, stato=Assegnazione.Stato.ATTIVA)
        .select_related("commessa", "fase")
        .order_by("commessa__codice", "fase__ordine", "fase__nome")
    )
    contesto = {
        "consulente": consulente,
        "fasi": fasi,
        "anno": anno,
        "mese": mese,
        "mese_testo": date(anno, mese, 1).strftime("%B %Y"),
        "login_url": f"{settings.SITE_URL.rstrip('/')}/login/",
    }
    oggetto = f"Promemoria compilazione timesheet – {mese:02d}/{anno}"
    testo = render_to_string(
        "emails/promemoria_timesheet.txt",
        contesto,
    )
    html = render_to_string(
        "emails/promemoria_timesheet.html",
        contesto,
    )

    email = EmailMultiAlternatives(
        subject=oggetto,
        body=testo,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[consulente.email],
    )
    email.attach_alternative(html, "text/html")
    return email


def invia_promemoria(
    *,
    configurazione: ConfigurazionePromemoria,
    anno: int,
    mese: int,
    forza: bool = False,
    momento=None,
) -> EsitoInvioPromemoria:
    momento = momento or timezone.now()

    if periodo_promemoria_chiuso(anno=anno, mese=mese):
        return EsitoInvioPromemoria(
            anno=anno,
            mese=mese,
            destinatari=0,
            inviati=0,
            saltati=0,
            errori=0,
            motivo_salto="Il periodo è già chiuso.",
        )

    if not forza and not promemoria_programmato_dovuto(
        configurazione=configurazione,
        momento=momento,
    ):
        return EsitoInvioPromemoria(
            anno=anno,
            mese=mese,
            destinatari=0,
            inviati=0,
            saltati=0,
            errori=0,
            motivo_salto="Il promemoria non è ancora dovuto.",
        )

    destinatari = consulenti_senza_ore(anno=anno, mese=mese)
    inviati = 0
    saltati = 0
    errori = 0

    for destinatario in destinatari:
        if destinatario.gia_inviato:
            saltati += 1
            continue

        invio, _ = InvioPromemoria.objects.get_or_create(
            consulente=destinatario.consulente,
            anno=anno,
            mese=mese,
            defaults={
                "configurazione": configurazione,
                "stato": InvioPromemoria.Stato.ERRORE,
                "data_tentativo": momento,
                "errore": "Tentativo in corso.",
            },
        )

        invio.configurazione = configurazione
        invio.data_tentativo = momento

        try:
            risultato = _email_promemoria(
                consulente=destinatario.consulente,
                anno=anno,
                mese=mese,
            ).send(fail_silently=False)

            if risultato != 1:
                raise RuntimeError(
                    "Il backend email non ha confermato l'invio."
                )
        except Exception as exc:
            invio.stato = InvioPromemoria.Stato.ERRORE
            invio.errore = str(exc)[:2000]
            invio.save()
            errori += 1
        else:
            invio.stato = InvioPromemoria.Stato.INVIATO
            invio.errore = ""
            invio.save()
            inviati += 1

    return EsitoInvioPromemoria(
        anno=anno,
        mese=mese,
        destinatari=len(destinatari),
        inviati=inviati,
        saltati=saltati,
        errori=errori,
    )


def invia_email_test(*, destinatario: User) -> int:
    email = EmailMultiAlternatives(
        subject="Test configurazione email – LEFTRACK",
        body=(
            "Questa email conferma che il backend di posta del sistema "
            "LEFTRACK è configurato correttamente."
        ),
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[destinatario.email],
    )
    return email.send(fail_silently=False)
