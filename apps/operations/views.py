from datetime import date

from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import Http404
from django.http import HttpResponse, HttpResponseRedirect
from django.core.paginator import Paginator
import csv
import json
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils import timezone
from django.views import View
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Q
from django.conf import settings

from apps.common.export_security import spreadsheet_safe_row
from apps.accounts.access import (
    business_units_in_scope,
    can_close_periods,
    can_manage_finance,
    perimetro_business_unit,
)
from apps.accounts.models import BusinessUnit, User
from apps.common.mixins import (
    BackofficeControlRequiredMixin,
    AuditReadRequiredMixin,
    ExecutiveDashboardRequiredMixin,
    FinanceManagementRequiredMixin,
)
from apps.projects.models import Cliente, Commessa
from .forms import (
    ChiusuraPeriodoForm,
    ConfigurazionePromemoriaForm,
    InvioManualePromemoriaForm,
    ImportazioneFileForm,
    AuditLogFilterForm,
    RiaperturaPeriodoForm,
)
from .models import (
    AuditLog,
    Importazione,
    InvioPromemoria,
    PeriodoMensile,
)
from .dashboard_visuals import admin_visuals, pm_visuals
from .services import (
    chiudi_periodo,
    riapri_periodo,
    valorizza_periodo,
    commesse_gestite_da_pm,
    dashboard_admin,
    dashboard_pm,
    consulenti_senza_ore,
    inizializza_configurazione_promemoria,
    invia_email_test,
    invia_promemoria,
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


class PeriodoDetailView(FinanceManagementRequiredMixin, View):
    template_name = "operations/periodo_detail.html"

    def get(self, request):
        anno, mese, valore_mese = _mese_richiesto(request)
        return self._render(
            request,
            anno=anno,
            mese=mese,
            valore_mese=valore_mese,
        )

    def post(self, request):
        anno, mese, valore_mese = _mese_richiesto(request)
        azione = request.POST.get("azione")

        if azione == "chiudi":
            form_chiusura = ChiusuraPeriodoForm(request.POST)
            form_riapertura = RiaperturaPeriodoForm()
            if form_chiusura.is_valid():
                try:
                    chiudi_periodo(
                        attore=request.user,
                        anno=anno,
                        mese=mese,
                        forza_tariffe_mancanti=form_chiusura.cleaned_data[
                            "forza_tariffe_mancanti"
                        ],
                        forza_approvazioni_mancanti=form_chiusura.cleaned_data[
                            "forza_approvazioni_mancanti"
                        ],
                        motivazione=form_chiusura.cleaned_data["motivazione"],
                    )
                except (ValidationError, PermissionDenied) as exc:
                    form_chiusura.add_error(None, str(exc))
                else:
                    messages.success(
                        request,
                        f"Periodo {mese:02d}/{anno} chiuso correttamente.",
                    )
                    return HttpResponseRedirect(
                        f"{reverse('operations:periodo-detail')}"
                        f"?mese={valore_mese}"
                    )
        elif azione == "riapri":
            form_chiusura = ChiusuraPeriodoForm()
            form_riapertura = RiaperturaPeriodoForm(request.POST)
            if form_riapertura.is_valid():
                try:
                    riapri_periodo(
                        attore=request.user,
                        anno=anno,
                        mese=mese,
                        motivazione=form_riapertura.cleaned_data[
                            "motivazione"
                        ],
                    )
                except (ValidationError, PermissionDenied) as exc:
                    form_riapertura.add_error(None, str(exc))
                else:
                    messages.success(
                        request,
                        f"Periodo {mese:02d}/{anno} riaperto correttamente.",
                    )
                    return HttpResponseRedirect(
                        f"{reverse('operations:periodo-detail')}"
                        f"?mese={valore_mese}"
                    )
        else:
            form_chiusura = ChiusuraPeriodoForm()
            form_riapertura = RiaperturaPeriodoForm()
            messages.error(request, "Azione non riconosciuta.")

        return self._render(
            request,
            anno=anno,
            mese=mese,
            valore_mese=valore_mese,
            form_chiusura=form_chiusura,
            form_riapertura=form_riapertura,
        )

    def _render(
        self,
        request,
        *,
        anno: int,
        mese: int,
        valore_mese: str,
        form_chiusura=None,
        form_riapertura=None,
    ):
        user = request.user
        bu_richiesta = request.GET.get("bu") or request.POST.get("bu") or None
        perimetro = perimetro_business_unit(user, bu_richiesta)
        riepilogo = valorizza_periodo(anno, mese, business_unit_ids=perimetro)
        periodo = PeriodoMensile.objects.filter(
            anno=anno,
            mese=mese,
        ).first()
        stato_chiuso = bool(
            periodo
            and periodo.stato == PeriodoMensile.Stato.CHIUSO
        )

        context = {
            "anno": anno,
            "mese": mese,
            "mese_data": date(anno, mese, 1),
            "mese_selezionato": valore_mese,
            "riepilogo": riepilogo,
            "periodo": periodo,
            "stato_chiuso": stato_chiuso,
            "form_chiusura": (
                form_chiusura or ChiusuraPeriodoForm()
            ),
            "form_riapertura": (
                form_riapertura or RiaperturaPeriodoForm()
            ),
            "puo_chiudere": can_close_periods(user),
            "business_units_filtro": business_units_in_scope(user).filter(attiva=True).order_by("nome"),
            "bu_selezionata": str(perimetro[0]) if perimetro and len(perimetro) == 1 and bu_richiesta else "",
            "perimetro_nomi": (
                list(BusinessUnit.objects.filter(pk__in=perimetro).order_by("nome").values_list("nome", flat=True))
                if perimetro is not None else []
            ),
        }
        return render(request, self.template_name, context)



class DashboardAdminView(ExecutiveDashboardRequiredMixin, View):
    template_name = "operations/dashboard_admin.html"

    def get(self, request):
        anno, mese, valore_mese = _mese_richiesto(request)

        cliente_id = request.GET.get("cliente", "").strip() or None
        commessa_id = request.GET.get("commessa", "").strip() or None
        consulente_id = (request.GET.get("consulente", "").strip() or None)
        fase_id = (request.GET.get("fase", "").strip() or None)
        bu_richiesta = request.GET.get("bu", "").strip() or None
        perimetro = perimetro_business_unit(request.user, bu_richiesta)

        dati = dashboard_admin(
            business_unit_ids=perimetro,
            anno=anno,
            mese=mese,
            cliente_id=cliente_id,
            commessa_id=commessa_id,
            consulente_id=consulente_id,
            fase_id=fase_id,
        )

        visuals = admin_visuals(
            business_unit_ids=perimetro,
            dashboard=dati,
            anno=anno,
            mese=mese,
            cliente_id=cliente_id,
            commessa_id=commessa_id,
            consulente_id=consulente_id,
            fase_id=fase_id,
        )

        from apps.phases.models import FaseCommessa

        commesse_perimetro = Commessa.objects.all()
        if perimetro is not None:
            commesse_perimetro = commesse_perimetro.filter(business_unit_id__in=perimetro)
        fasi_filtro = FaseCommessa.objects.filter(
            commessa__in=commesse_perimetro
        ).select_related("commessa").order_by("commessa__codice", "ordine", "nome")
        consulenti_filtro = User.objects.filter(
            ruolo__in=(User.Ruolo.CONSULENTE, User.Ruolo.RESPONSABILE_CONSULENZA)
        )
        if perimetro is not None:
            consulenti_filtro = consulenti_filtro.filter(
                assegnazioni__commessa__in=commesse_perimetro
            ).distinct()

        context = {
            "dashboard": dati,
            "visuals": visuals,
            "puo_gestire_controllo": can_manage_finance(request.user),
            "mese_selezionato": valore_mese,
            "clienti_filtro": Cliente.objects.order_by(
                "ragione_sociale"
            ),
            "commesse_filtro": commesse_perimetro.select_related(
                "cliente"
            ).order_by("codice"),
            "consulenti_filtro": consulenti_filtro.order_by("last_name", "first_name", "email"),
            "fasi_filtro": fasi_filtro,
            "fase_selezionata": fase_id,
            "business_units_filtro": business_units_in_scope(request.user).filter(attiva=True).order_by("nome"),
            "bu_selezionata": bu_richiesta or "",
            "perimetro_nomi": (
                list(BusinessUnit.objects.filter(pk__in=perimetro).order_by("nome").values_list("nome", flat=True))
                if perimetro is not None else []
            ),
        }
        return render(request, self.template_name, context)


class DashboardPMView(LoginRequiredMixin, View):
    template_name = "operations/dashboard_pm.html"

    def get(self, request):
        anno, mese, valore_mese = _mese_richiesto(request)
        commesse = list(commesse_gestite_da_pm(request.user))

        commessa_id = request.GET.get("commessa", "").strip()
        if not commessa_id and commesse:
            commessa_id = str(commesse[0].id)

        dati = None
        if commessa_id:
            dati = dashboard_pm(
                utente=request.user,
                commessa_id=commessa_id,
                anno=anno,
                mese=mese,
            )

        visuals = pm_visuals(dashboard=dati) if dati is not None else None

        return render(
            request,
            self.template_name,
            {
                "dashboard": dati,
                "visuals": visuals,
                "commesse_pm": commesse,
                "mese_selezionato": valore_mese,
                "commessa_selezionata": commessa_id,
            },
        )



class PromemoriaView(BackofficeControlRequiredMixin, View):
    template_name = "operations/promemoria.html"

    def get(self, request):
        anno, mese, valore_mese = _mese_richiesto(request)
        configurazione = inizializza_configurazione_promemoria(
            attore=request.user
        )
        return self._render(
            request,
            configurazione=configurazione,
            anno=anno,
            mese=mese,
            valore_mese=valore_mese,
        )

    def post(self, request):
        anno, mese, valore_mese = _mese_richiesto(request)
        configurazione = inizializza_configurazione_promemoria(
            attore=request.user
        )
        azione = request.POST.get("azione")

        form_configurazione = ConfigurazionePromemoriaForm(
            instance=configurazione
        )
        form_invio = InvioManualePromemoriaForm(
            initial={"mese": f"{anno:04d}-{mese:02d}"}
        )

        if azione == "salva_configurazione":
            form_configurazione = ConfigurazionePromemoriaForm(
                request.POST,
                instance=configurazione,
            )
            if form_configurazione.is_valid():
                configurazione = form_configurazione.save(commit=False)
                configurazione.aggiornata_da = request.user
                configurazione.save()
                messages.success(
                    request,
                    "Configurazione dei promemoria aggiornata.",
                )
                return HttpResponseRedirect(
                    f"{reverse('operations:promemoria')}"
                    f"?mese={valore_mese}"
                )

        elif azione == "invia":
            form_invio = InvioManualePromemoriaForm(request.POST)
            if form_invio.is_valid():
                giorno = form_invio.cleaned_data["mese"]
                anno = giorno.year
                mese = giorno.month
                valore_mese = f"{anno:04d}-{mese:02d}"

                esito = invia_promemoria(
                    configurazione=configurazione,
                    anno=anno,
                    mese=mese,
                    forza=True,
                )
                if esito.motivo_salto:
                    messages.warning(request, esito.motivo_salto)
                else:
                    messages.success(
                        request,
                        (
                            f"Invio completato: {esito.inviati} inviati, "
                            f"{esito.saltati} già presenti, "
                            f"{esito.errori} errori."
                        ),
                    )
                return HttpResponseRedirect(
                    f"{reverse('operations:promemoria')}"
                    f"?mese={valore_mese}"
                )

        elif azione == "test_email":
            try:
                risultato = invia_email_test(
                    destinatario=request.user
                )
                if risultato != 1:
                    raise RuntimeError(
                        "Il backend non ha confermato l'invio."
                    )
            except Exception as exc:
                messages.error(
                    request,
                    f"Test email non riuscito: {exc}",
                )
            else:
                messages.success(
                    request,
                    f"Email di test inviata a {request.user.email}.",
                )
            return HttpResponseRedirect(
                f"{reverse('operations:promemoria')}"
                f"?mese={valore_mese}"
            )
        else:
            messages.error(request, "Azione non riconosciuta.")

        return self._render(
            request,
            configurazione=configurazione,
            anno=anno,
            mese=mese,
            valore_mese=valore_mese,
            form_configurazione=form_configurazione,
            form_invio=form_invio,
        )

    def _render(
        self,
        request,
        *,
        configurazione,
        anno: int,
        mese: int,
        valore_mese: str,
        form_configurazione=None,
        form_invio=None,
    ):
        destinatari = consulenti_senza_ore(
            anno=anno,
            mese=mese,
        )
        invii = (
            InvioPromemoria.objects.filter(
                anno=anno,
                mese=mese,
            )
            .select_related("consulente", "configurazione")
            .order_by("-data_tentativo")[:100]
        )

        context = {
            "configurazione": configurazione,
            "form_configurazione": (
                form_configurazione
                or ConfigurazionePromemoriaForm(
                    instance=configurazione
                )
            ),
            "form_invio": (
                form_invio
                or InvioManualePromemoriaForm(
                    initial={"mese": valore_mese}
                )
            ),
            "destinatari": destinatari,
            "invii": invii,
            "mese_selezionato": valore_mese,
            "email_backend": settings.EMAIL_BACKEND,
            "email_console": settings.EMAIL_BACKEND.endswith(
                "console.EmailBackend"
            ),
        }
        return render(request, self.template_name, context)



class ImportazioneListView(BackofficeControlRequiredMixin, View):
    template_name = "operations/importazione_list.html"

    def get(self, request):
        importazioni = (
            Importazione.objects.select_related("avviata_da")
            .prefetch_related("errori")
            .order_by("-created_at")
        )
        paginator = Paginator(importazioni, 30)
        page = paginator.get_page(request.GET.get("page"))
        return render(
            request,
            self.template_name,
            {"page_obj": page, "importazioni": page.object_list},
        )


class ImportazioneCreateView(BackofficeControlRequiredMixin, View):
    template_name = "operations/importazione_form.html"

    def get(self, request):
        return render(
            request,
            self.template_name,
            {"form": ImportazioneFileForm()},
        )

    def post(self, request):
        form = ImportazioneFileForm(request.POST, request.FILES)
        if not form.is_valid():
            return render(
                request,
                self.template_name,
                {"form": form},
            )

        file = form.cleaned_data["file"]
        contenuto = file.read()

        from .import_services import (
            prepara_importazione,
            serializza_anteprima,
        )

        try:
            anteprima = prepara_importazione(
                attore=request.user,
                tipo_importazione=form.cleaned_data[
                    "tipo_importazione"
                ],
                nome_file=file.name,
                contenuto=contenuto,
            )
        except ValidationError as exc:
            form.add_error(None, "; ".join(exc.messages))
            return render(
                request,
                self.template_name,
                {"form": form},
            )

        if (
            anteprima.importazione.stato
            == Importazione.Stato.PRONTA
        ):
            request.session[
                f"importazione_{anteprima.importazione.id}"
            ] = serializza_anteprima(anteprima)

        return HttpResponseRedirect(
            reverse(
                "operations:importazione-detail",
                kwargs={"pk": anteprima.importazione.id},
            )
        )


class ImportazioneDetailView(BackofficeControlRequiredMixin, View):
    template_name = "operations/importazione_detail.html"

    def get(self, request, pk):
        importazione = get_object_or_404(
            Importazione.objects.select_related("avviata_da"),
            pk=pk,
        )
        dati_sessione = request.session.get(
            f"importazione_{importazione.id}",
            {},
        )
        righe_valide = dati_sessione.get("righe", [])
        return render(
            request,
            self.template_name,
            {
                "importazione": importazione,
                "errori": importazione.errori.all(),
                "righe_valide": righe_valide[:100],
                "numero_righe_sessione": len(righe_valide),
                "tipo_importazione": dati_sessione.get(
                    "tipo_importazione"
                ),
            },
        )


class ImportazioneCommitView(BackofficeControlRequiredMixin, View):
    def post(self, request, pk):
        importazione = get_object_or_404(Importazione, pk=pk)
        chiave_sessione = f"importazione_{importazione.id}"
        dati_sessione = request.session.get(chiave_sessione)

        if not dati_sessione:
            messages.error(
                request,
                "I dati temporanei non sono più disponibili. "
                "Carica nuovamente il file.",
            )
            return HttpResponseRedirect(
                reverse(
                    "operations:importazione-detail",
                    kwargs={"pk": importazione.id},
                )
            )

        from .import_services import conferma_importazione

        try:
            conferma_importazione(
                attore=request.user,
                importazione=importazione,
                dati_sessione=dati_sessione,
            )
        except ValidationError as exc:
            messages.error(
                request,
                "; ".join(exc.messages),
            )
        else:
            request.session.pop(chiave_sessione, None)
            messages.success(
                request,
                (
                    f"Importazione completata: "
                    f"{importazione.righe_valide} righe caricate."
                ),
            )

        return HttpResponseRedirect(
            reverse(
                "operations:importazione-detail",
                kwargs={"pk": importazione.id},
            )
        )


class ImportazioneTemplateView(BackofficeControlRequiredMixin, View):
    def get(self, request, tipo):
        tipo = tipo.upper()
        from .import_services import crea_template_xlsx

        try:
            contenuto = crea_template_xlsx(tipo)
        except ValidationError:
            raise Http404

        response = HttpResponse(
            contenuto,
            content_type=(
                "application/vnd.openxmlformats-officedocument."
                "spreadsheetml.sheet"
            ),
        )
        response["Content-Disposition"] = (
            f'attachment; filename="template_import_{tipo.lower()}.xlsx"'
        )
        return response


class ImportazioneErroriCsvView(BackofficeControlRequiredMixin, View):
    def get(self, request, pk):
        importazione = get_object_or_404(Importazione, pk=pk)
        response = HttpResponse(
            content_type="text/csv; charset=utf-8"
        )
        response["Content-Disposition"] = (
            f'attachment; filename="errori_importazione_{pk}.csv"'
        )
        response.write("\ufeff")
        writer = csv.writer(response, delimiter=";")
        writer.writerow(
            [
                "numero_riga",
                "campo",
                "codice_errore",
                "messaggio",
                "dati_riga",
            ]
        )
        for errore in importazione.errori.all():
            writer.writerow(
                spreadsheet_safe_row(
                    [
                        errore.numero_riga,
                        errore.campo,
                        errore.codice_errore,
                        errore.messaggio,
                        json.dumps(
                            errore.dati_riga,
                            ensure_ascii=False,
                        ),
                    ]
                )
            )
        return response


def _audit_queryset(request):
    queryset = AuditLog.objects.select_related("utente")
    form = AuditLogFilterForm(request.GET or None)

    if form.is_valid():
        entita = form.cleaned_data.get("entita")
        azione = form.cleaned_data.get("azione")
        utente = form.cleaned_data.get("utente")
        dal = form.cleaned_data.get("dal")
        al = form.cleaned_data.get("al")

        if entita:
            queryset = queryset.filter(entita__icontains=entita)
        if azione:
            queryset = queryset.filter(azione__icontains=azione)
        if utente:
            queryset = queryset.filter(
                Q(utente__email__icontains=utente)
                | Q(utente__first_name__icontains=utente)
                | Q(utente__last_name__icontains=utente)
            )
        if dal:
            queryset = queryset.filter(created_at__date__gte=dal)
        if al:
            queryset = queryset.filter(created_at__date__lte=al)

    return queryset.order_by("-created_at"), form


class AuditLogListView(AuditReadRequiredMixin, View):
    template_name = "operations/audit_list.html"

    def get(self, request):
        queryset, form = _audit_queryset(request)
        paginator = Paginator(queryset, 50)
        page = paginator.get_page(request.GET.get("page"))

        eventi = []
        for log in page.object_list:
            entita_display = None
            if log.entita == "PeriodoMensile":
                from .models import PeriodoMensile
                periodo = PeriodoMensile.objects.filter(pk=log.entita_id).first()
                if periodo:
                    entita_display = str(periodo)

            eventi.append(
                {
                    "log": log,
                    "entita_display": entita_display,
                    "precedente_json": json.dumps(
                        log.valore_precedente,
                        ensure_ascii=False,
                        indent=2,
                        default=str,
                    )
                    if log.valore_precedente is not None
                    else "",
                    "nuovo_json": json.dumps(
                        log.valore_nuovo,
                        ensure_ascii=False,
                        indent=2,
                        default=str,
                    )
                    if log.valore_nuovo is not None
                    else "",
                }
            )

        return render(
            request,
            self.template_name,
            {
                "form": form,
                "page_obj": page,
                "eventi": eventi,
            },
        )


class AuditLogCsvView(AuditReadRequiredMixin, View):
    def get(self, request):
        queryset, form = _audit_queryset(request)
        response = HttpResponse(
            content_type="text/csv; charset=utf-8"
        )
        response["Content-Disposition"] = (
            'attachment; filename="audit_log.csv"'
        )
        response.write("\ufeff")
        writer = csv.writer(response, delimiter=";")
        writer.writerow(
            [
                "data_ora",
                "utente",
                "entita",
                "entita_id",
                "azione",
                "motivazione",
                "valore_precedente",
                "valore_nuovo",
            ]
        )
        for log in queryset.iterator():
            writer.writerow(
                spreadsheet_safe_row(
                    [
                        timezone.localtime(log.created_at).strftime(
                            "%Y-%m-%d %H:%M:%S"
                        ),
                        log.utente.email,
                        log.entita,
                        str(log.entita_id),
                        log.azione,
                        log.motivazione,
                        json.dumps(
                            log.valore_precedente,
                            ensure_ascii=False,
                            default=str,
                        ),
                        json.dumps(
                            log.valore_nuovo,
                            ensure_ascii=False,
                            default=str,
                        ),
                    ]
                )
            )
        return response
