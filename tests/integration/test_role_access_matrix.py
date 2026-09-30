from datetime import date

from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import User
from apps.projects.models import Cliente, Commessa


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    DEFAULT_FROM_EMAIL="noreply@leftrack.test",
    SITE_URL="https://leftrack.test",
)
class RoleAccessMatrixTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            email="admin-matrix@example.com",
            password="Admin-Password-123!",
            ruolo=User.Ruolo.ADMIN,
            is_active=True,
            deve_cambiare_password=False,
        )
        self.commerciale = User.objects.create_user(
            email="commerciale@example.com",
            password="Password-123!",
            ruolo=User.Ruolo.COMMERCIALE,
            is_active=True,
            deve_cambiare_password=False,
        )
        self.dg = User.objects.create_user(
            email="dg@example.com",
            password="Password-123!",
            ruolo=User.Ruolo.DIREZIONE_GENERALE,
            is_active=True,
            deve_cambiare_password=False,
        )
        self.consulente = User.objects.create_user(
            email="consulente-matrix@example.com",
            password="Password-123!",
            ruolo=User.Ruolo.CONSULENTE,
            is_active=True,
            deve_cambiare_password=False,
        )
        self.responsabile = User.objects.create_user(
            email="responsabile@example.com",
            password="Password-123!",
            ruolo=User.Ruolo.RESPONSABILE_CONSULENZA,
            is_active=True,
            deve_cambiare_password=False,
        )
        self.amministrazione = User.objects.create_user(
            email="amministrazione@example.com",
            password="Password-123!",
            ruolo=User.Ruolo.AMMINISTRAZIONE,
            is_active=True,
            deve_cambiare_password=False,
        )
        self.cliente = Cliente.objects.create(
            ragione_sociale="Cliente Matrix",
            partita_iva="11111111111",
        )
        self.commessa = Commessa.objects.create(
            cliente=self.cliente,
            codice="MATRIX-001",
            descrizione="Test matrice autorizzativa",
            data_inizio=date(2026, 9, 1),
            data_fine_prevista=date(2026, 12, 31),
            ore_budget=80,
        )

    def test_admin_puo_creare_altro_admin_da_interfaccia_con_invito(self):
        self.client.force_login(self.admin)
        response = self.client.post(
            reverse("accounts:consulente-create"),
            {
                "email": "secondo.admin@example.com",
                "first_name": "Secondo",
                "last_name": "Admin",
                "telefono": "",
                "ruolo": User.Ruolo.ADMIN,
            },
        )
        self.assertEqual(response.status_code, 302)
        nuovo = User.objects.get(email="secondo.admin@example.com")
        self.assertEqual(nuovo.ruolo, User.Ruolo.ADMIN)
        self.assertFalse(nuovo.is_active)
        self.assertFalse(nuovo.has_usable_password())
        self.assertFalse(nuovo.is_staff)
        self.assertFalse(nuovo.is_superuser)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("account/attiva/", mail.outbox[0].body)

    def test_ultimo_admin_attivo_non_puo_disattivare_se_stesso(self):
        self.client.force_login(self.admin)
        response = self.client.post(
            reverse("accounts:consulente-toggle-active", args=[self.admin.pk])
        )
        self.assertEqual(response.status_code, 302)
        self.admin.refresh_from_db()
        self.assertTrue(self.admin.is_active)
        self.assertEqual(self.admin.ruolo, User.Ruolo.ADMIN)

    def test_admin_non_puo_auto_retrocedersi(self):
        self.client.force_login(self.admin)
        response = self.client.post(
            reverse("accounts:consulente-update", args=[self.admin.pk]),
            {
                "email": self.admin.email,
                "first_name": "Admin",
                "last_name": "Matrix",
                "telefono": "",
                "ruolo": User.Ruolo.CONSULENTE,
                "deve_cambiare_password": "",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.admin.refresh_from_db()
        self.assertEqual(self.admin.ruolo, User.Ruolo.ADMIN)

    def test_commerciale_gestisce_portafoglio_ma_non_operativita(self):
        self.client.force_login(self.commerciale)
        for name in (
            "projects:cliente-list",
            "projects:cliente-create",
            "projects:commessa-list",
            "projects:commessa-create",
            "documents:document-list",
        ):
            self.assertEqual(self.client.get(reverse(name)).status_code, 200, name)

        self.assertEqual(
            self.client.get(
                reverse("projects:commessa-teamwork", args=[self.commessa.pk])
            ).status_code,
            200,
        )
        for name in (
            "accounts:consulente-list",
            "timesheets:ore-list",
            "planning:pianificazione-list",
            "operations:dashboard-admin",
            "operations:audit-list",
        ):
            self.assertEqual(self.client.get(reverse(name)).status_code, 403, name)

    def test_direzione_ha_accesso_direzionale_in_sola_lettura(self):
        self.client.force_login(self.dg)
        for name in (
            "projects:cliente-list",
            "projects:commessa-list",
            "documents:document-list",
            "tasks:task-list",
            "accounts:skill-matrix",
            "operations:dashboard-admin",
            "operations:report-mensile",
            "operations:audit-list",
            "planning:pianificazione-list",
        ):
            self.assertEqual(self.client.get(reverse(name)).status_code, 200, name)

        self.assertEqual(
            self.client.get(
                reverse("projects:commessa-teamwork", args=[self.commessa.pk])
            ).status_code,
            200,
        )

        for name in (
            "projects:cliente-create",
            "projects:commessa-create",
            "accounts:consulente-list",
            "timesheets:ore-list",
        ):
            self.assertEqual(self.client.get(reverse(name)).status_code, 403, name)

    def test_consulente_non_ottiene_visibilita_globale_portafoglio(self):
        self.client.force_login(self.consulente)
        self.assertEqual(self.client.get(reverse("projects:cliente-list")).status_code, 403)
        self.assertEqual(self.client.get(reverse("projects:commessa-list")).status_code, 403)
        self.assertEqual(self.client.get(reverse("timesheets:ore-list")).status_code, 200)
        self.assertEqual(self.client.get(reverse("planning:pianificazione-list")).status_code, 200)

    def test_amministrazione_gestisce_tutto_tranne_la_piattaforma(self):
        """Revisione 29/09/2026: l'Amministrazione gestisce tutto ciò che
        gestisce l'Admin; resta esclusa solo la piattaforma (account e ruoli)."""
        self.client.force_login(self.amministrazione)
        for name in (
            "home",
            "timesheets:ore-list",
            "timesheets:spesa-list",
            "projects:tariffa-list",
            "operations:periodo-detail",
            "operations:report-mensile",
            "projects:cliente-list",
            "projects:commessa-list",
            "projects:assegnazione-list",
            "operations:dashboard-admin",
            "operations:promemoria",
            "operations:importazione-list",
            "operations:audit-list",
            "accounts:consulente-list",
            "accounts:business-unit-list",
            "accounts:business-unit-create",
            "accounts:skill-list",
            "projects:cliente-create",
            "projects:commessa-create",
            "projects:assegnazione-create",
            "planning:pianificazione-list",
        ):
            self.assertEqual(self.client.get(reverse(name)).status_code, 200, name)

        # Piattaforma: account, ruoli e inviti restano all'Admin LEF.
        self.assertEqual(
            self.client.get(reverse("accounts:consulente-create")).status_code, 403
        )
        self.assertEqual(
            self.client.get(
                reverse("accounts:consulente-update", args=[self.consulente.pk])
            ).status_code,
            403,
        )

    def test_responsabile_senza_business_unit_opera_come_consulente(self):
        """Il ruolo da solo non concede la gestione: serve la nomina su una BU."""
        self.client.force_login(self.responsabile)
        for name in (
            "home",
            "planning:pianificazione-list",
            "timesheets:ore-list",
            "timesheets:spesa-list",
        ):
            self.assertEqual(self.client.get(reverse(name)).status_code, 200, name)
        for name in (
            "accounts:consulente-list",
            "accounts:consulente-create",
            "operations:report-mensile",
            "projects:commessa-list",
        ):
            self.assertEqual(self.client.get(reverse(name)).status_code, 403, name)

    def test_profili_readonly_non_vedono_colonna_azioni(self):
        self.client.force_login(self.dg)
        for url in (
            reverse("projects:cliente-list"),
            reverse("projects:commessa-list"),
            reverse("accounts:skill-matrix"),
            reverse("planning:pianificazione-list"),
            reverse("tasks:task-list"),
            reverse("projects:commessa-teamwork", args=[self.commessa.pk]),
        ):
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200, url)
            self.assertNotContains(response, ">Azioni<", html=False)
            self.assertNotContains(response, "Sola lettura")
