from calendar import Calendar, monthrange
from collections import defaultdict
from datetime import date, timedelta
from urllib.parse import urlencode
from uuid import UUID

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from apps.accounts.access import can_view_operational_details
from apps.accounts.access import can_view_planning_portfolio
from apps.projects.models import Assegnazione, Commessa
from apps.phases.models import FaseCommessa

from .forms import PianificazioneForm
from .models import GiornoPianificato
from .permissions import (
    can_confirm_planning,
    can_delete_planning,
    can_edit_planning,
    can_view_planning,
)
from .selectors import (
    CAPACITA_SETTIMANALE_DEFAULT,
    planned_vs_actual,
    planned_vs_actual_by_consultant,
    planned_vs_actual_by_project,
    visible_assignments_for_user,
    visible_planning_for_user,
)
from .services import (
    confirm_planning,
    create_planning,
    delete_planning,
    update_planning,
)


User = get_user_model()


MESI_ITALIANI = (
    "",
    "Gennaio",
    "Febbraio",
    "Marzo",
    "Aprile",
    "Maggio",
    "Giugno",
    "Luglio",
    "Agosto",
    "Settembre",
    "Ottobre",
    "Novembre",
    "Dicembre",
)


GIORNI_SETTIMANA = (
    "Lun",
    "Mar",
    "Mer",
    "Gio",
    "Ven",
    "Sab",
    "Dom",
)


def _safe_uuid(value):
    if not value:
        return None

    try:
        return UUID(str(value))
    except (ValueError, TypeError, AttributeError):
        return None


def _reference_date(request):
    raw_data = request.GET.get("data")

    if raw_data:
        try:
            return date.fromisoformat(raw_data)
        except ValueError:
            pass

    raw_mese = request.GET.get("mese")

    if raw_mese:
        try:
            anno, mese = map(
                int,
                raw_mese.split("-"),
            )

            return date(
                anno,
                mese,
                1,
            )

        except (ValueError, TypeError):
            pass

    return timezone.localdate()


def _month_end(month_start):
    ultimo_giorno = monthrange(
        month_start.year,
        month_start.month,
    )[1]

    return month_start.replace(
        day=ultimo_giorno,
    )


def _shift_month(value, offset):
    mese = value.month - 1 + offset

    anno = value.year + mese // 12
    mese = mese % 12 + 1

    return date(
        anno,
        mese,
        1,
    )


def _calendar_url(
    *,
    vista,
    data,
    consulente=None,
    commessa=None,
    fase=None,
):
    params = {
        "vista": vista,
        "data": data.isoformat(),
    }

    if consulente:
        params["consulente"] = str(consulente)

    if commessa:
        params["commessa"] = str(commessa)
    if fase:
        params["fase"] = str(fase)

    return (
        f"{reverse('planning:pianificazione-list')}"
        f"?{urlencode(params)}"
    )


def _planning_list_url(data_riferimento):
    return _calendar_url(
        vista="mese",
        data=data_riferimento,
    )


def _add_validation_errors(
    form,
    exc,
):
    for message in exc.messages:
        form.add_error(
            None,
            message,
        )


def _build_event(
    *,
    request,
    pianificazione,
    mostra_consulente,
):
    # Cache per-richiesta dei controlli di supervisione (evita N+1 sul calendario).
    cache = request.__dict__.setdefault("_lef_planning_perm_cache", {})
    return {
        "object": pianificazione,
        "can_edit": can_edit_planning(
            request.user,
            pianificazione,
            cache,
        ),
        "can_delete": can_delete_planning(
            request.user,
            pianificazione,
            cache,
        ),
        "can_confirm": can_confirm_planning(
            request.user,
            pianificazione,
        ),
        "mostra_consulente": mostra_consulente,
    }


