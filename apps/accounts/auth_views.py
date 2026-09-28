from hashlib import sha256

from django.conf import settings
from django.contrib.auth import views as auth_views
from django.core.cache import cache
from django.utils import timezone

from apps.common.request_security import get_client_ip


class NokihubLoginView(auth_views.LoginView):
    """Login web con rate limiting per IP+email e per IP."""

    def _identifier(self) -> str:
        return (
            self.request.POST.get("username", "")
            or self.request.POST.get("email", "")
        ).strip().lower()

    def _rate_keys(self) -> tuple[str, str]:
        ip = get_client_ip(self.request)
        identifier = self._identifier()
        digest = sha256(f"{ip}:{identifier}".encode("utf-8")).hexdigest()
        ip_digest = sha256(ip.encode("utf-8")).hexdigest()
        return (
            f"nokihub:web-login:identity:{digest}",
            f"nokihub:web-login:ip:{ip_digest}",
        )

    def _limits(self) -> tuple[int, int, int]:
        return (
            int(getattr(settings, "WEB_LOGIN_RATE_LIMIT", 5)),
            int(getattr(settings, "WEB_LOGIN_IP_RATE_LIMIT", 30)),
            int(getattr(settings, "WEB_LOGIN_RATE_WINDOW_SECONDS", 300)),
        )

    @staticmethod
    def _counter_value(key: str) -> int:
        try:
            return int(cache.get(key, 0) or 0)
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _increment_counter(key: str, timeout: int) -> None:
        if cache.add(key, 1, timeout=timeout):
            return
        try:
            cache.incr(key)
        except (ValueError, TypeError):
            cache.set(key, 1, timeout=timeout)

    def _is_rate_limited(self) -> bool:
        identity_key, ip_key = self._rate_keys()
        identity_limit, ip_limit, _ = self._limits()
        return (
            self._counter_value(identity_key) >= identity_limit
            or self._counter_value(ip_key) >= ip_limit
        )

    def _record_failure(self) -> None:
        identity_key, ip_key = self._rate_keys()
        _, _, timeout = self._limits()
        self._increment_counter(identity_key, timeout)
        self._increment_counter(ip_key, timeout)

    def _clear_identity_counter(self) -> None:
        identity_key, _ = self._rate_keys()
        cache.delete(identity_key)

    def post(self, request, *args, **kwargs):
        if self._is_rate_limited():
            form = self.get_form()
            form.add_error(
                None,
                "Troppi tentativi di accesso. Attendi alcuni minuti e riprova.",
            )
            return self.render_to_response(
                self.get_context_data(form=form),
                status=429,
            )
        return super().post(request, *args, **kwargs)

    def form_invalid(self, form):
        self._record_failure()
        return super().form_invalid(form)

    def form_valid(self, form):
        self._clear_identity_counter()
        return super().form_valid(form)


class NokihubPasswordChangeView(auth_views.PasswordChangeView):
    """Cambio password autenticato che chiude il requisito obbligatorio."""

    def form_valid(self, form):
        response = super().form_valid(form)
        user = form.user
        if user.deve_cambiare_password:
            user.deve_cambiare_password = False
            user.save(update_fields=["deve_cambiare_password"])
        return response


class NokihubPasswordResetConfirmView(auth_views.PasswordResetConfirmView):
    """Reset password: una nuova password valida soddisfa il requisito."""

    def form_valid(self, form):
        response = super().form_valid(form)
        user = form.user
        if user.deve_cambiare_password:
            user.deve_cambiare_password = False
            user.save(update_fields=["deve_cambiare_password"])
        return response


class NokihubActivationConfirmView(auth_views.PasswordResetConfirmView):
    """Prima attivazione: l'utente sceglie la password e abilita l'account."""

    def form_valid(self, form):
        # PasswordResetConfirmView salva la nuova password e invalida il token.
        response = super().form_valid(form)
        user = form.user
        update_fields = []

        if not user.is_active:
            user.is_active = True
            update_fields.append("is_active")
        if user.deve_cambiare_password:
            user.deve_cambiare_password = False
            update_fields.append("deve_cambiare_password")
        if user.attivato_il is None:
            user.attivato_il = timezone.now()
            update_fields.append("attivato_il")

        if update_fields:
            user.save(update_fields=update_fields)
        return response
