from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q, Sum
from django.shortcuts import render
from django.utils import timezone

from apps.accounts.access import (
    is_global_manager,
    is_platform_admin,
    managed_business_unit_ids,
    managed_business_units,
)
from apps.accounts.business_units import (
    carichi_membri,
    commesse_business_unit,
    indicatori_business_unit,
    schede_business_unit,
)
from apps.accounts.models import BusinessUnit, User
from apps.operations.dashboard_visuals import dashboard_consulente
from apps.operations.models import PeriodoMensile
from apps.operations.services.periodi import valorizza_periodo
from apps.planning.models import GiornoPianificato
from apps.projects.models import Assegnazione, Cliente, Commessa
from apps.timesheets.models import RigaOre


def _mese_richiesto(request) -> tuple[int, int, str]:
    valore = request.GET.get("mese")
    if valore:
        try:
            anno_str, mese_str = valore.split("-", 1)
            anno = int(anno_str)
            mese = int(mese_str)
            if 1 <= mese <= 12:
                return anno, mese, f"{anno:04d}-{mese:02d}"
        except (TypeError, ValueError):
            pass

    oggi = timezone.localdate()
    return oggi.year, oggi.month, f"{oggi.year:04d}-{oggi.month:02d}"


def _controllo_mese(anno: int, mese: int, business_unit_ids=None) -> dict:
    riepilogo = valorizza_periodo(anno, mese, business_unit_ids=business_unit_ids)
    periodo = PeriodoMensile.objects.filter(anno=anno, mese=mese).first()
    periodo_chiuso = bool(periodo and periodo.stato == PeriodoMensile.Stato.CHIUSO)
    return {
        "riepilogo": riepilogo,
        "periodo": periodo,
        "periodo_chiuso": periodo_chiuso,
        "periodo_stato": periodo.get_stato_display() if periodo else "Aperto",
        "da_approvare": (
            riepilogo.approvazione_ore.da_approvare
            + riepilogo.approvazione_spese.da_approvare
        ),
        "rifiutate": (
            riepilogo.approvazione_ore.rifiutate
            + riepilogo.approvazione_spese.rifiutate
        ),
        "senza_tariffa": len(riepilogo.righe_senza_tariffa),
    }


def _home_gestione(request):
    """Home di Admin e Amministrazione: stessa interfaccia di gestione.

    L'Admin vede in più la sezione Piattaforma (account e ruoli).
    """
    anno, mese, valore_mese = _mese_richiesto(request)
    business_units = list(BusinessUnit.objects.filter(attiva=True).order_by("nome"))
    context = {
        "is_platform_admin": is_platform_admin(request.user),
        "mese_selezionato": valore_mese,
        "consulenti_attivi": User.objects.filter(
            ruolo__in=(User.Ruolo.CONSULENTE, User.Ruolo.RESPONSABILE_CONSULENZA),
            is_active=True,
        ).count(),
        "clienti_attivi": Cliente.objects.filter(attivo=True).count(),
        "commesse_aperte": Commessa.objects.filter(
            stato=Commessa.Stato.APERTA,
        ).count(),
        "commesse_senza_bu": Commessa.objects.filter(
            stato=Commessa.Stato.APERTA,
            business_unit__isnull=True,
        ).count(),
        "assegnazioni_attive": Assegnazione.objects.filter(
            stato=Assegnazione.Stato.ATTIVA,
        ).count(),
        "schede_bu": schede_business_unit(business_units, anno, mese),
        "ultime_commesse": (
            Commessa.objects.select_related("cliente", "business_unit")
            .annotate(
                numero_assegnazioni=Count(
                    "assegnazioni",
                    filter=Q(assegnazioni__stato=Assegnazione.Stato.ATTIVA),
                ),
                ore_assegnate=Sum(
                    "assegnazioni__ore_previste",
                    filter=Q(assegnazioni__stato=Assegnazione.Stato.ATTIVA),
                ),
            )
            .order_by("-created_at")[:8]
        ),
    }
    context.update(_controllo_mese(anno, mese))
    return render(request, "common/home_admin.html", context)


