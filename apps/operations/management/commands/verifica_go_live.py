from pathlib import Path
from urllib.parse import urlparse

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.checks import ERROR, run_checks
from django.core.management.base import BaseCommand
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.urls import NoReverseMatch, reverse


class Command(BaseCommand):
    help = "Verifica i requisiti tecnici essenziali prima del go-live."

    def add_arguments(self, parser):
        parser.add_argument(
            "--allow-http",
            action="store_true",
            help="Consente SITE_URL in HTTP per prove locali.",
        )
        parser.add_argument(
            "--allow-console-email",
            action="store_true",
            help="Consente il backend email console per prove locali.",
        )

    def handle(self, *args, **options):
        errori = []
        avvisi = []

        def ok(nome, dettaglio):
            self.stdout.write(self.style.SUCCESS(f"[OK] {nome}: {dettaglio}"))

        def warn(nome, dettaglio):
            avvisi.append(f"{nome}: {dettaglio}")
            self.stdout.write(self.style.WARNING(f"[AVVISO] {nome}: {dettaglio}"))

        def fail(nome, dettaglio):
            errori.append(f"{nome}: {dettaglio}")
            self.stderr.write(self.style.ERROR(f"[ERRORE] {nome}: {dettaglio}"))

        if settings.DEBUG:
            fail("DEBUG", "DJANGO_DEBUG deve essere False.")
        else:
            ok("DEBUG", "disattivato")

        secret_key = str(settings.SECRET_KEY)
        if not secret_key or secret_key == "unsafe-development-key" or len(secret_key) < 40:
            fail("SECRET_KEY", "impostare una chiave casuale di almeno 40 caratteri.")
        else:
            ok("SECRET_KEY", "configurata")

        allowed_hosts = list(settings.ALLOWED_HOSTS)
        if not allowed_hosts:
            fail("ALLOWED_HOSTS", "nessun host configurato.")
        elif "*" in allowed_hosts:
            fail("ALLOWED_HOSTS", "il wildcard * non è ammesso nel go-live.")
        else:
            ok("ALLOWED_HOSTS", ", ".join(allowed_hosts))

        site_url = str(getattr(settings, "SITE_URL", ""))
        parsed_url = urlparse(site_url)
        if parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc:
            fail("SITE_URL", "URL assente o non valido.")
        elif parsed_url.scheme != "https" and not options["allow_http"]:
            fail("SITE_URL", "in produzione deve usare HTTPS.")
        else:
            ok("SITE_URL", site_url)

        email_backend = str(settings.EMAIL_BACKEND)
        if email_backend.endswith("console.EmailBackend") and not options["allow_console_email"]:
            fail("EMAIL_BACKEND", "il backend console non recapita email reali.")
        else:
            ok("EMAIL_BACKEND", email_backend)

        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT current_database(), current_user")
                database, user = cursor.fetchone()
        except Exception as exc:
            fail("Database", exc)
        else:
            ok("Database", f"{database} come {user}")

        try:
            executor = MigrationExecutor(connection)
            plan = executor.migration_plan(executor.loader.graph.leaf_nodes())
        except Exception as exc:
            fail("Migrazioni", exc)
        else:
            if plan:
                names = ", ".join(
                    f"{migration.app_label}.{migration.name}"
                    for migration, _ in plan
                )
                fail("Migrazioni", f"non applicate: {names}")
            else:
                ok("Migrazioni", "allineate")

        User = get_user_model()
        admin_count = User.objects.filter(
            ruolo=User.Ruolo.ADMIN,
            is_active=True,
        ).count()
        if admin_count == 0:
            fail("Admin LEF", "nessun account Admin attivo.")
        else:
            ok("Admin LEF", f"{admin_count} account attivi")

        route_names = [
            "health",
            "health_ready",
            "login",
            "operations:dashboard-admin",
            "operations:periodo-detail",
            "operations:promemoria",
            "operations:importazione-list",
            "operations:audit-list",
            "operations:report-mensile",
        ]
        unresolved = []
        for route_name in route_names:
            try:
                reverse(route_name)
            except NoReverseMatch as exc:
                unresolved.append(f"{route_name}: {exc}")
        if unresolved:
            fail("URL", " | ".join(unresolved))
        else:
            ok("URL", f"{len(route_names)} percorsi principali risolti")

        private_media_root = Path(settings.PRIVATE_MEDIA_ROOT)
        try:
            private_media_root.mkdir(parents=True, exist_ok=True)
            probe = private_media_root / ".write_probe"
            probe.write_text("ok", encoding="utf-8")
            probe.unlink(missing_ok=True)
        except OSError as exc:
            fail("Private media", f"directory non scrivibile: {exc}")
        else:
            ok("Private media", f"scrivibile: {private_media_root}")

        if getattr(settings, "API_TRUST_X_FORWARDED_FOR", False):
            num_proxies = int(
                settings.REST_FRAMEWORK.get("NUM_PROXIES", 0) or 0
            )
            if num_proxies < 1:
                fail(
                    "Proxy/IP",
                    "API_TRUST_X_FORWARDED_FOR richiede API_NUM_PROXIES >= 1.",
                )
            else:
                ok("Proxy/IP", f"catena proxy fidata: {num_proxies}")
        else:
            warn(
                "Proxy/IP",
                "X-Forwarded-For non fidato; corretto solo se Django è esposto direttamente.",
            )

        static_root = Path(settings.STATIC_ROOT)
        if not static_root.exists():
            warn("File statici", "STATIC_ROOT non esiste ancora; eseguire collectstatic.")
        elif not any(static_root.iterdir()):
            warn("File statici", "STATIC_ROOT è vuota; eseguire collectstatic.")
        else:
            ok("File statici", str(static_root))

        deploy_issues = run_checks(include_deployment_checks=True)
        blocking = [issue for issue in deploy_issues if issue.level >= ERROR]
        if blocking:
            for issue in blocking:
                fail("Django deploy check", issue)
        else:
            ok("Django deploy check", "nessun errore bloccante")

        self.stdout.write("")
        self.stdout.write(
            f"Esito go-live: {len(errori)} errori, {len(avvisi)} avvisi."
        )
        if errori:
            raise SystemExit(1)
