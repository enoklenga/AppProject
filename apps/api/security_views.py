from django.conf import settings
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework.authtoken.models import Token
from rest_framework.response import Response
from rest_framework.views import APIView

from .authentication import ExpiringTokenAuthentication
from .models import ApiTokenMetadata
from .permissions import IsAdminLEF
from .security_serializers import (
    AdminTokenSerializer,
    RevokeTokenResponseSerializer,
    TokenIssueResponseSerializer,
    TokenStatusSerializer,
)
from .serializers import MeSerializer, UserSummarySerializer
from .throttles import (
    SensitiveOperationThrottle,
    UserBurstRateThrottle,
    UserSustainedRateThrottle,
)
from .token_services import (
    ensure_token_metadata,
    revoke_token,
    rotate_token,
    token_status,
)


@extend_schema(
    tags=["Sicurezza API"],
    responses={200: TokenStatusSerializer},
)
class TokenStatusAPIView(APIView):
    authentication_classes = [ExpiringTokenAuthentication]

    def get(self, request):
        return Response(TokenStatusSerializer(token_status(request.auth)).data)


@extend_schema(
    tags=["Sicurezza API"],
    request=None,
    responses={200: TokenIssueResponseSerializer},
)
class TokenRotateAPIView(APIView):
    authentication_classes = [ExpiringTokenAuthentication]
    throttle_classes = [
        UserBurstRateThrottle,
        UserSustainedRateThrottle,
        SensitiveOperationThrottle,
    ]

    def post(self, request):
        token, _ = rotate_token(
            request.user,
            created_by=request.user,
        )
        return Response(
            {
                "token": token.key,
                "token_type": "Token",
                "user": MeSerializer(request.user).data,
                "security": TokenStatusSerializer(
                    token_status(token)
                ).data,
            }
        )


@extend_schema(tags=["Sicurezza Admin"])
class AdminTokenListAPIView(APIView):
    permission_classes = [IsAdminLEF]

    def get(self, request):
        rows = []
        for token in Token.objects.select_related("user").order_by(
            "user__email"
        ):
            ensure_token_metadata(token)
            rows.append(
                {
                    "user": UserSummarySerializer(token.user).data,
                    "security": TokenStatusSerializer(
                        token_status(token)
                    ).data,
                }
            )
        return Response(
            {
                "count": len(rows),
                "results": rows,
            }
        )


@extend_schema(
    tags=["Sicurezza Admin"],
    request=None,
    responses={200: RevokeTokenResponseSerializer},
)
class AdminTokenRevokeAPIView(APIView):
    permission_classes = [IsAdminLEF]
    throttle_classes = [
        UserBurstRateThrottle,
        UserSustainedRateThrottle,
        SensitiveOperationThrottle,
    ]

    def post(self, request, user_id):
        from apps.accounts.models import User

        user = get_object_or_404(User, pk=user_id)
        revoked = bool(revoke_token(user))
        return Response(
            {
                "revoked": revoked,
                "user_id": user.id,
            }
        )


@extend_schema(tags=["Sicurezza Admin"])
class ApiSecurityStatusAPIView(APIView):
    permission_classes = [IsAdminLEF]

    def get(self, request):
        token_count = Token.objects.count()
        expired_count = ApiTokenMetadata.objects.filter(
            expires_at__lte=timezone.now()
        ).count()

        return Response(
            {
                "token_policy": {
                    "ttl_hours": settings.API_TOKEN_TTL_HOURS,
                    "touch_interval_minutes": (
                        settings.API_TOKEN_TOUCH_INTERVAL_MINUTES
                    ),
                    "rotate_on_login": (
                        settings.API_ROTATE_TOKEN_ON_LOGIN
                    ),
                    "require_password_changed": (
                        settings.API_REQUIRE_PASSWORD_CHANGED
                    ),
                },
                "throttling": {
                    "rates": settings.REST_FRAMEWORK[
                        "DEFAULT_THROTTLE_RATES"
                    ],
                    "num_proxies": settings.REST_FRAMEWORK.get(
                        "NUM_PROXIES"
                    ),
                },
                "runtime": {
                    "debug": settings.DEBUG,
                    "secure_ssl_redirect": (
                        settings.SECURE_SSL_REDIRECT
                    ),
                    "session_cookie_secure": (
                        settings.SESSION_COOKIE_SECURE
                    ),
                    "csrf_cookie_secure": (
                        settings.CSRF_COOKIE_SECURE
                    ),
                },
                "tokens": {
                    "total_records": token_count,
                    "expired_records": expired_count,
                },
            }
        )
