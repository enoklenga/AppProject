from datetime import date
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Q, Sum
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils import timezone
from django.views import View
from django.views.generic import FormView, ListView

from apps.accounts.models import User
from apps.accounts.access import (
    can_manage_commessa,
    can_view_finance_ledger,
    commesse_in_scope,
    is_global_manager,
    is_manager,
    persone_in_scope,
)
from apps.common.mixins import (
    FinanceManagementRequiredMixin,
    OperationalRequiredMixin,
    TimesheetReadRequiredMixin,
)
from apps.common.request_security import safe_internal_redirect
from apps.projects.models import Assegnazione
from .forms import ApprovazioneForm, RigaOreForm, SpesaTrasfertaForm
from .models import RigaOre, SpesaTrasferta
from .services import (
    approva_riga_ore,
    approva_spesa,
    elimina_ore,
    elimina_spesa,
    inserisci_ore,
    inserisci_spesa,
    modifica_ore,
    modifica_spesa,
    periodo_chiuso,
    rifiuta_riga_ore,
    rifiuta_spesa,
)


def _mese_richiesto(request) -> tuple[int, int, str]:
    valore = request.GET.get("mese") or request.POST.get("mese")
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


def _applica_validation_error(form, exc: ValidationError) -> None:
    if hasattr(exc, "error_dict"):
        for campo, errori in exc.error_dict.items():
            for errore in errori:
                form.add_error(
                    campo if campo in form.fields else None,
                    errore,
                )
    else:
        for errore in exc.error_list:
            form.add_error(None, errore)


def _perimetro_consuntivi(queryset, user):
    """Righe visibili: proprie + quelle delle commesse gestite."""
    if is_global_manager(user):
        return queryset
    return queryset.filter(
        Q(assegnazione__consulente=user)
        | Q(assegnazione__commessa__in=commesse_in_scope(user))
    )


def _contesto_consuntivi(request, periodo_e_chiuso: bool) -> dict:
    user = request.user
    can_write = bool(is_manager(user) or getattr(user, "is_risorsa_ingaggiabile", False))
    return {
        "can_view_all": can_view_finance_ledger(user),
        "is_admin": is_manager(user),
        "can_write": can_write,
        "can_manage_finance": is_manager(user),
    }


def _marca_righe_modificabili(oggetti, user, can_write: bool, periodo_e_chiuso: bool) -> None:
    """Calcola per ogni riga se l'utente corrente può modificarla/eliminarla."""
    cache: dict = {}
    for oggetto in oggetti:
        commessa = oggetto.assegnazione.commessa
        if commessa.pk not in cache:
            cache[commessa.pk] = can_manage_commessa(user, commessa)
        propria = oggetto.assegnazione.consulente_id == user.id
        supervisione = cache[commessa.pk] and not propria
        oggetto.modificabile = bool(
            can_write
            and not periodo_e_chiuso
            and (supervisione or (propria and not oggetto.bloccata_per_consulente))
        )
        oggetto.approvabile = bool(supervisione and not periodo_e_chiuso)


def _filtri_consuntivi(user) -> dict:
    return {
        "consulenti_filtro": persone_in_scope(user).filter(
            ruolo__in=(User.Ruolo.CONSULENTE, User.Ruolo.RESPONSABILE_CONSULENZA)
        ).order_by("last_name", "first_name", "email"),
        "commesse_filtro": commesse_in_scope(user).order_by("codice"),
    }


class RigaOreListView(TimesheetReadRequiredMixin, ListView):
    model = RigaOre
    template_name = "timesheets/riga_ore_list.html"
    context_object_name = "righe"
    paginate_by = 40

    def get_queryset(self):
        anno, mese, _ = _mese_richiesto(self.request)
        queryset = RigaOre.objects.select_related(
            "assegnazione",
            "assegnazione__consulente",
            "assegnazione__commessa",
            "assegnazione__commessa__cliente",
            "inserita_da",
            "ultima_modifica_da",
        ).filter(data__year=anno, data__month=mese)

        can_view_all = can_view_finance_ledger(self.request.user)
        if not can_view_all:
            queryset = queryset.filter(
                assegnazione__consulente=self.request.user
            )
        else:
            queryset = _perimetro_consuntivi(queryset, self.request.user)
            consulente_id = self.request.GET.get("consulente", "").strip()
            commessa_id = self.request.GET.get("commessa", "").strip()
            if consulente_id:
                queryset = queryset.filter(
                    assegnazione__consulente_id=consulente_id
                )
            if commessa_id:
                queryset = queryset.filter(
                    assegnazione__commessa_id=commessa_id
                )
        return queryset.order_by("-data", "-created_at")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        anno, mese, valore_mese = _mese_richiesto(self.request)
        queryset_non_paginato = self.get_queryset()
        context.update(
            {
                "mese_selezionato": valore_mese,
                "periodo_chiuso": periodo_chiuso(date(anno, mese, 1)),
                "totale_ore": (
                    queryset_non_paginato.aggregate(t=Sum("ore"))["t"] or 0
                ),
            }
        )
        context.update(_contesto_consuntivi(self.request, context["periodo_chiuso"]))
        context["mostra_azioni"] = bool(
            context["can_write"] and not context["periodo_chiuso"]
        )
        _marca_righe_modificabili(
            context["object_list"],
            self.request.user,
            context["can_write"],
            context["periodo_chiuso"],
        )
        if context["can_view_all"]:
            context.update(_filtri_consuntivi(self.request.user))
        return context


