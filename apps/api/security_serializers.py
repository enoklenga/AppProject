from rest_framework import serializers

from .serializers import UserSummarySerializer


class TokenStatusSerializer(serializers.Serializer):
    masked_token = serializers.CharField()
    created_at = serializers.DateTimeField()
    expires_at = serializers.DateTimeField()
    expired = serializers.BooleanField()
    seconds_remaining = serializers.IntegerField()
    last_used_at = serializers.DateTimeField(
        allow_null=True,
    )
    rotated_at = serializers.DateTimeField(
        allow_null=True,
    )


class TokenIssueResponseSerializer(serializers.Serializer):
    token = serializers.CharField()
    token_type = serializers.CharField()
    user = UserSummarySerializer()
    security = TokenStatusSerializer()


class AdminTokenSerializer(serializers.Serializer):
    user = UserSummarySerializer()
    security = TokenStatusSerializer()


class RevokeTokenResponseSerializer(serializers.Serializer):
    revoked = serializers.BooleanField()
    user_id = serializers.UUIDField()
