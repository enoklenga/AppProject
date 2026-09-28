from django.urls import path

from .report_views import ReportMensileView, ReportMensileXlsxView

from .views import (
    AuditLogCsvView,
    AuditLogListView,
    DashboardAdminView,
    DashboardPMView,
    ImportazioneCommitView,
    ImportazioneCreateView,
    ImportazioneDetailView,
    ImportazioneErroriCsvView,
    ImportazioneListView,
    ImportazioneTemplateView,
    PeriodoDetailView,
    PromemoriaView,
)

app_name = "operations"

urlpatterns = [
    path(
        "report/",
        ReportMensileView.as_view(),
        name="report-mensile",
    ),
    path(
        "report/esporta.xlsx",
        ReportMensileXlsxView.as_view(),
        name="report-mensile-xlsx",
    ),
    path(
        "dashboard/",
        DashboardAdminView.as_view(),
        name="dashboard-admin",
    ),
    path(
        "dashboard-pm/",
        DashboardPMView.as_view(),
        name="dashboard-pm",
    ),
    path(
        "periodi/",
        PeriodoDetailView.as_view(),
        name="periodo-detail",
    ),
    path(
        "promemoria/",
        PromemoriaView.as_view(),
        name="promemoria",
    ),
    path(
        "importazioni/",
        ImportazioneListView.as_view(),
        name="importazione-list",
    ),
    path(
        "importazioni/nuova/",
        ImportazioneCreateView.as_view(),
        name="importazione-create",
    ),
    path(
        "importazioni/template/<str:tipo>/",
        ImportazioneTemplateView.as_view(),
        name="importazione-template",
    ),
    path(
        "importazioni/<uuid:pk>/",
        ImportazioneDetailView.as_view(),
        name="importazione-detail",
    ),
    path(
        "importazioni/<uuid:pk>/conferma/",
        ImportazioneCommitView.as_view(),
        name="importazione-commit",
    ),
    path(
        "importazioni/<uuid:pk>/errori.csv",
        ImportazioneErroriCsvView.as_view(),
        name="importazione-errori-csv",
    ),
    path(
        "audit/",
        AuditLogListView.as_view(),
        name="audit-list",
    ),
    path(
        "audit/esporta.csv",
        AuditLogCsvView.as_view(),
        name="audit-csv",
    ),
]
