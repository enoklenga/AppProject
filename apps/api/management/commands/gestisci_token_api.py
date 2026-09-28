from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from rest_framework.authtoken.models import Token

from apps.api.token_services import (
    ensure_token_metadata,
    issue_token,
    revoke_token,
    token_status,
)

User = get_user_model()


class Command(BaseCommand):
    help = "Crea, controlla, rigenera o revoca il token API di un utente."

    def add_arguments(self, parser):
        parser.add_argument(
            "--email",
            required=True,
            help="Email dell'utente.",
        )
        actions = parser.add_mutually_exclusive_group()
        actions.add_argument(
            "--regenera",
            action="store_true",
            help="Revoca il token esistente e ne crea uno nuovo.",
        )
        actions.add_argument(
            "--revoca",
            action="store_true",
            help="Revoca il token esistente.",
        )
        actions.add_argument(
            "--stato",
            action="store_true",
            help="Mostra metadati e scadenza senza mostrare la chiave.",
        )
        parser.add_argument(
            "--scadenza-ore",
            type=int,
            help="Durata personalizzata del nuovo token.",
        )

    def handle(self, *args, **options):
        try:
            user = User.objects.get(
                email__iexact=options["email"].strip()
            )
        except User.DoesNotExist as exc:
            raise CommandError("Utente non trovato.") from exc

        if not user.is_active:
            raise CommandError("L'utente non è attivo.")

        ttl = options.get("scadenza_ore")
        if ttl is not None and ttl < 1:
            raise CommandError("--scadenza-ore deve essere maggiore di zero.")

        if options["revoca"]:
            if revoke_token(user):
                self.stdout.write(
                    self.style.SUCCESS("Token API revocato.")
                )
            else:
                self.stdout.write("Nessun token API presente.")
            return

        if options["stato"]:
            token = Token.objects.filter(user=user).first()
            if token is None:
                self.stdout.write("Nessun token API presente.")
                return
            ensure_token_metadata(token)
            stato = token_status(token)
            self.stdout.write(f"Utente: {user.email}")
            self.stdout.write(
                f"Token: {stato['masked_token']}"
            )
            self.stdout.write(
                f"Creato: {stato['created_at'].isoformat()}"
            )
            self.stdout.write(
                f"Scade: {stato['expires_at'].isoformat()}"
            )
            self.stdout.write(
                f"Scaduto: {'Sì' if stato['expired'] else 'No'}"
            )
            self.stdout.write(
                f"Ultimo uso: {stato['last_used_at'] or '-'}"
            )
            return

        token, metadata = issue_token(
            user,
            rotate=options["regenera"],
            created_by=user,
            ttl_hours=ttl,
        )
        azione = "rigenerato" if options["regenera"] else "disponibile"
        self.stdout.write(
            self.style.SUCCESS(
                f"Token API {azione} per {user.email}: {token.key}"
            )
        )
        self.stdout.write(
            f"Scadenza: {metadata.expires_at.isoformat()}"
        )
        self.stdout.write(
            self.style.WARNING(
                "Conservare il token come una password e usarlo solo su HTTPS."
            )
        )
