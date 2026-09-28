import logging
from typing import Any

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import exception_handler

logger = logging.getLogger("lef.api")


def api_exception_handler(exc: Exception, context: dict[str, Any]):
    request = context.get("request")
    request_id = getattr(request, "api_request_id", None)

    response = exception_handler(exc, context)
    if response is None:
        logger.exception(
            "Unhandled API error request_id=%s",
            request_id or "-",
            exc_info=exc,
        )
        return Response(
            {
                "error": {
                    "status": status.HTTP_500_INTERNAL_SERVER_ERROR,
                    "detail": (
                        "Errore interno. Comunicare il request_id "
                        "all’amministratore."
                    ),
                    "request_id": request_id,
                }
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    original_data = response.data
    if isinstance(original_data, dict) and set(original_data) == {"detail"}:
        detail = original_data["detail"]
    else:
        detail = original_data

    payload = {
        "status": response.status_code,
        "detail": detail,
    }
    if request_id:
        payload["request_id"] = request_id

    retry_after = response.headers.get("Retry-After")
    if retry_after:
        payload["retry_after_seconds"] = retry_after

    response.data = {"error": payload}
    return response