@login_required
def pianificazione_list(request):
    if not (
        can_view_operational_details(request.user)
        or can_view_planning_portfolio(request.user)
    ):
        raise PermissionDenied("La pianificazione è riservata ai profili operativi.")
    oggi = timezone.localdate()

    riferimento = _reference_date(request)

    vista = request.GET.get(
        "vista",
        "mese",
    )

    if vista not in {
        "mese",
        "settimana",
    }:
        vista = "mese"

    consulente_id = _safe_uuid(
        request.GET.get("consulente")
    )

    commessa_id = _safe_uuid(
        request.GET.get("commessa")
    )
    fase_id = _safe_uuid(request.GET.get("fase"))

    assegnazioni_visibili = (
        visible_assignments_for_user(
            request.user
        )
    )

    consulenti_filtro = (
        User.objects
        .filter(
            pk__in=assegnazioni_visibili.values(
                "consulente_id"
            )
        )
        .distinct()
        .order_by(
            "last_name",
            "first_name",
            "email",
        )
    )

    commesse_filtro = (
        Commessa.objects
        .filter(pk__in=assegnazioni_visibili.values("commessa_id"))
        .select_related("cliente")
        .distinct()
        .order_by("codice")
    )

    fasi_filtro = (
        FaseCommessa.objects
        .filter(pk__in=assegnazioni_visibili.values("fase_id"))
        .select_related("commessa")
        .distinct()
        .order_by("commessa__codice", "ordine", "nome")
    )

    pianificazioni = visible_planning_for_user(
        request.user
    )

    if consulente_id:
        pianificazioni = pianificazioni.filter(
            assegnazione__consulente_id=(
                consulente_id
            )
        )

        assegnazioni_visibili = (
            assegnazioni_visibili.filter(
                consulente_id=consulente_id
            )
        )

    if commessa_id:
        pianificazioni = pianificazioni.filter(assegnazione__commessa_id=commessa_id)
        assegnazioni_visibili = assegnazioni_visibili.filter(commessa_id=commessa_id)

    if fase_id:
        pianificazioni = pianificazioni.filter(assegnazione__fase_id=fase_id)
        assegnazioni_visibili = assegnazioni_visibili.filter(fase_id=fase_id)

    mostra_consulente = (
        request.user.is_admin_lef
        or consulenti_filtro.count() > 1
    )

    puo_pianificare = (
        request.user.is_admin_lef
        or Assegnazione.objects
        .filter(
            consulente=request.user,
            stato=Assegnazione.Stato.ATTIVA,
            commessa__stato=Commessa.Stato.APERTA,
        )
        .exists()
    )

    calendar_weeks = []
    week_days = []
    carichi_settimanali = []

    if vista == "mese":
        mese = riferimento.replace(
            day=1,
        )

        fine_mese = _month_end(
            mese
        )
        periodo_inizio = mese
        periodo_fine = fine_mese

        calendar_weeks_dates = (
            Calendar(firstweekday=0)
            .monthdatescalendar(
                mese.year,
                mese.month,
            )
        )

        visual_start = (
            calendar_weeks_dates[0][0]
        )

        visual_end = (
            calendar_weeks_dates[-1][-1]
        )

        eventi = (
            pianificazioni
            .filter(
                data__gte=visual_start,
                data__lte=visual_end,
            )
            .order_by(
                "data",
                "assegnazione__consulente__last_name",
                "assegnazione__commessa__codice",
            )
        )

        metriche_queryset = (
            pianificazioni
            .filter(
                data__gte=mese,
                data__lte=fine_mese,
            )
        )

        eventi_per_data = defaultdict(
            list
        )

        for pianificazione in eventi:
            eventi_per_data[
                pianificazione.data
            ].append(
                _build_event(
                    request=request,
                    pianificazione=pianificazione,
                    mostra_consulente=(
                        mostra_consulente
                    ),
                )
            )

        for settimana in calendar_weeks_dates:
            giorni = []

            for giorno in settimana:
                giorni.append(
                    {
                        "data": giorno,
                        "nel_mese": (
                            giorno.month
                            == mese.month
                        ),
                        "oggi": giorno == oggi,
                        "passato": giorno < oggi,
                        "puo_creare": (
                            puo_pianificare
                            and giorno >= oggi
                        ),
                        "eventi": (
                            eventi_per_data[
                                giorno
                            ]
                        ),
                    }
                )

            calendar_weeks.append(
                giorni
            )

        titolo_periodo = (
            f"{MESI_ITALIANI[mese.month]} "
            f"{mese.year}"
        )

        precedente = _shift_month(
            mese,
            -1,
        )

        successivo = _shift_month(
            mese,
            1,
        )

    else:
        lunedi = (
            riferimento
            - timedelta(
                days=riferimento.weekday()
            )
        )

        domenica = (
            lunedi
            + timedelta(days=6)
        )
        periodo_inizio = lunedi
        periodo_fine = domenica

        eventi = (
            pianificazioni
            .filter(
                data__gte=lunedi,
                data__lte=domenica,
            )
            .order_by(
                "data",
                "assegnazione__consulente__last_name",
                "assegnazione__commessa__codice",
            )
        )

        metriche_queryset = eventi

        eventi_per_data = defaultdict(
            list
        )

        for pianificazione in eventi:
            eventi_per_data[
                pianificazione.data
            ].append(
                _build_event(
                    request=request,
                    pianificazione=pianificazione,
                    mostra_consulente=(
                        mostra_consulente
                    ),
                )
            )

        for offset in range(7):
            giorno = (
                lunedi
                + timedelta(days=offset)
            )

            week_days.append(
                {
                    "data": giorno,
                    "nome": (
                        GIORNI_SETTIMANA[
                            giorno.weekday()
                        ]
                    ),
                    "oggi": giorno == oggi,
                    "passato": giorno < oggi,
                    "puo_creare": (
                        puo_pianificare
                        and giorno >= oggi
                    ),
                    "eventi": (
                        eventi_per_data[
                            giorno
                        ]
                    ),
                }
            )

        persone = (
            User.objects
            .filter(
                pk__in=assegnazioni_visibili.values(
                    "consulente_id"
                )
            )
            .distinct()
            .order_by(
                "last_name",
                "first_name",
                "email",
            )
        )

        totali = {
            row[
                "assegnazione__consulente_id"
            ]: row["totale"]
            for row in (
                eventi
                .values(
                    "assegnazione__consulente_id"
                )
                .annotate(
                    totale=Sum(
                        "ore_pianificate"
                    )
                )
            )
        }

        for persona in persone:
            ore = totali.get(
                persona.pk,
                0,
            )

            percentuale = round(
                (
                    ore
                    / CAPACITA_SETTIMANALE_DEFAULT
                )
                * 100
            )

            carichi_settimanali.append(
                {
                    "consulente": persona,
                    "ore": ore,
                    "disponibili": max(
                        CAPACITA_SETTIMANALE_DEFAULT - ore,
                        0,
                    ),
                    "capacita": (
                        CAPACITA_SETTIMANALE_DEFAULT
                    ),
                    "sovraccarico": (
                        ore
                        > CAPACITA_SETTIMANALE_DEFAULT
                    ),
                    "percentuale": min(
                        percentuale,
                        100,
                    ),
                }
            )

        titolo_periodo = (
            f"{lunedi:%d/%m/%Y} – "
            f"{domenica:%d/%m/%Y}"
        )

        precedente = (
            riferimento
            - timedelta(days=7)
        )

        successivo = (
            riferimento
            + timedelta(days=7)
        )

    totale_ore = (
        metriche_queryset.aggregate(
            totale=Sum("ore_pianificate")
        )["totale"]
        or 0
    )

    numero_giornate = (
        metriche_queryset
        .values(
            "assegnazione__consulente_id",
            "data",
        )
        .distinct()
        .count()
    )

    numero_commesse = (
        metriche_queryset
        .values(
            "assegnazione__commessa_id"
        )
        .distinct()
        .count()
    )

    righe = []

    for pianificazione in metriche_queryset.order_by(
        "data",
        "assegnazione__consulente__last_name",
        "assegnazione__commessa__codice",
    ):
        righe.append(
            _build_event(
                request=request,
                pianificazione=pianificazione,
                mostra_consulente=(
                    mostra_consulente
                ),
            )
        )

    mostra_azioni = any(
        evento["can_confirm"]
        or evento["can_edit"]
        or evento["can_delete"]
        for evento in righe
    )

    confronto = planned_vs_actual(
        user=request.user,
        data_inizio=periodo_inizio,
        data_fine=periodo_fine,
        consulente_id=consulente_id,
        commessa_id=commessa_id,
    )

    confronto_consulenti = planned_vs_actual_by_consultant(
        user=request.user,
        data_inizio=periodo_inizio,
        data_fine=periodo_fine,
        commessa_id=commessa_id,
    )

    if consulente_id:
        confronto_consulenti = [
            riga
            for riga in confronto_consulenti
            if str(riga["consulente_id"]) == str(consulente_id)
        ]

    confronto_consulenti = [
        riga
        for riga in confronto_consulenti
        if (
            riga["ore_pianificate"]
            or riga["ore_consuntivate"]
        )
    ]
    confronto_consulenti = sorted(
        confronto_consulenti,
        key=lambda r: (
            (r.get("consulente__last_name") or "").lower(),
            (r.get("consulente__first_name") or "").lower(),
            (r.get("consulente__email") or "").lower(),
        ),
    )

    confronto_commesse = planned_vs_actual_by_project(
        user=request.user,
        data_inizio=periodo_inizio,
        data_fine=periodo_fine,
        consulente_id=consulente_id,
    )

    if commessa_id:
        confronto_commesse = [
            riga
            for riga in confronto_commesse
            if str(riga["commessa_id"]) == str(commessa_id)
        ]

    confronto_commesse = [
        riga
        for riga in confronto_commesse
        if (
            riga["ore_pianificate"]
            or riga["ore_consuntivate"]
        )
    ]

    confronto_commesse = sorted(
        confronto_commesse,
        key=lambda r: (
            (r.get("commessa__codice") or "").lower(),
            (r.get("commessa__cliente__ragione_sociale") or "").lower(),
        ),
    )

    context = {
        "oggi": oggi,
        "vista": vista,
        "titolo_periodo": titolo_periodo,
        "calendar_weeks": calendar_weeks,
        "week_days": week_days,
        "carichi_settimanali": (
            carichi_settimanali
        ),
        "righe": righe,
        "mostra_azioni": mostra_azioni,
        "totale_ore": totale_ore,
        "numero_giornate": numero_giornate,
        "numero_commesse": numero_commesse,
        "puo_pianificare": puo_pianificare,
        "consulenti_filtro": (
            consulenti_filtro
        ),
        "commesse_filtro": (
            commesse_filtro
        ),
        "consulente_selezionato": (
            str(consulente_id)
            if consulente_id
            else ""
        ),
        "commessa_selezionata": (str(commessa_id) if commessa_id else ""),
        "fasi_filtro": fasi_filtro,
        "fase_selezionata": (str(fase_id) if fase_id else ""),
        "mostra_filtro_consulente": (
            consulenti_filtro.count() > 1
        ),
        "precedente_url": _calendar_url(
            vista=vista,
            data=precedente,
            consulente=consulente_id,
            commessa=commessa_id,
            fase=fase_id,
        ),
        "successivo_url": _calendar_url(
            vista=vista,
            data=successivo,
            consulente=consulente_id,
            commessa=commessa_id,
            fase=fase_id,
        ),
        "oggi_url": _calendar_url(
            vista=vista,
            data=oggi,
            consulente=consulente_id,
            commessa=commessa_id,
            fase=fase_id,
        ),
        "mese_url": _calendar_url(
            vista="mese",
            data=riferimento,
            consulente=consulente_id,
            commessa=commessa_id,
            fase=fase_id,
        ),
        "settimana_url": _calendar_url(
            vista="settimana",
            data=riferimento,
            consulente=consulente_id,
            commessa=commessa_id,
            fase=fase_id,
        ),
        "data_riferimento": (
            riferimento.isoformat()
        ),
        "confronto": confronto,
        "confronto_consulenti": confronto_consulenti,
        "confronto_commesse": confronto_commesse,
    }

    return render(
        request,
        "planning/pianificazione_list.html",
        context,
    )