def _home_responsabile_bu(request):
    """Home del Responsabile BU: interfaccia di gestione sulla propria BU."""
    anno, mese, valore_mese = _mese_richiesto(request)
    ids = managed_business_unit_ids(request.user)
    business_units = list(managed_business_units(request.user).order_by("nome"))
    context = {
        "mese_selezionato": valore_mese,
        "business_units": business_units,
        "schede_bu": schede_business_unit(business_units, anno, mese) if len(business_units) > 1 else [],
        "indicatori": indicatori_business_unit(ids, anno, mese),
        "carichi": carichi_membri(ids, anno, mese, deduplica_utenti=True)[:20],
        "commesse": list(commesse_business_unit(ids, solo_aperte=True)[:8]),
        "mie_assegnazioni": Assegnazione.objects.filter(
            consulente=request.user,
            stato=Assegnazione.Stato.ATTIVA,
        ).count(),
    }
    context.update(_controllo_mese(anno, mese, business_unit_ids=ids))
    return render(request, "common/home_responsabile.html", context)


@login_required
def home(request):
    user = request.user
    if is_global_manager(user):
        return _home_gestione(request)

    if getattr(request.user, "is_commerciale", False):
        context = {
            "clienti_attivi": Cliente.objects.filter(attivo=True).count(),
            "commesse_aperte": Commessa.objects.filter(
                stato=Commessa.Stato.APERTA,
            ).count(),
            "handover_da_completare": Commessa.objects.filter(
                stato=Commessa.Stato.APERTA,
                handover_completato=False,
            ).count(),
            "ultime_commesse": (
                Commessa.objects.select_related("cliente")
                .order_by("-created_at")[:8]
            ),
        }
        return render(request, "common/home_commerciale.html", context)

    if getattr(request.user, "is_direzione_generale", False):
        anno, mese, valore_mese = _mese_richiesto(request)
        context = {
            "consulenti_attivi": User.objects.filter(
                ruolo__in=(
                    User.Ruolo.CONSULENTE,
                    User.Ruolo.RESPONSABILE_CONSULENZA,
                ),
                is_active=True,
            ).count(),
            "clienti_attivi": Cliente.objects.filter(attivo=True).count(),
            "commesse_aperte": Commessa.objects.filter(
                stato=Commessa.Stato.APERTA,
            ).count(),
            "ore_budget_aperte": (
                Commessa.objects.filter(stato=Commessa.Stato.APERTA)
                .aggregate(totale=Sum("ore_budget"))["totale"]
                or 0
            ),
            "ore_pianificate_mese": (
                GiornoPianificato.objects.filter(
                    data__year=anno,
                    data__month=mese,
                ).aggregate(t=Sum("ore_pianificate"))["t"]
                or 0
            ),
            "ore_consuntivate_mese": (
                RigaOre.objects.filter(
                    data__year=anno,
                    data__month=mese,
                ).aggregate(t=Sum("ore"))["t"]
                or 0
            ),
            "mese_selezionato": valore_mese,
            "ultime_commesse": (
                Commessa.objects.select_related("cliente")
                .order_by("-created_at")[:8]
            ),
        }
        return render(request, "common/home_direzione.html", context)

    if managed_business_unit_ids(user):
        return _home_responsabile_bu(request)

    anno, mese, valore_mese = _mese_richiesto(request)
    dashboard = dashboard_consulente(
        utente=request.user,
        anno=anno,
        mese=mese,
    )
    return render(
        request,
        "common/home_consulente.html",
        {
            # Responsabile BU senza BU assegnata: interfaccia da consulente
            # con un avviso (la nomina avviene in Business Unit > Appartenenze).
            "responsabile_senza_bu": bool(getattr(user, "is_responsabile_business_unit", False)),
            "dashboard": dashboard,
            "assegnazioni": [
                voce["assegnazione"]
                for voce in dashboard["assegnazioni_attive"]
            ],
            "mese_selezionato": valore_mese,
        },
    )
