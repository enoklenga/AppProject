from django.conf import settings
from django.db import connection
from django.db.models import Q
from django.urls import reverse
from drf_spectacular.utils import (
    OpenApiParameter,
    OpenApiResponse,
    extend_schema,
    extend_schema_view,
)
from rest_framework import status, viewsets
from rest_framework.authtoken.models import Token
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.reverse import reverse as api_reverse
from rest_framework.views import APIView

from apps.operations.models import PeriodoMensile
from apps.projects.models import Assegnazione, Cliente, Commessa
from apps.timesheets.models import RigaOre, SpesaTrasferta
from apps.timesheets.services import (
    elimina_ore,
    elimina_spesa,
    inserisci_ore,
    inserisci_spesa,
    modifica_ore,
    modifica_spesa,
)

from .filters import (
    AssegnazioneFilter,
    ClienteFilter,
    CommessaFilter,
    PeriodoMensileFilter,
    RigaOreFilter,
    SpesaTrasfertaFilter,
)
from .querysets import (
    commesse_gestite_ids,
    filtro_visibilita_assegnazioni,
    filtro_visibilita_timesheet,
)
from .serializers import (
    AssegnazioneSerializer,
    ClienteSerializer,
    CommessaSerializer,
    MeSerializer,
    PeriodoMensileSerializer,
    DeleteVersionSerializer,
    RigaOreCreateSerializer,
    RigaOreMutationResponseSerializer,
    RigaOreSerializer,
    RigaOreUpdateSerializer,
    SpesaCreateSerializer,
    SpesaMutationResponseSerializer,
    SpesaTrasfertaSerializer,
    SpesaUpdateSerializer,
    TokenLoginSerializer,
    UserSummarySerializer,
)
from .service_errors import raise_api_service_error
from .security_serializers import TokenIssueResponseSerializer
from .throttles import LoginRateThrottle, MutationRateThrottle
from .token_services import issue_token, revoke_token, token_status


