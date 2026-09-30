from datetime import date

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.contrib.staticfiles import finders
from django.template.loader import get_template, render_to_string
from django.test import RequestFactory, SimpleTestCase, TestCase
from django.urls import resolve, reverse

from apps.operations.templatetags.navigation import (
    build_navigation_data,
    has_pm_access,
)
from apps.projects.models import Assegnazione, Cliente, Commessa

User = get_user_model()


class NavigationDataTests(SimpleTestCase):
    def test_navigation_data_exposes_current_page_label(self):
        match = resolve(reverse("timesheets:ore-create"))
        data = build_navigation_data(match)

        self.assertEqual(data["section"], "ore")
        self.assertEqual(data["current_label"], "Inserisci ore")

    def test_base_template_and_static_assets_exist(self):
        self.assertIsNotNone(get_template("base.html"))
        self.assertTrue(finders.find("css/app.css"))
        self.assertTrue(finders.find("js/app.js"))

    def test_guest_layout_renders_without_sidebar(self):
        request = RequestFactory().get("/")
        request.user = AnonymousUser()

        html = render_to_string(
            "base.html",
            {"request": request},
        )

        self.assertIn('class="guest-shell"', html)
        self.assertNotIn('id="app-sidebar"', html)


class AuthenticatedLayoutTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.admin = User.objects.create_user(
            email="admin-test@example.com",
            password="Password-test-123",
            ruolo=User.Ruolo.ADMIN,
            is_active=True,
            deve_cambiare_password=False,
        )
        self.consulente = User.objects.create_user(
            email="pm-test@example.com",
            password="Password-test-123",
            ruolo=User.Ruolo.CONSULENTE,
            is_active=True,
            deve_cambiare_password=False,
        )

        cliente = Cliente.objects.create(
            ragione_sociale="Cliente Test",
            partita_iva="17000000001",
        )
        commessa = Commessa.objects.create(
            cliente=cliente,
            codice="TEST",
            descrizione="Collaudo interfaccia",
            ore_budget=40,
            data_inizio=date(2026, 1, 1),
        )
        Assegnazione.objects.create(
            consulente=self.consulente,
            commessa=commessa,
            ore_previste=20,
            ruolo_commessa=Assegnazione.Ruolo.PROJECT_MANAGER,
            stato=Assegnazione.Stato.ATTIVA,
            data_inizio=date(2026, 1, 1),
        )

    def render_base(self, user):
        request = self.factory.get(reverse("home"))
        request.user = user
        request.resolver_match = resolve(reverse("home"))
        return render_to_string(
            "base.html",
            {"request": request, "user": user},
        )

    def test_admin_layout_contains_grouped_sidebar(self):
        html = self.render_base(self.admin)

        self.assertIn('id="app-sidebar"', html)
        self.assertIn("Portafoglio", html)
        self.assertIn("Organizzazione", html)
        self.assertIn("Controllo", html)
        self.assertIn("Dashboard", html)
        self.assertIn('data-sidebar-toggle', html)

    def test_pm_link_is_visible_only_with_active_pm_assignment(self):
        self.assertTrue(has_pm_access(self.consulente))

        html = self.render_base(self.consulente)
        self.assertIn("Dashboard", html)

        Assegnazione.objects.filter(
            consulente=self.consulente
        ).update(stato=Assegnazione.Stato.CONCLUSA)

        self.assertFalse(has_pm_access(self.consulente))
        html = self.render_base(self.consulente)
        self.assertNotIn("Dashboard", html)
