from django.core import mail
from django.core.exceptions import ImproperlyConfigured
from django.core.mail import EmailMessage
from django.test import SimpleTestCase, override_settings

from apps.common.email_backend import StagingRedirectEmailBackend


class StagingRedirectEmailBackendTests(SimpleTestCase):
    @override_settings(
        EMAIL_BACKEND="apps.common.email_backend.StagingRedirectEmailBackend",
        EMAIL_REAL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
        EMAIL_REDIRECT_ALL_TO=["tester@example.com"],
        EMAIL_STAGING_SUBJECT_PREFIX="[STAGING]",
    )
    def test_redirects_all_recipients_and_preserves_original_message(self):
        message = EmailMessage(
            subject="Invito account",
            body="Corpo",
            from_email="nokihub@example.com",
            to=["consulente@example.com"],
            cc=["pm@example.com"],
            bcc=["audit@example.com"],
        )

        backend = StagingRedirectEmailBackend()
        sent = backend.send_messages([message])

        self.assertEqual(sent, 1)
        self.assertEqual(len(mail.outbox), 1)
        delivered = mail.outbox[0]
        self.assertEqual(delivered.to, ["tester@example.com"])
        self.assertEqual(delivered.cc, [])
        self.assertEqual(delivered.bcc, [])
        self.assertIn("[STAGING]", delivered.subject)
        self.assertIn("consulente@example.com", delivered.subject)
        self.assertIn("pm@example.com", delivered.subject)
        self.assertIn("audit@example.com", delivered.subject)

        # L'oggetto originale viene ripristinato dopo l'invio.
        self.assertEqual(message.to, ["consulente@example.com"])
        self.assertEqual(message.cc, ["pm@example.com"])
        self.assertEqual(message.bcc, ["audit@example.com"])
        self.assertEqual(message.subject, "Invito account")

    @override_settings(
        EMAIL_BACKEND="apps.common.email_backend.StagingRedirectEmailBackend",
        EMAIL_REAL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
        EMAIL_REDIRECT_ALL_TO=[],
    )
    def test_requires_test_recipient(self):
        with self.assertRaises(ImproperlyConfigured):
            StagingRedirectEmailBackend()
