from pathlib import Path

from django.conf import settings
from django.contrib.staticfiles import finders
from django.test import SimpleTestCase


BASE_DIR = Path(settings.BASE_DIR)


class UxOperativaTests(SimpleTestCase):
    def test_static_assets_exist(self):
        for asset in (
            "css/ux.css",
            "js/app.js",
        ):
            self.assertTrue(finders.find(asset), asset)

    def test_base_loads_ux_layer_in_correct_order(self):
        source = (BASE_DIR / "templates" / "base.html").read_text(encoding="utf-8")
        self.assertIn("css/accessibility.css", source)
        self.assertIn("css/ux.css", source)
        self.assertIn("css/responsive.css", source)
        self.assertLess(source.index("css/accessibility.css"), source.index("css/ux.css"))
        self.assertLess(source.index("css/ux.css"), source.index("css/responsive.css"))

    def test_base_exposes_accessible_confirmation_dialog(self):
        source = (BASE_DIR / "templates" / "base.html").read_text(encoding="utf-8")
        self.assertIn('id="ux-confirm-dialog"', source)
        self.assertIn('aria-labelledby="ux-confirm-title"', source)
        self.assertIn('aria-describedby="ux-confirm-message"', source)
        self.assertIn('data-confirm-accept', source)
        self.assertIn('data-confirm-cancel', source)
        self.assertIn('id="ux-live-region"', source)

    def test_javascript_prevents_duplicate_submissions(self):
        source = (BASE_DIR / "static" / "js" / "app.js").read_text(encoding="utf-8")
        self.assertIn('dataset.uxSubmitting', source)
        self.assertIn('aria-busy', source)
        self.assertIn('is-loading', source)
        self.assertIn('La richiesta è già in corso.', source)

    def test_javascript_confirms_destructive_actions(self):
        source = (BASE_DIR / "static" / "js" / "app.js").read_text(encoding="utf-8")
        self.assertIn('button-danger', source)
        self.assertIn('link-button', source)
        self.assertIn('data-confirm-message', source)
        self.assertIn('showModal', source)
        self.assertIn('requestSubmit', source)

    def test_javascript_tracks_unsaved_changes(self):
        source = (BASE_DIR / "static" / "js" / "app.js").read_text(encoding="utf-8")
        self.assertIn('beforeunload', source)
        self.assertIn('data-no-unsaved-warning', source)
        self.assertIn('Modifiche non salvate', source)
        self.assertIn('ux-unsaved-indicator', source)

    def test_javascript_improves_server_side_validation_feedback(self):
        source = (BASE_DIR / "static" / "js" / "app.js").read_text(encoding="utf-8")
        self.assertIn('.errorlist', source)
        self.assertIn('aria-invalid', source)
        self.assertIn('aria-describedby', source)
        self.assertIn('scrollIntoView', source)

    def test_ux_css_covers_dialog_loading_errors_and_empty_states(self):
        source = (BASE_DIR / "static" / "css" / "ux.css").read_text(encoding="utf-8")
        for marker in (
            ".ux-dialog",
            ".is-loading",
            ".field.has-error",
            ".ux-unsaved-indicator",
            ".empty-state",
            "prefers-reduced-motion",
        ):
            self.assertIn(marker, source)
