from django.conf import settings
from rest_framework.authentication import TokenAuthentication
from rest_framework.exceptions import AuthenticationFailed

from .token_services import (
    ensure_token_metadata,
    touch_token_usage,
)


class ExpiringTokenAuthentication(TokenAuthentication):
    """
    Token DRF con scadenza e tracciamento utilizzo.

    I token legacy privi di metadata ricevono automaticamente i
    metadati alla prima autenticazione.
    """

    keyword = "Token"

    def authenticate_credentials(self, key):
        user, token = super().authenticate_credentials(key)
        metadata = ensure_token_metadata(token)

        if metadata.is_expired:
            token.delete()
            raise AuthenticationFailed(
                "Token scaduto. Eseguire nuovamente il login."
            )

        require_changed_password = bool(
            getattr(
                settings,
                "API_REQUIRE_PASSWORD_CHANGED",
                False,
            )
        )
        if (
            require_changed_password
            and getattr(user, "deve_cambiare_password", False)
        ):
            raise AuthenticationFailed(
                "È necessario cambiare la password prima di usare le API."
            )

        return user, token

    def authenticate(self, request):
        result = super().authenticate(request)
        if result is not None:
            _, token = result
            touch_token_usage(token, request)
        return result
