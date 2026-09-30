import csv
import json

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.utils import (
    OpenApiResponse,
    extend_schema,
)
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.generics import ListAPIView, RetrieveAPIView
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.export_security import spreadsheet_safe_row
from apps.operations.import_services import (
    conferma_importazione,
    crea_template_xlsx,
    prepara_importazione,
    serializza_anteprima,
)
from apps.operations.models import (
    AuditLog,
    Importazione,
    InvioPromemoria,
)
from apps.operations.services import (
    consulenti_senza_ore,
    configurazione_promemoria_corrente,
    inizializza_configurazione_promemoria,
    invia_promemoria,
)

from .models import ApiImportazioneAnteprima
from .operations_serializers import (
    AnteprimaPromemoriaSerializer,
    AuditLogFilterSerializer,
    AuditLogSerializer,
    ConfigurazionePromemoriaSerializer,
    EsitoPromemoriaSerializer,
    ImportazioneConfermaSerializer,
    ImportazioneFilterSerializer,
    ImportazioneSerializer,
    ImportazioneUploadSerializer,
    InvioManualePromemoriaSerializer,
    InvioPromemoriaFilterSerializer,
    InvioPromemoriaSerializer,
    PeriodoPromemoriaQuerySerializer,
)
from .permissions import IsGlobalManager
from .throttles import (
    ExportRateThrottle,
    ImportRateThrottle,
    SensitiveOperationThrottle,
    UserBurstRateThrottle,
    UserSustainedRateThrottle,
)


def _validated(serializer_class, data) -> dict:
    serializer = serializer_class(data=data)
    serializer.is_valid(raise_exception=True)
    return serializer.validated_data


def _drf_validation_error(exc: DjangoValidationError):
    if hasattr(exc, "message_dict"):
        raise ValidationError(exc.message_dict) from exc
    raise ValidationError(
        getattr(exc, "messages", [str(exc)])
    ) from exc


def _audit_queryset(query_params):
    filtri = _validated(AuditLogFilterSerializer, query_params)
    queryset = AuditLog.objects.select_related("utente")

    if filtri.get("entita"):
        queryset = queryset.filter(
            entita__icontains=filtri["entita"]
        )
    if filtri.get("entita_id"):
        queryset = queryset.filter(
            entita_id=filtri["entita_id"]
        )
    if filtri.get("azione"):
        queryset = queryset.filter(
            azione__icontains=filtri["azione"]
        )
    if filtri.get("utente"):
        testo = filtri["utente"]
        queryset = queryset.filter(
            Q(utente__email__icontains=testo)
            | Q(utente__first_name__icontains=testo)
            | Q(utente__last_name__icontains=testo)
        )
    if filtri.get("dal"):
        queryset = queryset.filter(
            created_at__date__gte=filtri["dal"]
        )
    if filtri.get("al"):
        queryset = queryset.filter(
            created_at__date__lte=filtri["al"]
        )

    return queryset.order_by("-created_at")


@extend_schema(
    tags=["Promemoria Admin"],
    responses={200: ConfigurazionePromemoriaSerializer},
)
class ConfigurazionePromemoriaAPIView(APIView):
    throttle_classes = [
        UserBurstRateThrottle,
        UserSustainedRateThrottle,
        SensitiveOperationThrottle,
    ]
    permission_classes = [IsGlobalManager]

    def get_object(self, request):
        configurazione = configurazione_promemoria_corrente()
        if configurazione is None:
            configurazione = inizializza_configurazione_promemoria(
                attore=request.user
            )
        return configurazione

    def get(self, request):
        configurazione = self.get_object(request)
        return Response(
            ConfigurazionePromemoriaSerializer(configurazione).data
        )

    @extend_schema(
        request=ConfigurazionePromemoriaSerializer,
        responses={200: ConfigurazionePromemoriaSerializer},
    )
    def patch(self, request):
        configurazione = self.get_object(request)
        serializer = ConfigurazionePromemoriaSerializer(
            configurazione,
            data=request.data,
            partial=True,
        )
        serializer.is_valid(raise_exception=True)
        serializer.save(aggiornata_da=request.user)
        return Response(serializer.data)


@extend_schema(
    tags=["Promemoria Admin"],
    parameters=[PeriodoPromemoriaQuerySerializer],
    responses={200: AnteprimaPromemoriaSerializer},
)
class AnteprimaPromemoriaAPIView(APIView):
    permission_classes = [IsGlobalManager]

    def get(self, request):
        filtri = _validated(
            PeriodoPromemoriaQuerySerializer,
            request.query_params,
        )
        destinatari = consulenti_senza_ore(
            anno=filtri["anno"],
            mese=filtri["mese"],
        )
        payload = {
            "anno": filtri["anno"],
            "mese": filtri["mese"],
            "totale_destinatari": len(destinatari),
            "destinatari": destinatari,
        }
        return Response(AnteprimaPromemoriaSerializer(payload).data)


