from django.test import SimpleTestCase
from django.urls import resolve, reverse

from apps.operations.templatetags.navigation import (
    build_navigation_data,
    section_for_match,
)


class NavigationTests(SimpleTestCase):
    def test_home_is_active_on_home_route(self):
        match = resolve(reverse("home"))
        self.assertEqual(section_for_match(match), "home")

    def test_ore_remains_active_on_create_page(self):
        match = resolve(reverse("timesheets:ore-create"))
        self.assertEqual(section_for_match(match), "ore")

    def test_spese_remains_active_on_update_page(self):
        match = resolve(
            "/timesheet/spese/00000000-0000-0000-0000-000000000001/modifica/"
        )
        self.assertEqual(section_for_match(match), "spese")

    def test_project_subpages_keep_the_correct_active_section(self):
        routes = {
            "projects:cliente-create": "clienti",
            "projects:commessa-create": "commesse",
            "projects:assegnazione-create": "assegnazioni",
            "projects:tariffa-create": "tariffe",
        }
        for route_name, expected_section in routes.items():
            with self.subTest(route_name=route_name):
                match = resolve(reverse(route_name))
                self.assertEqual(
                    section_for_match(match),
                    expected_section,
                )

    def test_import_detail_returns_to_import_list(self):
        match = resolve(
            "/controllo/importazioni/"
            "00000000-0000-0000-0000-000000000001/"
        )
        data = build_navigation_data(match)

        self.assertEqual(data["section"], "importazioni")
        self.assertEqual(
            data["back_url"],
            reverse("operations:importazione-list"),
        )
        self.assertEqual(
            data["breadcrumbs"][-1]["label"],
            "Dettaglio importazione",
        )

    def test_pm_dashboard_returns_to_home(self):
        match = resolve(reverse("operations:dashboard-pm"))
        data = build_navigation_data(match)

        self.assertEqual(data["section"], "dashboard")
        self.assertEqual(data["back_url"], reverse("home"))
        self.assertEqual(data["back_label"], "Torna alla Home")

    def test_top_level_page_returns_to_home(self):
        match = resolve(reverse("timesheets:ore-list"))
        data = build_navigation_data(match)

        self.assertEqual(data["back_url"], reverse("home"))
        self.assertEqual(data["back_label"], "Torna alla Home")
