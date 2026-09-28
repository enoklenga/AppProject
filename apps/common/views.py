from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q, Sum
from django.shortcuts import render
from django.utils import timezone

from apps.accounts.models import User
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


@login_required
def home(request):
    if getattr(request.user, "is_admin_lef", False):
        context = {
            "consulenti_attivi": User.objects.filter(
                ruolo__in=(User.Ruolo.CONSULENTE, User.Ruolo.RESPONSABILE_CONSULENZA),
                is_active=True,
            ).count(),
            "clienti_attivi": Cliente.objects.filter(attivo=True).count(),
            "commesse_aperte": Commessa.objects.filter(
                stato=Commessa.Stato.APERTA,
            ).count(),
            "assegnazioni_attive": Assegnazione.objects.filter(
                stato=Assegnazione.Stato.ATTIVA,
            ).count(),
            "ultime_commesse": (
                Commessa.objects.select_related("cliente")
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
        return render(request, "common/home_admin.html", context)

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

    if getattr(request.user, "is_amministrazione", False):
        anno, mese, valore_mese = _mese_richiesto(request)
        riepilogo = valorizza_periodo(anno, mese)
        periodo = PeriodoMensile.objects.filter(anno=anno, mese=mese).first()
        context = {
            "mese_selezionato": valore_mese,
            "riepilogo": riepilogo,
            "periodo": periodo,
            "periodo_chiuso": bool(
                periodo and periodo.stato == PeriodoMensile.Stato.CHIUSO
            ),
            "da_approvare": (
                riepilogo.approvazione_ore.da_approvare
                + riepilogo.approvazione_spese.da_approvare
                + riepilogo.approvazione_ore.rifiutate
                + riepilogo.approvazione_spese.rifiutate
            ),
            "senza_tariffa": len(riepilogo.righe_senza_tariffa),
        }
        return render(request, "common/home_amministrazione.html", context)

    if getattr(request.user, "is_responsabile_consulenza", False):
        anno, mese, valore_mese = _mese_richiesto(request)
        risorse = list(
            User.objects.filter(
                ruolo__in=(
                    User.Ruolo.CONSULENTE,
                    User.Ruolo.RESPONSABILE_CONSULENZA,
                ),
                is_active=True,
            ).order_by("last_name", "first_name", "email")
        )
        carichi = []
        for risorsa in risorse:
            ore_pianificate = (
                GiornoPianificato.objects.filter(
                    assegnazione__consulente=risorsa,
                    data__year=anno,
                    data__month=mese,
                ).aggregate(t=Sum("ore_pianificate"))["t"]
                or 0
            )
            ore_consuntivate = (
                RigaOre.objects.filter(
                    assegnazione__consulente=risorsa,
                    data__year=anno,
                    data__month=mese,
                ).aggregate(t=Sum("ore"))["t"]
                or 0
            )
            carichi.append(
                {
                    "risorsa": risorsa,
                    "ore_pianificate": ore_pianificate,
                    "ore_consuntivate": ore_consuntivate,
                    "assegnazioni_attive": Assegnazione.objects.filter(
                        consulente=risorsa,
                        stato=Assegnazione.Stato.ATTIVA,
                    ).count(),
                }
            )

        context = {
            "mese_selezionato": valore_mese,
            "risorse_attive": len(risorse),
            "assegnazioni_attive": Assegnazione.objects.filter(
                consulente__ruolo__in=(
                    User.Ruolo.CONSULENTE,
                    User.Ruolo.RESPONSABILE_CONSULENZA,
                ),
                stato=Assegnazione.Stato.ATTIVA,
            ).count(),
            "commesse_presidiate": Commessa.objects.filter(
                assegnazioni__stato=Assegnazione.Stato.ATTIVA,
                assegnazioni__consulente__ruolo__in=(
                    User.Ruolo.CONSULENTE,
                    User.Ruolo.RESPONSABILE_CONSULENZA,
                ),
            ).distinct().count(),
            "ore_pianificate": (
                GiornoPianificato.objects.filter(
                    data__year=anno,
                    data__month=mese,
                ).aggregate(t=Sum("ore_pianificate"))["t"]
                or 0
            ),
            "ore_consuntivate": (
                RigaOre.objects.filter(
                    data__year=anno,
                    data__month=mese,
                ).aggregate(t=Sum("ore"))["t"]
                or 0
            ),
            "carichi": carichi[:20],
        }
        return render(request, "common/home_responsabile.html", context)

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
            "dashboard": dashboard,
            "assegnazioni": [
                voce["assegnazione"]
                for voce in dashboard["assegnazioni_attive"]
            ],
            "mese_selezionato": valore_mese,
        },
    )
