from urllib.parse import urlparse

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.utils import timezone
from rest_framework.authtoken.models import Token

from apps.api.models import ApiTokenMetadata


class Command(BaseCommand):
    help = "Verifica la configurazione di sicurezza e rilascio delle API."

    def add_arguments(self, parser):
        parser.add_argument(
            "--strict",
            action="store_true",
            help=(
                "Tratta come errori anche le impostazioni ammesse "
                "solo nella simulazione locale."
            ),
        )

    def handle(self, *args, **options):
        strict = options["strict"]
        failures = []
        warnings = []

        def ok(message):
            self.stdout.write(self.style.SUCCESS(f"[OK] {message}"))

        def warn(message):
            warnings.append(message)
            self.stdout.write(self.style.WARNING(f"[WARN] {message}"))

        def fail(message):
            failures.append(message)
            self.stdout.write(self.style.ERROR(f"[FAIL] {message}"))

        if settings.DEBUG:
            (fail if strict else warn)("DJANGO_DEBUG è attivo.")
        else:
            ok("DEBUG disattivato.")

        if (
            not settings.SECRET_KEY
            or settings.SECRET_KEY == "unsafe-development-key"
            or len(settings.SECRET_KEY) < 32
        ):
            fail("DJANGO_SECRET_KEY assente, predefinita o troppo corta.")
        else:
            ok("Secret key valorizzata.")

        if not settings.ALLOWED_HOSTS or "*" in settings.ALLOWED_HOSTS:
            fail("DJANGO_ALLOWED_HOSTS è vuoto o contiene '*'.")
        else:
            ok("Allowed hosts espliciti.")

        site_url = urlparse(settings.SITE_URL)
        if site_url.scheme != "https":
            (fail if strict else warn)(
                "SITE_URL non usa HTTPS; ammesso solo per test locale."
            )
        else:
            ok("SITE_URL usa HTTPS.")

        secure_flags = {
            "SECURE_SSL_REDIRECT": settings.SECURE_SSL_REDIRECT,
            "SESSION_COOKIE_SECURE": settings.SESSION_COOKIE_SECURE,
            "CSRF_COOKIE_SECURE": settings.CSRF_COOKIE_SECURE,
        }
        missing_flags = [
            key for key, value in secure_flags.items() if not value
        ]
        if missing_flags:
            message = (
                "Flag HTTPS disattivati: " + ", ".join(missing_flags)
            )
            (fail if strict else warn)(message)
        else:
            ok("Flag HTTPS attivi.")

        if settings.API_TOKEN_TTL_HOURS < 1:
            fail("API_TOKEN_TTL_HOURS non valido.")
        else:
            ok(
                f"Scadenza token: {settings.API_TOKEN_TTL_HOURS} ore."
            )

        rates = settings.REST_FRAMEWORK.get(
            "DEFAULT_THROTTLE_RATES",
            {},
        )
        required_rates = {
            "anon",
            "user_burst",
            "user_sustained",
            "api_login",
            "api_mutation",
            "api_sensitive",
            "api_import",
            "api_export",
        }
        missing_rates = sorted(required_rates - set(rates))
        if missing_rates:
            fail(
                "Rate limit mancanti: " + ", ".join(missing_rates)
            )
        else:
            ok("Rate limit completi.")

        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                cursor.fetchone()
            ok("Database raggiungibile.")
        except Exception as exc:
            fail(f"Database non raggiungibile: {type(exc).__name__}")

        try:
            executor = MigrationExecutor(connection)
            pending = executor.migration_plan(
                executor.loader.graph.leaf_nodes()
            )
            if pending:
                fail(f"Migrazioni pendenti: {len(pending)}.")
            else:
                ok("Nessuna migrazione pendente.")
        except Exception as exc:
            fail(
                "Impossibile verificare le migrazioni: "
                f"{type(exc).__name__}"
            )

        expired = ApiTokenMetadata.objects.filter(
            expires_at__lte=timezone.now()
        ).count()
        tokens = Token.objects.count()
        if expired:
            warn(
                f"Token registrati: {tokens}; scaduti da pulire: {expired}."
            )
        else:
            ok(f"Token registrati: {tokens}; nessuno scaduto.")

        self.stdout.write("")
        self.stdout.write(
            f"Esito: {len(failures)} errori, {len(warnings)} avvisi."
        )
        if failures:
            raise CommandError(
                "Verifica sicurezza API non superata."
            )
