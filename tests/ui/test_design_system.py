from pathlib import Path

from django.conf import settings
from django.contrib.staticfiles import finders
from django.test import SimpleTestCase


class DesignSystemTests(SimpleTestCase):
    def test_design_system_static_assets_exist(self):
        for asset in (
            "css/tokens.css",
            "css/app.css",
            "css/components.css",
            "css/forms.css",
            "css/tables.css",
            "css/responsive.css",
        ):
            with self.subTest(asset=asset):
                self.assertTrue(finders.find(asset), asset)

    def test_base_loads_design_system_in_order(self):
        content = (Path(settings.BASE_DIR) / "templates" / "base.html").read_text()
        assets = [
            "css/tokens.css",
            "css/app.css",
            "css/components.css",
            "css/forms.css",
            "css/tables.css",
            "css/responsive.css",
        ]
        positions = [content.index(asset) for asset in assets]
        self.assertEqual(positions, sorted(positions))

    def test_tokens_define_core_semantics(self):
        path = finders.find("css/tokens.css")
        content = Path(path).read_text()
        for token in (
            "--lef-success",
            "--lef-warning",
            "--lef-danger",
            "--lef-info",
            "--space-4",
            "--radius-md",
            "--focus-ring",
        ):
            with self.subTest(token=token):
                self.assertIn(token, content)

    def test_component_library_contains_required_variants(self):
        path = finders.find("css/components.css")
        content = Path(path).read_text()
        for selector in (
            ".button-primary",
            ".button-secondary",
            ".button-danger",
            ".badge-warning",
            ".metric-card",
            ".message-error",
        ):
            with self.subTest(selector=selector):
                self.assertIn(selector, content)

    def test_forms_and_tables_have_error_and_numeric_states(self):
        forms = Path(finders.find("css/forms.css")).read_text()
        tables = Path(finders.find("css/tables.css")).read_text()
        self.assertIn('aria-invalid="true"', forms)
        self.assertIn(".field-error", forms)
        self.assertIn(".table-numeric", tables)
        self.assertIn("font-variant-numeric: tabular-nums", tables)
