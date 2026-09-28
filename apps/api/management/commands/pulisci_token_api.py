from django.core.management.base import BaseCommand
from django.utils import timezone
from rest_framework.authtoken.models import Token

from apps.api.token_services import ensure_token_metadata


class Command(BaseCommand):
    help = "Revoca i token API scaduti."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Mostra quanti token verrebbero revocati.",
        )

    def handle(self, *args, **options):
        expired_keys = []
        for token in Token.objects.select_related("user"):
            metadata = ensure_token_metadata(token)
            if metadata.expires_at <= timezone.now():
                expired_keys.append(token.key)

        count = len(expired_keys)
        if options["dry_run"]:
            self.stdout.write(
                f"Token scaduti da revocare: {count}"
            )
            return

        if count:
            Token.objects.filter(key__in=expired_keys).delete()
        self.stdout.write(
            self.style.SUCCESS(
                f"Token scaduti revocati: {count}"
            )
        )
