from __future__ import annotations

from django.core.exceptions import ObjectDoesNotExist
from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from django.core.exceptions import ValidationError as DjangoValidationError
from apps.operations.period_lock import PeriodoChiusoError

from rest_framework.exceptions import (
    APIException,
    NotFound,
    PermissionDenied,
    ValidationError,
)


class Conflict(APIException):
    status_code = 409
    default_detail = (
        "Il dato è stato modificato da un altro utente. "
        "Rileggere la risorsa e ripetere l’operazione."
    )
    default_code = "version_conflict"


class Locked(APIException):
    status_code = 423
    default_detail = "La risorsa è bloccata."
    default_code = "resource_locked"


def _django_validation_detail(exc: DjangoValidationError):
    if hasattr(exc, "message_dict"):
        return {
            field: list(messages)
            for field, messages in exc.message_dict.items()
        }

    messages = list(getattr(exc, "messages", []))
    if len(messages) == 1:
        return messages[0]
    return messages


def _normalised_message(detail) -> str:
    if isinstance(detail, dict):
        values = []
        for messages in detail.values():
            if isinstance(messages, (list, tuple)):
                values.extend(str(item) for item in messages)
            else:
                values.append(str(messages))
        return " ".join(values).lower()

    if isinstance(detail, (list, tuple)):
        return " ".join(str(item) for item in detail).lower()

    return str(detail).lower()


def raise_api_service_error(exc: Exception) -> None:
    if isinstance(exc, DjangoPermissionDenied):
        raise PermissionDenied(str(exc)) from exc

    if isinstance(exc, PeriodoChiusoError):
        detail = _django_validation_detail(exc)
        raise Locked(detail=detail) from exc

    if isinstance(exc, DjangoValidationError):
        detail = _django_validation_detail(exc)
        message = _normalised_message(detail)

        if (
            "modificato da un altro utente" in message
            or "il dato è stato modificato" in message
        ):
            raise Conflict() from exc

        if (
            "mese selezionato è chiuso" in message
            or "appartiene a un mese chiuso" in message
            or "riga appartiene a un mese chiuso" in message
            or "spesa appartiene a un mese chiuso" in message
        ):
            raise Locked(detail=detail) from exc

        raise ValidationError(detail) from exc

    if isinstance(exc, ObjectDoesNotExist):
        raise NotFound("Risorsa collegata non trovata.") from exc

    raise exc
