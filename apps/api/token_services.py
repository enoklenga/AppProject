from __future__ import annotations

from datetime import timedelta
from hashlib import sha256

from django.conf import settings
from apps.common.request_security import get_client_ip
from django.db import transaction
from django.utils import timezone
from rest_framework.authtoken.models import Token

from .models import ApiTokenMetadata


def token_ttl_hours() -> int:
    return max(int(getattr(settings, "API_TOKEN_TTL_HOURS", 720)), 1)


def token_expiry(token: Token, ttl_hours: int | None = None):
    hours = ttl_hours if ttl_hours is not None else token_ttl_hours()
    return token.created + timedelta(hours=max(int(hours), 1))


def ensure_token_metadata(
    token: Token,
    *,
    created_by=None,
    ttl_hours: int | None = None,
) -> ApiTokenMetadata:
    defaults = {
        "expires_at": token_expiry(token, ttl_hours),
        "created_by": created_by,
    }
    metadata, created = ApiTokenMetadata.objects.get_or_create(
        token=token,
        defaults=defaults,
    )
    if not created and created_by and metadata.created_by_id is None:
        metadata.created_by = created_by
        metadata.save(update_fields=("created_by",))
    return metadata


@transaction.atomic
def issue_token(
    user,
    *,
    rotate: bool = False,
    created_by=None,
    ttl_hours: int | None = None,
) -> tuple[Token, ApiTokenMetadata]:
    existing = Token.objects.select_for_update().filter(user=user).first()

    if existing is not None:
        metadata = ensure_token_metadata(
            existing,
            created_by=created_by,
            ttl_hours=ttl_hours,
        )
        if rotate or metadata.is_expired:
            existing.delete()
            existing = None

    if existing is None:
        token = Token.objects.create(user=user)
        metadata = ApiTokenMetadata.objects.create(
            token=token,
            expires_at=token_expiry(token, ttl_hours),
            created_by=created_by,
            rotated_at=timezone.now() if rotate else None,
        )
        return token, metadata

    return existing, metadata


@transaction.atomic
def rotate_token(
    user,
    *,
    created_by=None,
    ttl_hours: int | None = None,
) -> tuple[Token, ApiTokenMetadata]:
    return issue_token(
        user,
        rotate=True,
        created_by=created_by,
        ttl_hours=ttl_hours,
    )


def revoke_token(user) -> int:
    deleted, _ = Token.objects.filter(user=user).delete()
    return deleted


def mask_token(key: str) -> str:
    if len(key) <= 8:
        return "****"
    return f"{key[:4]}...{key[-4:]}"


def _request_ip(request) -> str:
    return get_client_ip(request)


def request_ip_hash(request) -> str:
    raw_ip = _request_ip(request)
    salt = settings.SECRET_KEY[:32]
    return sha256(f"{salt}:{raw_ip}".encode("utf-8")).hexdigest()


def touch_token_usage(token: Token, request) -> None:
    metadata = ensure_token_metadata(token)
    now = timezone.now()
    minutes = max(
        int(
            getattr(
                settings,
                "API_TOKEN_TOUCH_INTERVAL_MINUTES",
                5,
            )
        ),
        0,
    )
    threshold = now - timedelta(minutes=minutes)

    if (
        metadata.last_used_at is not None
        and metadata.last_used_at >= threshold
    ):
        return

    ApiTokenMetadata.objects.filter(token=token).update(
        last_used_at=now,
        last_used_ip_hash=request_ip_hash(request),
    )


def token_status(token: Token) -> dict:
    metadata = ensure_token_metadata(token)
    now = timezone.now()
    remaining = max(
        int((metadata.expires_at - now).total_seconds()),
        0,
    )
    return {
        "masked_token": mask_token(token.key),
        "created_at": token.created,
        "expires_at": metadata.expires_at,
        "expired": metadata.is_expired,
        "seconds_remaining": remaining,
        "last_used_at": metadata.last_used_at,
        "rotated_at": metadata.rotated_at,
    }
