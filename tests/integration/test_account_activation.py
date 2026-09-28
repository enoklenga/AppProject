from urllib.parse import urlparse
from unittest.mock import patch

from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.forms import ConsulenteCreateForm
from apps.accounts.models import User


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    DEFAULT_FROM_EMAIL="noreply@nokihub.test",
    SITE_URL="https://nokihub.test",
)
class AccountActivationWorkflowTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            email="admin-activation@example.com",
            password="Admin-Password-123!",
            ruolo=User.Ruolo.ADMIN,
            deve_cambiare_password=False,
        )
        self.client.force_login(self.admin)

    def _create_consulente_via_ui(self, email="nuovo.consulente@example.com"):
        return self.client.post(
            reverse("accounts:consulente-create"),
            {
                "email": email,
                "first_name": "Nuovo",
                "last_name": "Consulente",
                "telefono": "+39 040 0000000",
                "ruolo": User.Ruolo.CONSULENTE,
            },
        )

    def test_form_creazione_non_chiede_password_ne_stato_attivo(self):
        form = ConsulenteCreateForm()
        self.assertNotIn("password1", form.fields)
        self.assertNotIn("password2", form.fields)
        self.assertNotIn("is_active", form.fields)

    def test_creazione_genera_account_inattivo_e_invia_invito(self):
        response = self._create_consulente_via_ui()

        self.assertRedirects(
            response,
            reverse("accounts:consulente-list"),
            fetch_redirect_response=False,
        )
        user = User.objects.get(email="nuovo.consulente@example.com")
        self.assertFalse(user.is_active)
        self.assertFalse(user.has_usable_password())
        self.assertTrue(user.deve_cambiare_password)
        self.assertIsNotNone(user.invito_inviato_il)

        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        self.assertEqual(message.to, [user.email])
        self.assertIn("Attiva il tuo account LEFTRACK", message.subject)
        self.assertIn("https://nokihub.test/account/attiva/", message.body)

    def test_link_invito_permette_di_scegliere_password_e_attiva_account(self):
        self._create_consulente_via_ui("attivazione@example.com")
        user = User.objects.get(email="attivazione@example.com")

        activation_url = next(
            line.strip()
            for line in mail.outbox[0].body.splitlines()
            if line.strip().startswith("https://nokihub.test/account/attiva/")
        )
        activation_path = urlparse(activation_url).path

        # Il link viene aperto dal consulente senza una sessione Admin attiva.
        self.client.logout()
        response = self.client.get(activation_path)
        self.assertEqual(response.status_code, 302)
        self.assertIn("set-password", response.url)

        response = self.client.post(
            response.url,
            {
                "new_password1": "Password-Nokihub-456!",
                "new_password2": "Password-Nokihub-456!",
            },
        )
        self.assertRedirects(
            response,
            reverse("account_activation_complete"),
            fetch_redirect_response=False,
        )

        user.refresh_from_db()
        self.assertTrue(user.is_active)
        self.assertTrue(user.has_usable_password())
        self.assertTrue(user.check_password("Password-Nokihub-456!"))
        self.assertFalse(user.deve_cambiare_password)
        self.assertIsNotNone(user.attivato_il)


    def test_modifica_email_di_account_pendente_reinvia_invito_al_nuovo_indirizzo(self):
        self._create_consulente_via_ui("vecchia@example.com")
        user = User.objects.get(email="vecchia@example.com")
        mail.outbox.clear()

        response = self.client.post(
            reverse("accounts:consulente-update", args=[user.pk]),
            {
                "email": "nuova@example.com",
                "first_name": user.first_name,
                "last_name": user.last_name,
                "telefono": user.telefono,
                "ruolo": user.ruolo,
                "deve_cambiare_password": "on",
            },
        )

        self.assertRedirects(
            response,
            reverse("accounts:consulente-list"),
            fetch_redirect_response=False,
        )
        user.refresh_from_db()
        self.assertEqual(user.email, "nuova@example.com")
        self.assertIsNotNone(user.invito_inviato_il)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["nuova@example.com"])

    def test_reinvio_invito_per_account_pendente(self):
        user = User(
            email="pending@example.com",
            first_name="Pending",
            last_name="User",
            ruolo=User.Ruolo.CONSULENTE,
            is_active=False,
            deve_cambiare_password=True,
        )
        user.set_unusable_password()
        user.save()

        response = self.client.post(
            reverse("accounts:consulente-resend-invite", args=[user.pk])
        )

        self.assertRedirects(
            response,
            reverse("accounts:consulente-list"),
            fetch_redirect_response=False,
        )
        user.refresh_from_db()
        self.assertIsNotNone(user.invito_inviato_il)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("account/attiva/", mail.outbox[0].body)

    def test_reinvio_invito_non_si_applica_ad_account_gia_attivo(self):
        user = User.objects.create_user(
            email="active@example.com",
            password="Password-Attiva-123!",
            ruolo=User.Ruolo.CONSULENTE,
            is_active=True,
            deve_cambiare_password=False,
        )

        response = self.client.post(
            reverse("accounts:consulente-resend-invite", args=[user.pk])
        )

        self.assertRedirects(
            response,
            reverse("accounts:consulente-list"),
            fetch_redirect_response=False,
        )
        self.assertEqual(len(mail.outbox), 0)

    def test_account_pendente_non_puo_essere_riattivato_manualmente(self):
        user = User(
            email="pending-toggle@example.com",
            ruolo=User.Ruolo.CONSULENTE,
            is_active=False,
        )
        user.set_unusable_password()
        user.save()

        self.client.post(
            reverse("accounts:consulente-toggle-active", args=[user.pk])
        )
        user.refresh_from_db()
        self.assertFalse(user.is_active)
        self.assertFalse(user.has_usable_password())

    def test_password_dimenticata_continua_a_funzionare_dopo_attivazione(self):
        user = User.objects.create_user(
            email="reset-after-activation@example.com",
            password="Password-Attiva-123!",
            ruolo=User.Ruolo.CONSULENTE,
            is_active=True,
            deve_cambiare_password=False,
        )
        mail.outbox.clear()

        response = self.client.post(
            reverse("password_reset"),
            {"email": user.email},
        )

        self.assertRedirects(
            response,
            reverse("password_reset_done"),
            fetch_redirect_response=False,
        )
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("recupero della password", mail.outbox[0].body.lower())

    @patch(
        "apps.accounts.views.send_account_activation_email",
        side_effect=RuntimeError("smtp down"),
    )
    def test_errore_smtp_non_perde_l_account_e_lascia_reinvio_disponibile(self, _send):
        response = self._create_consulente_via_ui("smtp-fail@example.com")

        self.assertEqual(response.status_code, 302)
        user = User.objects.get(email="smtp-fail@example.com")
        self.assertFalse(user.is_active)
        self.assertFalse(user.has_usable_password())
        self.assertIsNone(user.invito_inviato_il)

        list_response = self.client.get(reverse("accounts:consulente-list"))
        self.assertContains(list_response, "Invito da reinviare")
        self.assertContains(list_response, "Reinvia invito")