@extend_schema(
    tags=["Promemoria Admin"],
    request=InvioManualePromemoriaSerializer,
    responses={200: EsitoPromemoriaSerializer},
)
class InviaPromemoriaAPIView(APIView):
    throttle_classes = [
        UserBurstRateThrottle,
        UserSustainedRateThrottle,
        SensitiveOperationThrottle,
    ]
    permission_classes = [IsGlobalManager]

    def post(self, request):
        dati = _validated(
            InvioManualePromemoriaSerializer,
            request.data,
        )
        configurazione = configurazione_promemoria_corrente()
        if configurazione is None:
            configurazione = inizializza_configurazione_promemoria(
                attore=request.user
            )

        esito = invia_promemoria(
            configurazione=configurazione,
            anno=dati["anno"],
            mese=dati["mese"],
            forza=True,
        )
        return Response(EsitoPromemoriaSerializer(esito).data)


@extend_schema(
    tags=["Promemoria Admin"],
    parameters=[InvioPromemoriaFilterSerializer],
)
class InvioPromemoriaListAPIView(ListAPIView):
    permission_classes = [IsGlobalManager]
    serializer_class = InvioPromemoriaSerializer

    def get_queryset(self):
        filtri = _validated(
            InvioPromemoriaFilterSerializer,
            self.request.query_params,
        )
        queryset = InvioPromemoria.objects.select_related(
            "consulente",
            "configurazione",
        )

        if filtri.get("anno") is not None:
            queryset = queryset.filter(anno=filtri["anno"])
        if filtri.get("mese") is not None:
            queryset = queryset.filter(mese=filtri["mese"])
        if filtri.get("stato"):
            queryset = queryset.filter(stato=filtri["stato"])
        if filtri.get("consulente_id"):
            queryset = queryset.filter(
                consulente_id=filtri["consulente_id"]
            )

        return queryset.order_by("-data_tentativo", "-created_at")


@extend_schema(
    tags=["Importazioni Admin"],
    parameters=[ImportazioneFilterSerializer],
)
class ImportazioneListAPIView(ListAPIView):
    permission_classes = [IsGlobalManager]
    serializer_class = ImportazioneSerializer

    def get_queryset(self):
        filtri = _validated(
            ImportazioneFilterSerializer,
            self.request.query_params,
        )
        queryset = Importazione.objects.select_related(
            "avviata_da"
        ).prefetch_related("errori")

        if filtri.get("stato"):
            queryset = queryset.filter(stato=filtri["stato"])
        if filtri.get("avviata_da_id"):
            queryset = queryset.filter(
                avviata_da_id=filtri["avviata_da_id"]
            )
        if filtri.get("dal"):
            queryset = queryset.filter(
                created_at__date__gte=filtri["dal"]
            )
        if filtri.get("al"):
            queryset = queryset.filter(
                created_at__date__lte=filtri["al"]
            )

        return queryset.order_by("-created_at")


@extend_schema(tags=["Importazioni Admin"])
class ImportazioneDetailAPIView(RetrieveAPIView):
    permission_classes = [IsGlobalManager]
    serializer_class = ImportazioneSerializer
    lookup_field = "pk"

    def get_queryset(self):
        return Importazione.objects.select_related(
            "avviata_da"
        ).prefetch_related("errori")


@extend_schema(
    tags=["Importazioni Admin"],
    request=ImportazioneUploadSerializer,
    responses={
        201: OpenApiResponse(
            description=(
                "Importazione validata. Se lo stato è PRONTA, "
                "può essere confermata tramite l'endpoint dedicato."
            )
        ),
    },
)
class ImportazioneUploadAPIView(APIView):
    throttle_classes = [
        UserBurstRateThrottle,
        UserSustainedRateThrottle,
        ImportRateThrottle,
    ]
    permission_classes = [IsGlobalManager]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        serializer = ImportazioneUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        file = serializer.validated_data["file"]
        tipo = serializer.validated_data["tipo_importazione"]

        try:
            anteprima = prepara_importazione(
                attore=request.user,
                tipo_importazione=tipo,
                nome_file=file.name,
                contenuto=file.read(),
            )
        except DjangoValidationError as exc:
            _drf_validation_error(exc)

        dati_sessione = serializza_anteprima(anteprima)

        if anteprima.importazione.stato == Importazione.Stato.PRONTA:
            ApiImportazioneAnteprima.objects.update_or_create(
                importazione=anteprima.importazione,
                defaults={
                    "tipo_importazione": tipo,
                    "dati_sessione": dati_sessione,
                },
            )

        importazione = (
            Importazione.objects.select_related("avviata_da")
            .prefetch_related("errori")
            .get(pk=anteprima.importazione.pk)
        )

        return Response(
            {
                "importazione": ImportazioneSerializer(
                    importazione
                ).data,
                "anteprima": dati_sessione["righe"][:100],
                "anteprima_limitata": (
                    len(dati_sessione["righe"]) > 100
                ),
            },
            status=status.HTTP_201_CREATED,
        )