class RigaOreCreateView(OperationalRequiredMixin, FormView):
    form_class = RigaOreForm
    template_name = "timesheets/riga_ore_form.html"

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["attore"] = self.request.user
        return kwargs

    def get_initial(self):
        initial = super().get_initial()
        initial["data"] = timezone.localdate()
        assegnazione = self.request.GET.get("assegnazione")
        if assegnazione:
            initial["assegnazione"] = assegnazione
        return initial

    def form_valid(self, form):
        dati = form.cleaned_data
        try:
            esito = inserisci_ore(
                attore=self.request.user,
                assegnazione_id=dati["assegnazione"].id,
                giorno=dati["data"],
                tipo_attivita=dati["tipo_attivita"],
                ore=dati["ore"],
                nota=dati["nota"],
                motivazione=dati.get("motivazione", ""),
            )
        except (ValidationError, PermissionDenied) as exc:
            if isinstance(exc, PermissionDenied):
                form.add_error(None, str(exc))
            else:
                _applica_validation_error(form, exc)
            return self.form_invalid(form)

        messages.success(self.request, "Ore registrate correttamente.")
        if esito.monte_ore_superato:
            messages.warning(
                self.request,
                "Attenzione: il monte ore previsto dell'assegnazione è stato superato.",
            )
        if esito.limite_giornaliero_superato:
            messages.warning(
                self.request,
                "Eccezione autorizzata: il totale giornaliero supera 8 ore.",
            )
        return HttpResponseRedirect(
            f"{reverse('timesheets:ore-list')}?mese={dati['data']:%Y-%m}"
        )


class RigaOreUpdateView(OperationalRequiredMixin, View):
    template_name = "timesheets/riga_ore_form.html"

    def get_object(self):
        riga = get_object_or_404(
            RigaOre.objects.select_related(
                "assegnazione",
                "assegnazione__consulente",
                "assegnazione__commessa",
                "assegnazione__fase",
            ),
            pk=self.kwargs["pk"],
        )
        if (
            riga.assegnazione.consulente_id != self.request.user.id
            and not can_manage_commessa(self.request.user, riga.assegnazione.commessa)
        ):
            raise PermissionDenied
        return riga

    def get(self, request, *args, **kwargs):
        riga = self.get_object()
        form = RigaOreForm(instance=riga, attore=request.user)
        return render(
            request,
            self.template_name,
            {"form": form, "object": riga},
        )

    def post(self, request, *args, **kwargs):
        riga = self.get_object()
        form = RigaOreForm(
            request.POST,
            instance=riga,
            attore=request.user,
        )
        if form.is_valid():
            dati = form.cleaned_data
            try:
                esito = modifica_ore(
                    attore=request.user,
                    riga_id=riga.id,
                    versione=dati["versione"],
                    assegnazione_id=dati["assegnazione"].id,
                    giorno=dati["data"],
                    tipo_attivita=dati["tipo_attivita"],
                    ore=dati["ore"],
                    nota=dati["nota"],
                    motivazione=dati.get("motivazione", ""),
                )
            except (ValidationError, PermissionDenied) as exc:
                if isinstance(exc, PermissionDenied):
                    form.add_error(None, str(exc))
                else:
                    _applica_validation_error(form, exc)
            else:
                messages.success(request, "Riga ore aggiornata.")
                if esito.monte_ore_superato:
                    messages.warning(
                        request,
                        "Il monte ore previsto dell'assegnazione è stato superato.",
                    )
                if esito.limite_giornaliero_superato:
                    messages.warning(
                        request,
                        "Eccezione autorizzata: il totale giornaliero supera 8 ore.",
                    )
                return HttpResponseRedirect(
                    f"{reverse('timesheets:ore-list')}?mese={dati['data']:%Y-%m}"
                )
        return render(
            request,
            self.template_name,
            {"form": form, "object": riga},
        )


