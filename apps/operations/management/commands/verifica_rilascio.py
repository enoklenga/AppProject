from pathlib import Path

from django.conf import settings
from django.core.checks import run_checks
from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db import connection


class Command(BaseCommand):
    help = "Verifica configurazione, database e file statici prima del rilascio."

    def handle(self, *args, **options):
        errori = []

        self.stdout.write("1. Controllo Django per il deployment...")
        problemi = run_checks(include_deployment_checks=True)
        for problema in problemi:
            self.stdout.write(str(problema))
            if getattr(problema, "level", 0) >= 40:
                errori.append(str(problema))

        self.stdout.write("2. Connessione al database...")
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                cursor.fetchone()
        except Exception as exc:
            errori.append(f"Database non raggiungibile: {exc}")
        else:
            self.stdout.write(self.style.SUCCESS("Database raggiungibile."))

        self.stdout.write("3. Controllo migrazioni non applicate...")
        try:
            call_command("migrate", check=True, verbosity=0)
        except SystemExit:
            errori.append("Sono presenti migrazioni non applicate.")
        except Exception as exc:
            errori.append(f"Verifica migrazioni fallita: {exc}")
        else:
            self.stdout.write(self.style.SUCCESS("Migrazioni allineate."))

        self.stdout.write("4. Controllo directory statiche...")
        static_root = Path(settings.STATIC_ROOT)
        if not static_root.exists():
            self.stdout.write(
                self.style.WARNING(
                    "STATIC_ROOT non esiste ancora: eseguire collectstatic."
                )
            )
        else:
            self.stdout.write(self.style.SUCCESS(str(static_root)))

        if errori:
            for errore in errori:
                self.stderr.write(self.style.ERROR(errore))
            raise SystemExit(1)

        self.stdout.write(
            self.style.SUCCESS("Verifica di rilascio completata senza errori bloccanti.")
        )
