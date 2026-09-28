from rest_framework.settings import api_settings
from rest_framework.throttling import (
    AnonRateThrottle,
    UserRateThrottle,
)


class DynamicRateMixin:
    def get_rate(self):
        rates = api_settings.DEFAULT_THROTTLE_RATES
        return rates.get(self.scope)


class LoginRateThrottle(DynamicRateMixin, AnonRateThrottle):
    scope = "api_login"


class UserBurstRateThrottle(DynamicRateMixin, UserRateThrottle):
    scope = "user_burst"


class UserSustainedRateThrottle(DynamicRateMixin, UserRateThrottle):
    scope = "user_sustained"


class MutationRateThrottle(DynamicRateMixin, UserRateThrottle):
    scope = "api_mutation"


class SensitiveOperationThrottle(
    DynamicRateMixin,
    UserRateThrottle,
):
    scope = "api_sensitive"


class ImportRateThrottle(DynamicRateMixin, UserRateThrottle):
    scope = "api_import"


class ExportRateThrottle(DynamicRateMixin, UserRateThrottle):
    scope = "api_export"