class RigaOreDeleteView(OperationalRequiredMixin, View):
    def post(self, request, pk):
        riga = get_object_or_404(RigaOre, pk=pk)
        mese = f"{riga.data:%Y-%m}"
        try:
            versione = int(request.POST.get("versione", "0"))
            elimina_ore(
                attore=request.user,
                riga_id=riga.id,
                versione=versione,
                motivazione=request.POST.get("motivazione", ""),
            )
        except (ValueError, ValidationError, PermissionDenied) as exc:
            messages.error(request, str(exc))
        else:
            messages.success(request, "Riga ore eliminata.")
        return HttpResponseRedirect(
            f"{reverse('timesheets:ore-list')}?mese={mese}"
        )


class SpesaListView(TimesheetReadRequiredMixin, ListView):
    model = SpesaTrasferta
    template_name = "timesheets/spesa_list.html"
    context_object_name = "spese"
    paginate_by = 40

    def get_queryset(self):
        anno, mese, _ = _mese_richiesto(self.request)
        queryset = SpesaTrasferta.objects.select_related(
            "assegnazione",
            "assegnazione__consulente",
            "assegnazione__commessa",
            "assegnazione__commessa__cliente",
        ).filter(data__year=anno, data__month=mese)

        can_view_all = can_view_finance_ledger(self.request.user)
        if not can_view_all:
            queryset = queryset.filter(
                assegnazione__consulente=self.request.user
            )
        else:
            queryset = _perimetro_consuntivi(queryset, self.request.user)
            consulente_id = self.request.GET.get("consulente", "").strip()
            commessa_id = self.request.GET.get("commessa", "").strip()
            if consulente_id:
                queryset = queryset.filter(
                    assegnazione__consulente_id=consulente_id
                )
            if commessa_id:
                queryset = queryset.filter(
                    assegnazione__commessa_id=commessa_id
                )
        return queryset.order_by("-data", "-created_at")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        anno, mese, valore_mese = _mese_richiesto(self.request)
        queryset_non_paginato = self.get_queryset()
        context.update(
            {
                "mese_selezionato": valore_mese,
                "periodo_chiuso": periodo_chiuso(date(anno, mese, 1)),
                "totale_spese": (
                    queryset_non_paginato.aggregate(t=Sum("importo"))["t"]
                    or Decimal("0.00")
                ),
            }
        )
        context.update(_contesto_consuntivi(self.request, context["periodo_chiuso"]))
        context["mostra_azioni"] = bool(
            context["can_write"] and not context["periodo_chiuso"]
        )
        _marca_righe_modificabili(
            context["object_list"],
            self.request.user,
            context["can_write"],
            context["periodo_chiuso"],
        )
        if context["can_view_all"]:
            context.update(_filtri_consuntivi(self.request.user))
        return context


class SpesaCreateView(OperationalRequiredMixin, FormView):
    form_class = SpesaTrasfertaForm
    template_name = "timesheets/spesa_form.html"

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["attore"] = self.request.user
        return kwargs

    def get_initial(self):
        initial = super().get_initial()
        initial["data"] = timezone.localdate()
        assegnazione = self.request.GET.get("assegnazione")
        if assegnazione:
            initial["assegnazione"] = assegnazione
        return initial

    def form_valid(self, form):
        dati = form.cleaned_data
        try:
            inserisci_spesa(
                attore=self.request.user,
                assegnazione_id=dati["assegnazione"].id,
                giorno=dati["data"],
                categoria=dati["categoria"],
                importo=dati["importo"],
                nota=dati["nota"],
            )
        except (ValidationError, PermissionDenied) as exc:
            if isinstance(exc, PermissionDenied):
                form.add_error(None, str(exc))
            else:
                _applica_validation_error(form, exc)
            return self.form_invalid(form)

        messages.success(self.request, "Spesa registrata correttamente.")
        return HttpResponseRedirect(
            f"{reverse('timesheets:spesa-list')}?mese={dati['data']:%Y-%m}"
        )