@login_required
def pianificazione_create(request):
    if not can_view_operational_details(request.user):
        raise PermissionDenied("La pianificazione è riservata ai profili operativi.")
    initial = {}

    commessa_id = _safe_uuid(request.GET.get("commessa"))
    fase_id = _safe_uuid(request.GET.get("fase"))

    data_iniziale = request.GET.get(
        "data"
    )

    if data_iniziale:
        try:
            data_iniziale = (
                date.fromisoformat(
                    data_iniziale
                )
            )

            if (
                data_iniziale
                >= timezone.localdate()
            ):
                initial["data"] = (
                    data_iniziale
                )

        except ValueError:
            pass

    if request.method == "POST":
        form = PianificazioneForm(
            request.POST,
            user=request.user,
            commessa_id=commessa_id,
            fase_id=fase_id,
        )

        if form.is_valid():
            try:
                pianificazione = (
                    create_planning(
                        user=request.user,
                        assegnazione=(
                            form.cleaned_data[
                                "assegnazione"
                            ]
                        ),
                        data=(
                            form.cleaned_data[
                                "data"
                            ]
                        ),
                        ore_pianificate=(
                            form.cleaned_data[
                                "ore_pianificate"
                            ]
                        ),
                        tipo_attivita=(
                            form.cleaned_data[
                                "tipo_attivita"
                            ]
                        ),
                    )
                )

            except PermissionDenied as exc:
                form.add_error(
                    None,
                    str(exc),
                )

            except ValidationError as exc:
                _add_validation_errors(
                    form,
                    exc,
                )

            else:
                messages.success(
                    request,
                    (
                        "Pianificazione "
                        "inserita correttamente."
                    ),
                )

                return redirect(
                    _planning_list_url(
                        pianificazione.data
                    )
                )

    else:
        form = PianificazioneForm(
            user=request.user,
            initial=initial,
            commessa_id=commessa_id,
            fase_id=fase_id,
        )

    return render(
        request,
        "planning/pianificazione_form.html",
        {
            "form": form,
            "titolo": "Pianifica ore",
            "is_update": False,
        },
    )


