from datetime import date

from django.core.management.base import (
    BaseCommand,
    CommandError,
)
from django.utils import timezone

from apps.notifications.models import Notification
from apps.notifications.selectors import (
    tasks_due_soon_for_notifications,
    tasks_overdue_for_notifications,
)
from apps.notifications.services import (
    generate_due_soon_notifications,
    generate_overdue_notifications,
)


class Command(BaseCommand):
    help = (
        "Genera le notifiche automatiche per "
        "attività in scadenza e attività scadute."
    )

    def add_arguments(self, parser):

        parser.add_argument(
            "--giorni",
            type=int,
            default=7,
            help=(
                "Numero di giorni da considerare "
                "per le attività in scadenza. "
                "Default: 7."
            ),
        )

        parser.add_argument(
            "--data",
            type=str,
            default=None,
            help=(
                "Data di riferimento in formato YYYY-MM-DD. "
                "Se omessa viene utilizzata la data corrente."
            ),
        )

        parser.add_argument(
            "--dry-run",
            action="store_true",
            help=(
                "Mostra quanti task verrebbero elaborati "
                "senza creare notifiche."
            ),
        )

    def handle(self, *args, **options):

        giorni = options["giorni"]
        data_raw = options["data"]
        dry_run = options["dry_run"]

        # =================================================
        # VALIDAZIONE
        # =================================================

        if giorni < 0:
            raise CommandError(
                "--giorni non può essere negativo."
            )

        if data_raw:
            try:
                oggi = date.fromisoformat(
                    data_raw
                )

            except ValueError as exc:
                raise CommandError(
                    "--data deve essere nel formato YYYY-MM-DD."
                ) from exc

        else:
            oggi = timezone.localdate()

        # =================================================
        # TASK DA ANALIZZARE
        # =================================================

        due_soon_tasks = (
            tasks_due_soon_for_notifications(
                giorni=giorni,
                oggi=oggi,
            )
        )

        overdue_tasks = (
            tasks_overdue_for_notifications(
                oggi=oggi,
            )
        )

        numero_due_soon = (
            due_soon_tasks.count()
        )

        numero_overdue = (
            overdue_tasks.count()
        )

        self.stdout.write(
            ""
        )

        self.stdout.write(
            f"Data riferimento: "
            f"{oggi.strftime('%d/%m/%Y')}"
        )

        self.stdout.write(
            f"Finestra prossima scadenza: "
            f"{giorni} giorni"
        )

        self.stdout.write(
            ""
        )

        self.stdout.write(
            f"Task in scadenza trovati: "
            f"{numero_due_soon}"
        )

        self.stdout.write(
            f"Task scaduti trovati: "
            f"{numero_overdue}"
        )

        # =================================================
        # DRY RUN
        # =================================================

        if dry_run:

            self.stdout.write(
                ""
            )

            self.stdout.write(
                self.style.WARNING(
                    "DRY RUN: nessuna notifica creata."
                )
            )

            return

        # =================================================
        # CONTEGGIO PRIMA
        # =================================================

        due_soon_before = (
            Notification.objects
            .filter(
                tipo=(
                    Notification
                    .Tipo
                    .TASK_DUE_SOON
                )
            )
            .count()
        )

        overdue_before = (
            Notification.objects
            .filter(
                tipo=(
                    Notification
                    .Tipo
                    .TASK_OVERDUE
                )
            )
            .count()
        )

        # =================================================
        # GENERAZIONE
        # =================================================

        generate_due_soon_notifications(
            tasks=due_soon_tasks,
        )

        generate_overdue_notifications(
            tasks=overdue_tasks,
        )

        # =================================================
        # CONTEGGIO DOPO
        # =================================================

        due_soon_after = (
            Notification.objects
            .filter(
                tipo=(
                    Notification
                    .Tipo
                    .TASK_DUE_SOON
                )
            )
            .count()
        )

        overdue_after = (
            Notification.objects
            .filter(
                tipo=(
                    Notification
                    .Tipo
                    .TASK_OVERDUE
                )
            )
            .count()
        )

        nuove_due_soon = (
            due_soon_after
            - due_soon_before
        )

        nuove_overdue = (
            overdue_after
            - overdue_before
        )

        totale_nuove = (
            nuove_due_soon
            + nuove_overdue
        )

        # =================================================
        # OUTPUT
        # =================================================

        self.stdout.write(
            ""
        )

        self.stdout.write(
            self.style.SUCCESS(
                "Generazione notifiche completata."
            )
        )

        self.stdout.write(
            f"Nuove notifiche in scadenza: "
            f"{nuove_due_soon}"
        )

        self.stdout.write(
            f"Nuove notifiche scadute: "
            f"{nuove_overdue}"
        )

        self.stdout.write(
            self.style.SUCCESS(
                f"Totale nuove notifiche: "
                f"{totale_nuove}"
            )
        )