import logging
import re
import time
import uuid

from django.conf import settings

from .token_services import request_ip_hash

logger = logging.getLogger("lef.api.security")

REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9._-]{8,64}$")


class ApiSecurityMiddleware:
    """
    Aggiunge un request ID e registra solo metadati tecnici.

    Non vengono mai registrati corpo della richiesta, password,
    token, cookie o query string.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not request.path.startswith("/api/"):
            return self.get_response(request)

        supplied = request.headers.get("X-Request-ID", "")
        request_id = (
            supplied
            if REQUEST_ID_RE.fullmatch(supplied)
            else uuid.uuid4().hex
        )
        request.api_request_id = request_id
        started = time.monotonic()

        try:
            response = self.get_response(request)
        except Exception:
            logger.exception(
                "api_exception request_id=%s method=%s path=%s ip_hash=%s",
                request_id,
                request.method,
                request.path,
                request_ip_hash(request),
            )
            raise

        response["X-Request-ID"] = request_id
        response["X-Content-Type-Options"] = "nosniff"
        response["Referrer-Policy"] = "no-referrer"
        response["Cache-Control"] = "no-store"

        duration_ms = round((time.monotonic() - started) * 1000)
        user = getattr(request, "user", None)
        user_id = (
            str(user.pk)
            if user is not None and getattr(user, "is_authenticated", False)
            else "-"
        )

        status_code = response.status_code
        if status_code in {401, 403, 429}:
            logger.warning(
                (
                    "api_security status=%s request_id=%s method=%s "
                    "path=%s user_id=%s ip_hash=%s duration_ms=%s"
                ),
                status_code,
                request_id,
                request.method,
                request.path,
                user_id,
                request_ip_hash(request),
                duration_ms,
            )
        elif (
            request.method not in {"GET", "HEAD", "OPTIONS"}
            and getattr(
                settings,
                "API_SECURITY_LOG_MUTATIONS",
                True,
            )
        ):
            logger.info(
                (
                    "api_mutation status=%s request_id=%s method=%s "
                    "path=%s user_id=%s duration_ms=%s"
                ),
                status_code,
                request_id,
                request.method,
                request.path,
                user_id,
                duration_ms,
            )

        return response