class SpesaUpdateView(OperationalRequiredMixin, View):
    template_name = "timesheets/spesa_form.html"

    def get_object(self):
        spesa = get_object_or_404(
            SpesaTrasferta.objects.select_related(
                "assegnazione",
                "assegnazione__consulente",
                "assegnazione__commessa",
                "assegnazione__fase",
            ),
            pk=self.kwargs["pk"],
        )
        if (
            spesa.assegnazione.consulente_id != self.request.user.id
            and not can_manage_commessa(self.request.user, spesa.assegnazione.commessa)
        ):
            raise PermissionDenied
        return spesa

    def get(self, request, *args, **kwargs):
        spesa = self.get_object()
        form = SpesaTrasfertaForm(instance=spesa, attore=request.user)
        return render(
            request,
            self.template_name,
            {"form": form, "object": spesa},
        )

    def post(self, request, *args, **kwargs):
        spesa = self.get_object()
        form = SpesaTrasfertaForm(
            request.POST,
            instance=spesa,
            attore=request.user,
        )
        if form.is_valid():
            dati = form.cleaned_data
            try:
                modifica_spesa(
                    attore=request.user,
                    spesa_id=spesa.id,
                    versione=dati["versione"],
                    assegnazione_id=dati["assegnazione"].id,
                    giorno=dati["data"],
                    categoria=dati["categoria"],
                    importo=dati["importo"],
                    nota=dati["nota"],
                    motivazione=request.POST.get("motivazione", ""),
                )
            except (ValidationError, PermissionDenied) as exc:
                if isinstance(exc, PermissionDenied):
                    form.add_error(None, str(exc))
                else:
                    _applica_validation_error(form, exc)
            else:
                messages.success(request, "Spesa aggiornata.")
                return HttpResponseRedirect(
                    f"{reverse('timesheets:spesa-list')}?mese={dati['data']:%Y-%m}"
                )
        return render(
            request,
            self.template_name,
            {"form": form, "object": spesa},
        )


class SpesaDeleteView(OperationalRequiredMixin, View):
    def post(self, request, pk):
        spesa = get_object_or_404(SpesaTrasferta, pk=pk)
        mese = f"{spesa.data:%Y-%m}"
        try:
            versione = int(request.POST.get("versione", "0"))
            elimina_spesa(
                attore=request.user,
                spesa_id=spesa.id,
                versione=versione,
                motivazione=request.POST.get("motivazione", ""),
            )
        except (ValueError, ValidationError, PermissionDenied) as exc:
            messages.error(request, str(exc))
        else:
            messages.success(request, "Spesa eliminata.")
        return HttpResponseRedirect(
            f"{reverse('timesheets:spesa-list')}?mese={mese}"
        )


class _ApprovazioneBaseView(FinanceManagementRequiredMixin, View):
    """Base per le 4 viste di approvazione/rifiuto (ore e spese), usate
    dalla pagina di chiusura periodo (solo Admin)."""

    def _redirect(self, request, oggetto):
        next_url = safe_internal_redirect(
            request,
            request.POST.get("next"),
        )
        if next_url:
            return HttpResponseRedirect(next_url)
        return HttpResponseRedirect(
            f"{reverse('operations:periodo-detail')}"
            f"?mese={oggetto.data:%Y-%m}"
        )


class RigaOreApprovaView(_ApprovazioneBaseView):
    def post(self, request, pk):
        riga = get_object_or_404(RigaOre, pk=pk)
        form = ApprovazioneForm(request.POST)
        try:
            if form.is_valid():
                approva_riga_ore(
                    attore=request.user,
                    riga_id=riga.id,
                    motivazione=form.cleaned_data["motivazione"],
                )
                messages.success(request, "Riga ore approvata.")
        except (ValidationError, PermissionDenied) as exc:
            messages.error(request, str(exc))
        return self._redirect(request, riga)


class RigaOreRifiutaView(_ApprovazioneBaseView):
    def post(self, request, pk):
        riga = get_object_or_404(RigaOre, pk=pk)
        form = ApprovazioneForm(request.POST)
        try:
            if form.is_valid():
                rifiuta_riga_ore(
                    attore=request.user,
                    riga_id=riga.id,
                    motivazione=form.cleaned_data["motivazione"],
                )
                messages.success(
                    request,
                    "Riga ore rifiutata: torna modificabile dal consulente.",
                )
        except (ValidationError, PermissionDenied) as exc:
            messages.error(request, str(exc))
        return self._redirect(request, riga)


class SpesaApprovaView(_ApprovazioneBaseView):
    def post(self, request, pk):
        spesa = get_object_or_404(SpesaTrasferta, pk=pk)
        form = ApprovazioneForm(request.POST)
        try:
            if form.is_valid():
                approva_spesa(
                    attore=request.user,
                    spesa_id=spesa.id,
                    motivazione=form.cleaned_data["motivazione"],
                )
                messages.success(request, "Spesa approvata.")
        except (ValidationError, PermissionDenied) as exc:
            messages.error(request, str(exc))
        return self._redirect(request, spesa)


class SpesaRifiutaView(_ApprovazioneBaseView):
    def post(self, request, pk):
        spesa = get_object_or_404(SpesaTrasferta, pk=pk)
        form = ApprovazioneForm(request.POST)
        try:
            if form.is_valid():
                rifiuta_spesa(
                    attore=request.user,
                    spesa_id=spesa.id,
                    motivazione=form.cleaned_data["motivazione"],
                )
                messages.success(
                    request,
                    "Spesa rifiutata: torna modificabile dal consulente.",
                )
        except (ValidationError, PermissionDenied) as exc:
            messages.error(request, str(exc))
        return self._redirect(request, spesa)
