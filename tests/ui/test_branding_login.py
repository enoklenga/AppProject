from pathlib import Path

from django.conf import settings
from django.contrib.staticfiles import finders
from django.test import SimpleTestCase


BASE_DIR = Path(settings.BASE_DIR)


class BrandingLoginTests(SimpleTestCase):
    def test_branding_static_files_exist(self):
        self.assertTrue(finders.find("css/branding.css"))
        self.assertTrue(finders.find("css/login.css"))

    def test_base_loads_branding_styles(self):
        content = (BASE_DIR / "templates" / "base.html").read_text(encoding="utf-8")
        self.assertIn("css/branding.css", content)
        self.assertIn("css/login.css", content)
        self.assertIn("brand-logo-slot-sidebar", content)
        self.assertIn("images/branding/leftrack-mark.png", content)

    def test_base_exposes_body_class_hook(self):
        content = (BASE_DIR / "templates" / "base.html").read_text(encoding="utf-8")
        self.assertEqual(content.count("{% block body_class %}"), 1)
        self.assertEqual(content.count("{% block content %}"), 1)

    def test_login_template_has_branding_structure(self):
        content = (BASE_DIR / "templates" / "registration" / "login.html").read_text(encoding="utf-8")
        self.assertIn("{% block body_class %}page-login{% endblock %}", content)
        self.assertIn("auth-brand", content)
        self.assertIn("images/branding/leftrack-mark.png", content)
        self.assertIn("auth-login", content)
        self.assertIn("{% csrf_token %}", content)


    def test_login_css_points_to_expected_background_asset(self):
        content = (
            BASE_DIR
            / "static"
            / "css"
            / "login.css"
        ).read_text(encoding="utf-8")
        self.assertIn(".auth-login", content)
        self.assertIn("linear-gradient", content)

    def test_login_does_not_add_reset_action(self):
        content = (BASE_DIR / "templates" / "registration" / "login.html").read_text(encoding="utf-8").lower()
        self.assertNotIn(">reset<", content)
