from django.core.management.base import BaseCommand

from apps.notifications.services import (
    ensure_notification_preferences,
)


class Command(BaseCommand):

    help = (
        "Crea le preferenze notifiche "
        "mancanti per gli utenti esistenti."
    )

    def handle(self, *args, **options):

        created = (
            ensure_notification_preferences()
        )

        self.stdout.write(
            self.style.SUCCESS(
                f"Create {created} preferenze notifiche."
            )
        )