"""Backend email di sicurezza per l'ambiente staging.

Tutte le email generate dall'applicazione vengono realmente consegnate tramite
il backend configurato in ``EMAIL_REAL_BACKEND``, ma i destinatari vengono
sostituiti con ``EMAIL_REDIRECT_ALL_TO``. In questo modo si possono provare
inviti account, reset password e promemoria senza rischiare invii a consulenti
reali.
"""
from __future__ import annotations

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.core.mail.backends.base import BaseEmailBackend
from django.utils.module_loading import import_string


class StagingRedirectEmailBackend(BaseEmailBackend):
    """Invia email reali solo ai destinatari di test configurati."""

    def __init__(self, fail_silently: bool = False, **kwargs):
        super().__init__(fail_silently=fail_silently)

        self.real_backend_path = getattr(
            settings,
            "EMAIL_REAL_BACKEND",
            "django.core.mail.backends.smtp.EmailBackend",
        )
        self.redirect_to = list(
            getattr(settings, "EMAIL_REDIRECT_ALL_TO", []) or []
        )
        self.subject_prefix = getattr(
            settings,
            "EMAIL_STAGING_SUBJECT_PREFIX",
            "[LEFTRACK STAGING]",
        ).strip()

        if not self.redirect_to:
            raise ImproperlyConfigured(
                "EMAIL_REDIRECT_ALL_TO deve contenere almeno un indirizzo "
                "quando si usa StagingRedirectEmailBackend."
            )

        if self.real_backend_path == settings.EMAIL_BACKEND:
            raise ImproperlyConfigured(
                "EMAIL_REAL_BACKEND non può coincidere con EMAIL_BACKEND."
            )

        backend_class = import_string(self.real_backend_path)
        self.connection = backend_class(
            fail_silently=fail_silently,
            **kwargs,
        )

    def open(self):
        return self.connection.open()

    def close(self):
        return self.connection.close()

    @staticmethod
    def _safe_recipient_label(recipients: list[str]) -> str:
        cleaned = [
            str(value).replace("\r", " ").replace("\n", " ").strip()
            for value in recipients
            if str(value).strip()
        ]
        return ", ".join(cleaned)

    def send_messages(self, email_messages):
        if not email_messages:
            return 0

        originals = []
        try:
            for message in email_messages:
                original_to = list(message.to or [])
                original_cc = list(message.cc or [])
                original_bcc = list(message.bcc or [])
                original_subject = message.subject or ""
                original_recipients = original_to + original_cc + original_bcc

                originals.append(
                    (
                        message,
                        original_to,
                        original_cc,
                        original_bcc,
                        original_subject,
                    )
                )

                message.to = list(self.redirect_to)
                message.cc = []
                message.bcc = []

                label = self._safe_recipient_label(original_recipients)
                prefix = self.subject_prefix
                if label:
                    prefix = f"{prefix} [dest. originale: {label}]"
                message.subject = f"{prefix} {original_subject}".strip()

            return self.connection.send_messages(email_messages)
        finally:
            # Ripristina gli oggetti EmailMessage: chi li ha creati continua a
            # vedere i destinatari e l'oggetto originali anche dopo l'invio.
            for (
                message,
                original_to,
                original_cc,
                original_bcc,
                original_subject,
            ) in originals:
                message.to = original_to
                message.cc = original_cc
                message.bcc = original_bcc
                message.subject = original_subject
