"""Helper condivisi per IP client e redirect interni sicuri."""

from ipaddress import ip_address

from django.conf import settings
from django.utils.http import url_has_allowed_host_and_scheme


def _validated_ip(value: str) -> str | None:
    value = (value or "").strip()
    if not value:
        return None
    try:
        return str(ip_address(value))
    except ValueError:
        return None


def get_client_ip(request) -> str:
    """
    Restituisce l'IP client senza fidarsi del primo valore arbitrario di XFF.

    Se API_TRUST_X_FORWARDED_FOR è abilitato, viene usato il numero di proxy
    fidati configurato in REST_FRAMEWORK['NUM_PROXIES'] e si seleziona il
    valore corrispondente partendo da destra. In questo modo eventuali valori
    X-Forwarded-For preiniettati dal client a sinistra non diventano l'IP
    attribuito all'utente.
    """

    remote = _validated_ip(request.META.get("REMOTE_ADDR", ""))

    if not bool(getattr(settings, "API_TRUST_X_FORWARDED_FOR", False)):
        return remote or "unknown"

    try:
        proxy_count = int(
            getattr(settings, "REST_FRAMEWORK", {}).get("NUM_PROXIES", 0)
            or 0
        )
    except (TypeError, ValueError):
        proxy_count = 0

    if proxy_count <= 0:
        return remote or "unknown"

    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    chain = [part.strip() for part in forwarded.split(",") if part.strip()]

    if len(chain) >= proxy_count:
        candidate = _validated_ip(chain[-proxy_count])
        if candidate:
            return candidate

    return remote or "unknown"


def safe_internal_redirect(request, target: str | None) -> str | None:
    target = (target or "").strip()
    if not target:
        return None

    if url_has_allowed_host_and_scheme(
        url=target,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return target

    return None