@login_required
def pianificazione_update(
    request,
    pk,
):
    if not can_view_operational_details(request.user):
        raise PermissionDenied("La pianificazione è riservata ai profili operativi.")
    pianificazione = get_object_or_404(
        GiornoPianificato.objects.select_related(
            "assegnazione",
            "assegnazione__consulente",
            "assegnazione__commessa",
            "assegnazione__commessa__cliente",
        ),
        pk=pk,
    )

    if not can_view_planning(
        request.user,
        pianificazione,
    ):
        raise PermissionDenied

    if not can_edit_planning(
        request.user,
        pianificazione,
    ):
        raise PermissionDenied(
            "Non puoi modificare questa pianificazione."
        )

    if request.method == "POST":
        form = PianificazioneForm(
            request.POST,
            user=request.user,
            pianificazione=pianificazione,
        )

        if form.is_valid():
            try:
                pianificazione = (
                    update_planning(
                        user=request.user,
                        pianificazione=(
                            pianificazione
                        ),
                        data=(
                            form.cleaned_data[
                                "data"
                            ]
                        ),
                        ore_pianificate=(
                            form.cleaned_data[
                                "ore_pianificate"
                            ]
                        ),
                        tipo_attivita=(
                            form.cleaned_data[
                                "tipo_attivita"
                            ]
                        ),
                    )
                )

            except PermissionDenied as exc:
                form.add_error(
                    None,
                    str(exc),
                )

            except ValidationError as exc:
                _add_validation_errors(
                    form,
                    exc,
                )

            else:
                messages.success(
                    request,
                    (
                        "Pianificazione "
                        "aggiornata correttamente."
                    ),
                )

                return redirect(
                    _planning_list_url(
                        pianificazione.data
                    )
                )

    else:
        form = PianificazioneForm(
            user=request.user,
            pianificazione=pianificazione,
        )

    return render(
        request,
        "planning/pianificazione_form.html",
        {
            "form": form,
            "pianificazione": pianificazione,
            "titolo": "Modifica pianificazione",
            "is_update": True,
            "congelata": (
                pianificazione.congelata
            ),
        },
    )


