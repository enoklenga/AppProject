from pathlib import Path

from django.conf import settings
from django.contrib.staticfiles import finders
from django.test import SimpleTestCase


BASE_DIR = Path(settings.BASE_DIR)


class ResponsiveAccessibilityTests(SimpleTestCase):
    def test_static_assets_exist(self):
        for asset in (
            "css/accessibility.css",
            "css/responsive.css",
            "css/dashboard.css",
            "js/app.js",
            "js/dashboard.js",
        ):
            self.assertTrue(finders.find(asset), asset)

    def test_base_loads_accessibility_before_responsive(self):
        source = (BASE_DIR / "templates" / "base.html").read_text(encoding="utf-8")
        self.assertIn("css/accessibility.css", source)
        self.assertIn("css/responsive.css", source)
        self.assertLess(source.index("css/accessibility.css"), source.index("css/responsive.css"))
        self.assertIn('class="skip-link"', source)
        self.assertIn('id="contenuto-principale"', source)

    def test_mobile_navigation_has_keyboard_support(self):
        source = (BASE_DIR / "static" / "js" / "app.js").read_text(encoding="utf-8")
        self.assertIn('event.key === "Escape"', source)
        self.assertIn('event.key !== "Tab"', source)
        self.assertIn('aria-hidden', source)
        self.assertIn('aria-expanded', source)
        self.assertIn('table-wrapper', source)
        self.assertIn('tabindex', source)

    def test_accessibility_css_covers_user_preferences_and_focus(self):
        source = (BASE_DIR / "static" / "css" / "accessibility.css").read_text(encoding="utf-8")
        self.assertIn(":focus-visible", source)
        self.assertIn("prefers-reduced-motion", source)
        self.assertIn("prefers-contrast: more", source)
        self.assertIn("forced-colors: active", source)
        self.assertIn("min-height: 44px", source)

    def test_responsive_css_has_core_breakpoints(self):
        source = (BASE_DIR / "static" / "css" / "responsive.css").read_text(encoding="utf-8")
        for breakpoint in ("1080px", "900px", "680px", "560px", "380px"):
            self.assertIn(breakpoint, source)
        self.assertIn("overflow: hidden", source)
        self.assertIn("overflow-scrolling: touch", source)

    def test_dashboard_charts_have_accessible_descriptions(self):
        source = (BASE_DIR / "static" / "js" / "dashboard.js").read_text(encoding="utf-8")
        self.assertIn('createSvg("title"', source)
        self.assertIn('createSvg("desc"', source)
        self.assertIn("aria-labelledby", source)
        self.assertIn('role", "group"', source)

    def test_dashboard_tables_have_semantics(self):
        admin = (BASE_DIR / "templates" / "operations" / "dashboard_admin.html").read_text(encoding="utf-8")
        pm = (BASE_DIR / "templates" / "operations" / "dashboard_pm.html").read_text(encoding="utf-8")
        self.assertIn("<caption", admin)
        self.assertIn('scope="col"', admin)
        self.assertIn("<caption", pm)
        self.assertIn('scope="col"', pm)
