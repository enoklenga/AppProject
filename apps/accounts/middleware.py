from django.conf import settings
from django.shortcuts import redirect
from django.urls import reverse


class ForcePasswordChangeMiddleware:
    """Obbliga gli utenti marcati a cambiare password prima di usare la UI web.

    La policy è attivabile via ``WEB_REQUIRE_PASSWORD_CHANGED``; resta separata
    dalla policy API, che continua a essere governata da
    ``API_REQUIRE_PASSWORD_CHANGED``.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not getattr(settings, "WEB_REQUIRE_PASSWORD_CHANGED", False):
            return self.get_response(request)

        user = getattr(request, "user", None)
        if not user or not user.is_authenticated:
            return self.get_response(request)

        if not getattr(user, "deve_cambiare_password", False):
            return self.get_response(request)

        path = request.path_info
        password_change = reverse("password_change")
        allowed_exact = {
            password_change,
            reverse("logout"),
            reverse("password_reset"),
            reverse("password_reset_done"),
            reverse("password_reset_complete"),
            reverse("health"),
            reverse("health_ready"),
        }
        allowed_prefixes = (
            "/password/reset/confirm/",
            "/api/",
            settings.STATIC_URL,
            settings.MEDIA_URL,
        )

        if path in allowed_exact or any(
            prefix and path.startswith(prefix) for prefix in allowed_prefixes
        ):
            return self.get_response(request)

        return redirect(password_change)
