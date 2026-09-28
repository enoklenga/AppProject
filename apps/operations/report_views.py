from datetime import date

from django.http import HttpResponse
from django.shortcuts import render
from django.urls import reverse
from django.utils import timezone

from apps.phases.models import FaseCommessa
from django.views import View

from apps.common.mixins import ReportsReadRequiredMixin
from .report_forms import ReportMensileFilterForm
from .report_services import FiltriReport, crea_report_xlsx, dati_report


def _form_iniziale(request):
    oggi = timezone.localdate()
    dati = request.GET.copy()
    if not dati.get("mese"):
        dati["mese"] = f"{oggi.year:04d}-{oggi.month:02d}"
    return ReportMensileFilterForm(dati)


def _filtri_da_form(form):
    giorno = form.cleaned_data["mese"]
    cliente = form.cleaned_data.get("cliente")
    commessa = form.cleaned_data.get("commessa")
    consulente = form.cleaned_data.get("consulente")
    fase = form.cleaned_data.get("fase")
    return FiltriReport(
        anno=giorno.year,
        mese=giorno.month,
        cliente_id=cliente.id if cliente else None,
        commessa_id=commessa.id if commessa else None,
        consulente_id=consulente.id if consulente else None,
        fase_id=fase.id if fase else None,
    )


class ReportMensileView(ReportsReadRequiredMixin, View):
    template_name = "operations/report_mensile.html"

    def get(self, request):
        form = _form_iniziale(request)
        report = None
        if form.is_valid():
            report = dati_report(_filtri_da_form(form))
        return render(
            request,
            self.template_name,
            {"form": form, "report": report},
        )


class ReportMensileXlsxView(ReportsReadRequiredMixin, View):
    def get(self, request):
        form = _form_iniziale(request)
        if not form.is_valid():
            response = HttpResponse(
                "Filtri non validi.",
                status=400,
                content_type="text/plain; charset=utf-8",
            )
            return response

        filtri = _filtri_da_form(form)
        contenuto = crea_report_xlsx(filtri)
        response = HttpResponse(
            contenuto,
            content_type=(
                "application/vnd.openxmlformats-officedocument."
                "spreadsheetml.sheet"
            ),
        )
        response["Content-Disposition"] = (
            f'attachment; filename="report_timesheet_'
            f'{filtri.anno}_{filtri.mese:02d}.xlsx"'
        )
        return response
