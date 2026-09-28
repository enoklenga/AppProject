from django.urls import include, path
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularRedocView,
    SpectacularSwaggerView,
)
from rest_framework.permissions import IsAuthenticated
from rest_framework.routers import DefaultRouter

from .dashboard_views import (
    DashboardAdminAPIView,
    DashboardPersonaleView,
    DashboardPMAPIView,
    ReportMensileAPIView,
    ReportMensileExcelAPIView,
)


from .operations_views import (
    AnteprimaPromemoriaAPIView,
    AuditLogCsvAPIView,
    AuditLogDetailAPIView,
    AuditLogListAPIView,
    ConfigurazionePromemoriaAPIView,
    ImportazioneConfermaAPIView,
    ImportazioneDetailAPIView,
    ImportazioneErroriCsvAPIView,
    ImportazioneListAPIView,
    ImportazioneTemplateAPIView,
    ImportazioneUploadAPIView,
    InviaPromemoriaAPIView,
    InvioPromemoriaListAPIView,
)


from .security_views import (
    AdminTokenListAPIView,
    AdminTokenRevokeAPIView,
    ApiSecurityStatusAPIView,
    TokenRotateAPIView,
    TokenStatusAPIView,
)

from .views import (
    ApiHealthView,
    ApiRootView,
    AssegnazioneViewSet,
    ClienteViewSet,
    CommessaViewSet,
    MeView,
    PeriodoMensileViewSet,
    RigaOreViewSet,
    SpesaTrasfertaViewSet,
    TokenLoginView,
    TokenLogoutView,
)

app_name = "api"

router = DefaultRouter()
router.register("clienti", ClienteViewSet, basename="cliente")
router.register("commesse", CommessaViewSet, basename="commessa")
router.register(
    "assegnazioni",
    AssegnazioneViewSet,
    basename="assegnazione",
)
router.register("ore", RigaOreViewSet, basename="ore")
router.register("spese", SpesaTrasfertaViewSet, basename="spesa")
router.register(
    "periodi",
    PeriodoMensileViewSet,
    basename="periodo",
)

urlpatterns = [

    path(
        "auth/token/status/",
        TokenStatusAPIView.as_view(),
        name="token-status",
    ),
    path(
        "auth/token/rotate/",
        TokenRotateAPIView.as_view(),
        name="token-rotate",
    ),
    path(
        "security/status/",
        ApiSecurityStatusAPIView.as_view(),
        name="security-status",
    ),
    path(
        "security/tokens/",
        AdminTokenListAPIView.as_view(),
        name="security-token-list",
    ),
    path(
        "security/tokens/<uuid:user_id>/revoke/",
        AdminTokenRevokeAPIView.as_view(),
        name="security-token-revoke",
    ),

    path(
        "promemoria/configurazione/",
        ConfigurazionePromemoriaAPIView.as_view(),
        name="promemoria-configurazione-api",
    ),
    path(
        "promemoria/anteprima/",
        AnteprimaPromemoriaAPIView.as_view(),
        name="promemoria-anteprima-api",
    ),
    path(
        "promemoria/invia/",
        InviaPromemoriaAPIView.as_view(),
        name="promemoria-invia-api",
    ),
    path(
        "promemoria/invii/",
        InvioPromemoriaListAPIView.as_view(),
        name="promemoria-invii-api",
    ),
    path(
        "importazioni/",
        ImportazioneListAPIView.as_view(),
        name="importazioni-api",
    ),
    path(
        "importazioni/upload/",
        ImportazioneUploadAPIView.as_view(),
        name="importazioni-upload-api",
    ),
    path(
        "importazioni/template/<str:tipo>.xlsx",
        ImportazioneTemplateAPIView.as_view(),
        name="importazioni-template-api",
    ),
    path(
        "importazioni/<uuid:pk>/",
        ImportazioneDetailAPIView.as_view(),
        name="importazioni-detail-api",
    ),
    path(
        "importazioni/<uuid:pk>/conferma/",
        ImportazioneConfermaAPIView.as_view(),
        name="importazioni-conferma-api",
    ),
    path(
        "importazioni/<uuid:pk>/errori.csv",
        ImportazioneErroriCsvAPIView.as_view(),
        name="importazioni-errori-csv-api",
    ),
    path(
        "audit/",
        AuditLogListAPIView.as_view(),
        name="audit-api",
    ),
    path(
        "audit/export.csv",
        AuditLogCsvAPIView.as_view(),
        name="audit-csv-api",
    ),
    path(
        "audit/<int:pk>/",
        AuditLogDetailAPIView.as_view(),
        name="audit-detail-api",
    ),
    path(
        "dashboard/me/",
        DashboardPersonaleView.as_view(),
        name="dashboard-me",
    ),
    path(
        "dashboard/admin/",
        DashboardAdminAPIView.as_view(),
        name="dashboard-admin-api",
    ),
    path(
        "dashboard/pm/",
        DashboardPMAPIView.as_view(),
        name="dashboard-pm-api",
    ),
    path(
        "report/mensile/",
        ReportMensileAPIView.as_view(),
        name="report-mensile-api",
    ),
    path(
        "report/mensile.xlsx",
        ReportMensileExcelAPIView.as_view(),
        name="report-mensile-excel-api",
    ),
    path("", ApiRootView.as_view(), name="root"),
    path("health/", ApiHealthView.as_view(), name="health"),
    path("auth/token/", TokenLoginView.as_view(), name="token-login"),
    path("auth/logout/", TokenLogoutView.as_view(), name="token-logout"),
    path("auth/me/", MeView.as_view(), name="me"),
    path(
        "schema/",
        SpectacularAPIView.as_view(
            permission_classes=[IsAuthenticated],
        ),
        name="schema",
    ),
    path(
        "docs/",
        SpectacularSwaggerView.as_view(
            url_name="api:schema",
            permission_classes=[IsAuthenticated],
        ),
        name="swagger-ui",
    ),
    path(
        "redoc/",
        SpectacularRedocView.as_view(
            url_name="api:schema",
            permission_classes=[IsAuthenticated],
        ),
        name="redoc",
    ),
    path("", include(router.urls)),
]
