from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from django.http import HttpResponse
from drf_spectacular.utils import (
    OpenApiResponse,
    extend_schema,
)
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.operations.report_services import (
    FiltriReport,
    crea_report_xlsx,
    dati_report,
)
from apps.operations.services import (
    dashboard_admin,
    dashboard_pm,
)

from .dashboard_serializers import (
    DashboardAdminQuerySerializer,
    DashboardAdminSerializer,
    DashboardPMQuerySerializer,
    DashboardPMSerializer,
    DashboardPersonaleSerializer,
    PeriodoQuerySerializer,
    ReportQuerySerializer,
    ReportRigaOreSerializer,
    ReportSpesaSerializer,
)
from .dashboard_services import dashboard_personale
from .permissions import IsAdminLEF, IsProjectManager
from .throttles import (
    ExportRateThrottle,
    UserBurstRateThrottle,
    UserSustainedRateThrottle,
)


def _validated_query(serializer_class, request) -> dict:
    serializer = serializer_class(data=request.query_params)
    serializer.is_valid(raise_exception=True)
    return serializer.validated_data


@extend_schema(
    tags=["Dashboard"],
    parameters=[PeriodoQuerySerializer],
    responses={200: DashboardPersonaleSerializer},
)
class DashboardPersonaleView(APIView):
    def get(self, request):
        filtri = _validated_query(PeriodoQuerySerializer, request)
        dati = dashboard_personale(
            utente=request.user,
            anno=filtri["anno"],
            mese=filtri["mese"],
        )
        return Response(DashboardPersonaleSerializer(dati).data)


@extend_schema(
    tags=["Dashboard Admin"],
    parameters=[DashboardAdminQuerySerializer],
    responses={
        200: DashboardAdminSerializer,
        403: OpenApiResponse(
            description="Funzione riservata agli Admin LEF."
        ),
    },
)
class DashboardAdminAPIView(APIView):
    permission_classes = [IsAdminLEF]

    def get(self, request):
        filtri = _validated_query(
            DashboardAdminQuerySerializer,
            request,
        )
        dati = dashboard_admin(
            anno=filtri["anno"],
            mese=filtri["mese"],
            cliente_id=filtri.get("cliente_id"),
            commessa_id=filtri.get("commessa_id"),
            consulente_id=filtri.get("consulente_id"),
        )
        return Response(DashboardAdminSerializer(dati).data)


@extend_schema(
    tags=["Dashboard PM"],
    parameters=[DashboardPMQuerySerializer],
    responses={
        200: DashboardPMSerializer,
        403: OpenApiResponse(
            description=(
                "Utente non PM o commessa non gestita dall'utente."
            )
        ),
    },
)
class DashboardPMAPIView(APIView):
    permission_classes = [IsProjectManager]

    def get(self, request):
        filtri = _validated_query(
            DashboardPMQuerySerializer,
            request,
        )
        try:
            dati = dashboard_pm(
                utente=request.user,
                commessa_id=filtri["commessa_id"],
                anno=filtri["anno"],
                mese=filtri["mese"],
            )
        except DjangoPermissionDenied as exc:
            raise PermissionDenied(str(exc)) from exc

        return Response(
            DashboardPMSerializer(
                dati,
                context={"request": request},
            ).data
        )


@extend_schema(
    tags=["Report Admin"],
    parameters=[ReportQuerySerializer],
    responses={
        200: OpenApiResponse(
            description=(
                "Report mensile JSON con dati economici e dettaglio."
            )
        ),
        403: OpenApiResponse(
            description="Funzione riservata agli Admin LEF."
        ),
    },
)
class ReportMensileAPIView(APIView):
    permission_classes = [IsAdminLEF]

    def get(self, request):
        parametri = _validated_query(ReportQuerySerializer, request)
        filtri = FiltriReport(**parametri)
        dati = dati_report(filtri)

        return Response(
            {
                "periodo": {
                    "anno": filtri.anno,
                    "mese": filtri.mese,
                    "testo": filtri.mese_testo,
                },
                "filtri": {
                    "cliente_id": filtri.cliente_id,
                    "commessa_id": filtri.commessa_id,
                    "consulente_id": filtri.consulente_id,
                },
                "dashboard": DashboardAdminSerializer(
                    dati["dashboard"]
                ).data,
                "ore": ReportRigaOreSerializer(
                    dati["righe"],
                    many=True,
                ).data,
                "spese": ReportSpesaSerializer(
                    dati["spese"],
                    many=True,
                ).data,
            }
        )


@extend_schema(
    tags=["Report Admin"],
    parameters=[ReportQuerySerializer],
    responses={
        200: OpenApiResponse(
            description="File Excel del report mensile."
        ),
        403: OpenApiResponse(
            description="Funzione riservata agli Admin LEF."
        ),
    },
)
class ReportMensileExcelAPIView(APIView):
    throttle_classes = [
        UserBurstRateThrottle,
        UserSustainedRateThrottle,
        ExportRateThrottle,
    ]
    permission_classes = [IsAdminLEF]

    def get(self, request):
        parametri = _validated_query(ReportQuerySerializer, request)
        filtri = FiltriReport(**parametri)
        contenuto = crea_report_xlsx(filtri)

        nome_file = (
            f"LEF_Timesheet_Report_"
            f"{filtri.anno:04d}_{filtri.mese:02d}.xlsx"
        )

        response = HttpResponse(
            contenuto,
            content_type=(
                "application/vnd.openxmlformats-officedocument."
                "spreadsheetml.sheet"
            ),
        )
        response["Content-Disposition"] = (
            f'attachment; filename="{nome_file}"'
        )
        response["Cache-Control"] = "no-store"
        return response