@login_required
def pianificazione_delete(
    request,
    pk,
):
    if not can_view_operational_details(request.user):
        raise PermissionDenied("La pianificazione è riservata ai profili operativi.")
    pianificazione = get_object_or_404(
        GiornoPianificato.objects.select_related(
            "assegnazione",
            "assegnazione__consulente",
            "assegnazione__commessa",
            "assegnazione__commessa__cliente",
        ),
        pk=pk,
    )

    if not can_view_planning(
        request.user,
        pianificazione,
    ):
        raise PermissionDenied

    if not can_delete_planning(
        request.user,
        pianificazione,
    ):
        raise PermissionDenied(
            "Non puoi eliminare questa pianificazione."
        )

    if request.method == "POST":
        data_riferimento = (
            pianificazione.data
        )

        try:
            delete_planning(
                user=request.user,
                pianificazione=pianificazione,
            )

        except (
            PermissionDenied,
            ValidationError,
        ) as exc:
            messages.error(
                request,
                str(exc),
            )

        else:
            messages.success(
                request,
                (
                    "Pianificazione "
                    "eliminata correttamente."
                ),
            )

        return redirect(
            _planning_list_url(
                data_riferimento
            )
        )

    return render(
        request,
        (
            "planning/"
            "pianificazione_confirm_delete.html"
        ),
        {
            "pianificazione": pianificazione,
        },
    )

@login_required
def pianificazione_confirm(request, pk):
    """La risorsa conferma che la sessione in agenda è stata svolta."""
    if not can_view_operational_details(request.user):
        raise PermissionDenied("La pianificazione è riservata ai profili operativi.")
    pianificazione = get_object_or_404(
        GiornoPianificato.objects.select_related(
            "assegnazione",
            "assegnazione__consulente",
            "assegnazione__commessa",
            "assegnazione__commessa__cliente",
            "assegnazione__fase",
        ),
        pk=pk,
    )

    if not can_view_planning(request.user, pianificazione):
        raise PermissionDenied

    if request.method != "POST":
        return redirect(_planning_list_url(pianificazione.data))

    data_riferimento = pianificazione.data
    try:
        confirm_planning(user=request.user, pianificazione=pianificazione)
    except (PermissionDenied, ValidationError) as exc:
        messages.error(request, "; ".join(getattr(exc, "messages", [str(exc)])))
    else:
        messages.success(
            request,
            "Sessione conclusa e confermata. Le ore sono state riportate nel timesheet.",
        )

    return redirect(_planning_list_url(data_riferimento))