@extend_schema(exclude=True)
class ApiHealthView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request):
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                cursor.fetchone()
        except Exception:
            return Response(
                {
                    "status": "error",
                    "service": "lef-timesheet-api",
                    "database": "unavailable",
                },
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        return Response(
            {
                "status": "ok",
                "service": "lef-timesheet-api",
                "version": "v1",
                "database": "available",
            }
        )


@extend_schema(exclude=True)
class ApiRootView(APIView):
    def get(self, request):
        return Response(
            {
                "version": "v1",
                "authenticated_user": request.user.email,
                "endpoints": {
                    "me": api_reverse(
                        "api:me",
                        request=request,
                    ),
                    "clienti": api_reverse(
                        "api:cliente-list",
                        request=request,
                    ),
                    "commesse": api_reverse(
                        "api:commessa-list",
                        request=request,
                    ),
                    "assegnazioni": api_reverse(
                        "api:assegnazione-list",
                        request=request,
                    ),
                    "ore": api_reverse(
                        "api:ore-list",
                        request=request,
                    ),
                    "spese": api_reverse(
                        "api:spesa-list",
                        request=request,
                    ),
                    "periodi": api_reverse(
                        "api:periodo-list",
                        request=request,
                    ),
                    "schema": request.build_absolute_uri(
                        reverse("api:schema")
                    ),
                    "docs": request.build_absolute_uri(
                        reverse("api:swagger-ui")
                    ),
                },
            }
        )


@extend_schema(
    tags=["Autenticazione"],
    request=TokenLoginSerializer,
    responses={200: TokenIssueResponseSerializer},
)
class TokenLoginView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [LoginRateThrottle]

    def post(self, request):
        serializer = TokenLoginSerializer(
            data=request.data,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data["user"]
        token, _ = issue_token(
            user,
            rotate=settings.API_ROTATE_TOKEN_ON_LOGIN,
            created_by=user,
        )

        return Response(
            {
                "token": token.key,
                "token_type": "Token",
                "user": MeSerializer(user).data,
                "security": token_status(token),
            }
        )


class TokenLogoutView(APIView):
    def post(self, request):
        revoke_token(request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)


class MeView(APIView):
    def get(self, request):
        return Response(MeSerializer(request.user).data)


class BaseReadOnlyViewSet(viewsets.ReadOnlyModelViewSet):
    http_method_names = ["get", "head", "options"]


class BaseTimesheetWriteViewSet(viewsets.ModelViewSet):
    http_method_names = [
        "get",
        "post",
        "put",
        "patch",
        "delete",
        "head",
        "options",
    ]

    def get_throttles(self):
        throttles = super().get_throttles()
        if self.request.method not in {"GET", "HEAD", "OPTIONS"}:
            throttles.append(MutationRateThrottle())
        return throttles


    def _versione_richiesta(self, request) -> int:
        raw_value = (
            request.data.get("versione")
            if hasattr(request.data, "get")
            else None
        )
        if raw_value in (None, ""):
            raw_value = request.query_params.get("versione")

        if raw_value in (None, ""):
            raw_value = request.headers.get("If-Match")

        if raw_value in (None, ""):
            from rest_framework.exceptions import ValidationError

            raise ValidationError(
                {
                    "versione": (
                        "Indicare la versione corrente nel corpo JSON, "
                        "nel parametro ?versione= oppure nell’header If-Match."
                    )
                }
            )

        value = str(raw_value).strip()
        if value.startswith("W/"):
            value = value[2:].strip()
        value = value.strip('"')

        try:
            versione = int(value)
        except (TypeError, ValueError) as exc:
            from rest_framework.exceptions import ValidationError

            raise ValidationError(
                {"versione": "La versione deve essere un numero intero."}
            ) from exc

        if versione < 1:
            from rest_framework.exceptions import ValidationError

            raise ValidationError(
                {"versione": "La versione deve essere almeno 1."}
            )
        return versione

    def _motivazione(self, request) -> str:
        if hasattr(request.data, "get"):
            value = request.data.get("motivazione")
            if value not in (None, ""):
                return str(value)
        return str(request.query_params.get("motivazione", ""))

    def _payload_update(self, request, instance, *, partial: bool) -> dict:
        incoming = {
            key: value
            for key, value in request.data.items()
            if key not in {"versione", "motivazione"}
        }

        if partial:
            payload = self._current_write_values(instance)
            payload.update(incoming)
        else:
            payload = incoming

        payload["versione"] = self._versione_richiesta(request)
        payload["motivazione"] = self._motivazione(request)
        return payload


@extend_schema_view(
    list=extend_schema(tags=["Clienti"]),
    retrieve=extend_schema(tags=["Clienti"]),
)
class ClienteViewSet(BaseReadOnlyViewSet):
    serializer_class = ClienteSerializer
    queryset = Cliente.objects.all()
    filterset_class = ClienteFilter
    search_fields = [
        "ragione_sociale",
        "partita_iva",
        "referente",
    ]
    ordering_fields = [
        "ragione_sociale",
        "partita_iva",
        "created_at",
    ]
    ordering = ["ragione_sociale"]

    def get_queryset(self):
        queryset = super().get_queryset()
        user = self.request.user
        if user.is_admin_lef:
            return queryset

        return queryset.filter(
            Q(commesse__assegnazioni__consulente=user)
            | Q(commesse__id__in=commesse_gestite_ids(user))
        ).distinct()


@extend_schema_view(
    list=extend_schema(tags=["Commesse"]),
    retrieve=extend_schema(tags=["Commesse"]),
)
class CommessaViewSet(BaseReadOnlyViewSet):
    serializer_class = CommessaSerializer
    queryset = Commessa.objects.select_related("cliente")
    filterset_class = CommessaFilter
    search_fields = [
        "codice",
        "descrizione",
        "cliente__ragione_sociale",
    ]
    ordering_fields = [
        "codice",
        "data_inizio",
        "data_fine_prevista",
        "created_at",
    ]
    ordering = ["-data_inizio", "codice"]

    def get_queryset(self):
        queryset = super().get_queryset()
        user = self.request.user
        if user.is_admin_lef:
            return queryset

        return queryset.filter(
            Q(assegnazioni__consulente=user)
            | Q(id__in=commesse_gestite_ids(user))
        ).distinct()


@extend_schema_view(
    list=extend_schema(tags=["Assegnazioni"]),
    retrieve=extend_schema(tags=["Assegnazioni"]),
)
class AssegnazioneViewSet(BaseReadOnlyViewSet):
    serializer_class = AssegnazioneSerializer
    queryset = Assegnazione.objects.select_related(
        "consulente",
        "commessa",
        "commessa__cliente",
    )
    filterset_class = AssegnazioneFilter
    search_fields = [
        "consulente__email",
        "consulente__first_name",
        "consulente__last_name",
        "commessa__codice",
        "commessa__descrizione",
    ]
    ordering_fields = [
        "data_inizio",
        "data_fine",
        "ore_previste",
        "created_at",
    ]
    ordering = ["commessa__codice", "consulente__last_name"]

    def get_queryset(self):
        queryset = super().get_queryset()
        user = self.request.user
        if user.is_admin_lef:
            return queryset
        return queryset.filter(
            filtro_visibilita_assegnazioni(user)
        ).distinct()


@extend_schema_view(
    list=extend_schema(tags=["Ore"]),
    retrieve=extend_schema(tags=["Ore"]),
    create=extend_schema(
        tags=["Ore"],
        request=RigaOreCreateSerializer,
        responses={
            201: RigaOreMutationResponseSerializer,
            400: OpenApiResponse(description="Dati non validi."),
            403: OpenApiResponse(description="Operazione non consentita."),
            423: OpenApiResponse(description="Periodo mensile chiuso."),
        },
    ),
    update=extend_schema(
        tags=["Ore"],
        request=RigaOreUpdateSerializer,
        responses={
            200: RigaOreMutationResponseSerializer,
            400: OpenApiResponse(description="Dati non validi."),
            403: OpenApiResponse(description="Operazione non consentita."),
            409: OpenApiResponse(description="Conflitto di versione."),
            423: OpenApiResponse(description="Periodo mensile chiuso."),
        },
    ),
    partial_update=extend_schema(
        tags=["Ore"],
        request=RigaOreUpdateSerializer,
        responses={
            200: RigaOreMutationResponseSerializer,
            400: OpenApiResponse(description="Dati non validi."),
            403: OpenApiResponse(description="Operazione non consentita."),
            409: OpenApiResponse(description="Conflitto di versione."),
            423: OpenApiResponse(description="Periodo mensile chiuso."),
        },
    ),
    destroy=extend_schema(
        tags=["Ore"],
        parameters=[
            OpenApiParameter(
                name="versione",
                type=int,
                location=OpenApiParameter.QUERY,
                required=False,
                description=(
                    "Versione corrente. Può essere fornita anche "
                    "nel corpo JSON o nell’header If-Match."
                ),
            ),
            OpenApiParameter(
                name="motivazione",
                type=str,
                location=OpenApiParameter.QUERY,
                required=False,
                description="Motivazione della cancellazione Admin.",
            ),
        ],
        responses={
            204: None,
            400: OpenApiResponse(description="Versione mancante o non valida."),
            403: OpenApiResponse(description="Operazione non consentita."),
            409: OpenApiResponse(description="Conflitto di versione."),
            423: OpenApiResponse(description="Periodo mensile chiuso."),
        },
    ),
)
class RigaOreViewSet(BaseTimesheetWriteViewSet):
    queryset = RigaOre.objects.select_related(
        "assegnazione",
        "assegnazione__consulente",
        "assegnazione__commessa",
        "assegnazione__commessa__cliente",
    )
    filterset_class = RigaOreFilter
    search_fields = [
        "nota",
        "assegnazione__consulente__email",
        "assegnazione__consulente__first_name",
        "assegnazione__consulente__last_name",
        "assegnazione__commessa__codice",
    ]
    ordering_fields = [
        "data",
        "ore",
        "created_at",
        "updated_at",
    ]
    ordering = ["-data", "-created_at"]

    def get_serializer_class(self):
        if self.action == "create":
            return RigaOreCreateSerializer
        if self.action in {"update", "partial_update"}:
            return RigaOreUpdateSerializer
        return RigaOreSerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        user = self.request.user
        if user.is_admin_lef:
            return queryset
        return queryset.filter(
            filtro_visibilita_timesheet(user)
        ).distinct()

    def _current_write_values(self, instance) -> dict:
        return {
            "assegnazione_id": instance.assegnazione_id,
            "data": instance.data,
            "tipo_attivita": instance.tipo_attivita,
            "ore": instance.ore,
            "nota": instance.nota,
        }

    def _response_data(self, esito):
        return {
            "riga": RigaOreSerializer(
                esito.riga,
                context=self.get_serializer_context(),
            ).data,
            "avvisi": {
                "monte_ore_superato": esito.monte_ore_superato,
                "limite_giornaliero_superato": (
                    esito.limite_giornaliero_superato
                ),
            },
        }

    def create(self, request, *args, **kwargs):
        serializer = RigaOreCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        dati = serializer.validated_data

        try:
            esito = inserisci_ore(
                attore=request.user,
                assegnazione_id=dati["assegnazione_id"],
                giorno=dati["data"],
                tipo_attivita=dati["tipo_attivita"],
                ore=dati["ore"],
                nota=dati.get("nota", ""),
                motivazione=dati.get("motivazione", ""),
            )
        except Exception as exc:
            raise_api_service_error(exc)

        return Response(
            self._response_data(esito),
            status=status.HTTP_201_CREATED,
        )

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        instance = self.get_object()
        payload = self._payload_update(
            request,
            instance,
            partial=partial,
        )

        serializer = RigaOreUpdateSerializer(data=payload)
        serializer.is_valid(raise_exception=True)
        dati = serializer.validated_data

        try:
            esito = modifica_ore(
                attore=request.user,
                riga_id=instance.id,
                versione=dati["versione"],
                assegnazione_id=dati["assegnazione_id"],
                giorno=dati["data"],
                tipo_attivita=dati["tipo_attivita"],
                ore=dati["ore"],
                nota=dati.get("nota", ""),
                motivazione=dati.get("motivazione", ""),
            )
        except Exception as exc:
            raise_api_service_error(exc)

        return Response(self._response_data(esito))

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        versione = self._versione_richiesta(request)

        try:
            elimina_ore(
                attore=request.user,
                riga_id=instance.id,
                versione=versione,
                motivazione=self._motivazione(request),
            )
        except Exception as exc:
            raise_api_service_error(exc)

        return Response(status=status.HTTP_204_NO_CONTENT)


@extend_schema_view(
    list=extend_schema(tags=["Spese"]),
    retrieve=extend_schema(tags=["Spese"]),
    create=extend_schema(
        tags=["Spese"],
        request=SpesaCreateSerializer,
        responses={
            201: SpesaMutationResponseSerializer,
            400: OpenApiResponse(description="Dati non validi."),
            403: OpenApiResponse(description="Operazione non consentita."),
            423: OpenApiResponse(description="Periodo mensile chiuso."),
        },
    ),
    update=extend_schema(
        tags=["Spese"],
        request=SpesaUpdateSerializer,
        responses={
            200: SpesaMutationResponseSerializer,
            400: OpenApiResponse(description="Dati non validi."),
            403: OpenApiResponse(description="Operazione non consentita."),
            409: OpenApiResponse(description="Conflitto di versione."),
            423: OpenApiResponse(description="Periodo mensile chiuso."),
        },
    ),
    partial_update=extend_schema(
        tags=["Spese"],
        request=SpesaUpdateSerializer,
        responses={
            200: SpesaMutationResponseSerializer,
            400: OpenApiResponse(description="Dati non validi."),
            403: OpenApiResponse(description="Operazione non consentita."),
            409: OpenApiResponse(description="Conflitto di versione."),
            423: OpenApiResponse(description="Periodo mensile chiuso."),
        },
    ),
    destroy=extend_schema(
        tags=["Spese"],
        parameters=[
            OpenApiParameter(
                name="versione",
                type=int,
                location=OpenApiParameter.QUERY,
                required=False,
                description=(
                    "Versione corrente. Può essere fornita anche "
                    "nel corpo JSON o nell’header If-Match."
                ),
            ),
            OpenApiParameter(
                name="motivazione",
                type=str,
                location=OpenApiParameter.QUERY,
                required=False,
                description="Motivazione della cancellazione Admin.",
            ),
        ],
        responses={
            204: None,
            400: OpenApiResponse(description="Versione mancante o non valida."),
            403: OpenApiResponse(description="Operazione non consentita."),
            409: OpenApiResponse(description="Conflitto di versione."),
            423: OpenApiResponse(description="Periodo mensile chiuso."),
        },
    ),
)
class SpesaTrasfertaViewSet(BaseTimesheetWriteViewSet):
    queryset = SpesaTrasferta.objects.select_related(
        "assegnazione",
        "assegnazione__consulente",
        "assegnazione__commessa",
        "assegnazione__commessa__cliente",
    )
    filterset_class = SpesaTrasfertaFilter
    search_fields = [
        "nota",
        "assegnazione__consulente__email",
        "assegnazione__consulente__first_name",
        "assegnazione__consulente__last_name",
        "assegnazione__commessa__codice",
    ]
    ordering_fields = [
        "data",
        "importo",
        "created_at",
        "updated_at",
    ]
    ordering = ["-data", "-created_at"]

    def get_serializer_class(self):
        if self.action == "create":
            return SpesaCreateSerializer
        if self.action in {"update", "partial_update"}:
            return SpesaUpdateSerializer
        return SpesaTrasfertaSerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        user = self.request.user
        if user.is_admin_lef:
            return queryset
        return queryset.filter(
            filtro_visibilita_timesheet(user)
        ).distinct()

    def _current_write_values(self, instance) -> dict:
        return {
            "assegnazione_id": instance.assegnazione_id,
            "data": instance.data,
            "categoria": instance.categoria,
            "importo": instance.importo,
            "nota": instance.nota,
        }

    def create(self, request, *args, **kwargs):
        serializer = SpesaCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        dati = serializer.validated_data

        try:
            spesa = inserisci_spesa(
                attore=request.user,
                assegnazione_id=dati["assegnazione_id"],
                giorno=dati["data"],
                categoria=dati["categoria"],
                importo=dati["importo"],
                nota=dati.get("nota", ""),
            )
        except Exception as exc:
            raise_api_service_error(exc)

        return Response(
            {
                "spesa": SpesaTrasfertaSerializer(
                    spesa,
                    context=self.get_serializer_context(),
                ).data
            },
            status=status.HTTP_201_CREATED,
        )

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        instance = self.get_object()
        payload = self._payload_update(
            request,
            instance,
            partial=partial,
        )

        serializer = SpesaUpdateSerializer(data=payload)
        serializer.is_valid(raise_exception=True)
        dati = serializer.validated_data

        try:
            spesa = modifica_spesa(
                attore=request.user,
                spesa_id=instance.id,
                versione=dati["versione"],
                assegnazione_id=dati["assegnazione_id"],
                giorno=dati["data"],
                categoria=dati["categoria"],
                importo=dati["importo"],
                nota=dati.get("nota", ""),
                motivazione=dati.get("motivazione", ""),
            )
        except Exception as exc:
            raise_api_service_error(exc)

        return Response(
            {
                "spesa": SpesaTrasfertaSerializer(
                    spesa,
                    context=self.get_serializer_context(),
                ).data
            }
        )

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        versione = self._versione_richiesta(request)

        try:
            elimina_spesa(
                attore=request.user,
                spesa_id=instance.id,
                versione=versione,
                motivazione=self._motivazione(request),
            )
        except Exception as exc:
            raise_api_service_error(exc)

        return Response(status=status.HTTP_204_NO_CONTENT)


@extend_schema_view(
    list=extend_schema(tags=["Periodi"]),
    retrieve=extend_schema(tags=["Periodi"]),
)
class PeriodoMensileViewSet(BaseReadOnlyViewSet):
    serializer_class = PeriodoMensileSerializer
    queryset = PeriodoMensile.objects.all()
    filterset_class = PeriodoMensileFilter
    ordering_fields = ["anno", "mese", "data_chiusura"]
    ordering = ["-anno", "-mese"]