@extend_schema(
    tags=["Importazioni Admin"],
    request=ImportazioneConfermaSerializer,
    responses={200: ImportazioneSerializer},
)
class ImportazioneConfermaAPIView(APIView):
    throttle_classes = [
        UserBurstRateThrottle,
        UserSustainedRateThrottle,
        SensitiveOperationThrottle,
    ]
    permission_classes = [IsGlobalManager]

    def post(self, request, pk):
        _validated(ImportazioneConfermaSerializer, request.data)

        importazione = get_object_or_404(
            Importazione.objects.select_related("avviata_da"),
            pk=pk,
        )

        try:
            payload = importazione.api_anteprima
        except ApiImportazioneAnteprima.DoesNotExist as exc:
            raise ValidationError(
                {
                    "importazione": (
                        "L’anteprima API non è disponibile. "
                        "Caricare nuovamente il file."
                    )
                }
            ) from exc

        try:
            conferma_importazione(
                attore=request.user,
                importazione=importazione,
                dati_sessione=payload.dati_sessione,
            )
        except DjangoValidationError as exc:
            _drf_validation_error(exc)

        payload.delete()
        importazione.refresh_from_db()

        return Response(
            ImportazioneSerializer(importazione).data
        )


@extend_schema(
    tags=["Importazioni Admin"],
    responses={
        200: OpenApiResponse(
            description="Template Excel per importazione ore o spese."
        )
    },
)
class ImportazioneTemplateAPIView(APIView):
    throttle_classes = [
        UserBurstRateThrottle,
        UserSustainedRateThrottle,
        ExportRateThrottle,
    ]
    permission_classes = [IsGlobalManager]

    def get(self, request, tipo):
        tipo = tipo.upper()
        try:
            contenuto = crea_template_xlsx(tipo)
        except DjangoValidationError as exc:
            _drf_validation_error(exc)

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
        response["Cache-Control"] = "no-store"
        return response


@extend_schema(
    tags=["Importazioni Admin"],
    responses={
        200: OpenApiResponse(
            description="CSV degli errori dell'importazione."
        )
    },
)
class ImportazioneErroriCsvAPIView(APIView):
    throttle_classes = [
        UserBurstRateThrottle,
        UserSustainedRateThrottle,
        ExportRateThrottle,
    ]
    permission_classes = [IsGlobalManager]

    def get(self, request, pk):
        importazione = get_object_or_404(
            Importazione.objects.prefetch_related("errori"),
            pk=pk,
        )
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
                            default=str,
                        ),
                    ]
                )
            )
        return response


@extend_schema(
    tags=["Audit Admin"],
    parameters=[AuditLogFilterSerializer],
)
class AuditLogListAPIView(ListAPIView):
    permission_classes = [IsGlobalManager]
    serializer_class = AuditLogSerializer

    def get_queryset(self):
        return _audit_queryset(self.request.query_params)


@extend_schema(tags=["Audit Admin"])
class AuditLogDetailAPIView(RetrieveAPIView):
    permission_classes = [IsGlobalManager]
    serializer_class = AuditLogSerializer
    queryset = AuditLog.objects.select_related("utente")
    lookup_field = "pk"


@extend_schema(
    tags=["Audit Admin"],
    parameters=[AuditLogFilterSerializer],
    responses={
        200: OpenApiResponse(
            description="Esportazione CSV del registro di audit."
        )
    },
)
class AuditLogCsvAPIView(APIView):
    throttle_classes = [
        UserBurstRateThrottle,
        UserSustainedRateThrottle,
        ExportRateThrottle,
    ]
    permission_classes = [IsGlobalManager]

    def get(self, request):
        queryset = _audit_queryset(request.query_params)
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
