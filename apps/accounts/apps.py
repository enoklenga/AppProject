from django.apps import AppConfig


class AccountsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.accounts"
    verbose_name = "Account"

    def ready(self):
        from .signals import connect_scope_signals

        connect_scope_signals()
