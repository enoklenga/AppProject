from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import RequestFactory, SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import User
from apps.common.export_security import spreadsheet_safe
from apps.common.request_security import get_client_ip, safe_internal_redirect
from apps.documents.services import _valida_file
from apps.timesheets.views import _ApprovazioneBaseView


class Step3SecurityUnitTests(SimpleTestCase):
    def test_spreadsheet_formula_is_forced_to_text(self):
        self.assertEqual(spreadsheet_safe("=1+1"), "'=1+1")
        self.assertEqual(spreadsheet_safe("  @SUM(A1:A2)"), "'  @SUM(A1:A2)")
        self.assertEqual(spreadsheet_safe("testo normale"), "testo normale")
        self.assertEqual(spreadsheet_safe(12), 12)

    def test_documento_rinominato_pdf_ma_eseguibile_viene_rifiutato(self):
        fake = SimpleUploadedFile(
            "contratto.pdf",
            b"MZ" + b"\x00" * 100,
            content_type="application/pdf",
        )
        with self.assertRaises(ValidationError):
            _valida_file(fake)

    def test_documento_pdf_reale_supera_la_validazione_contenuto(self):
        fake = SimpleUploadedFile(
            "contratto.pdf",
            b"%PDF-1.7\n%test\n",
            content_type="application/pdf",
        )
        _valida_file(fake)

    @override_settings(
        API_TRUST_X_FORWARDED_FOR=True,
        REST_FRAMEWORK={"NUM_PROXIES": 1},
    )
    def test_ip_proxy_ignora_valore_spoofato_a_sinistra(self):
        request = RequestFactory().get(
            "/",
            REMOTE_ADDR="10.0.0.10",
            HTTP_X_FORWARDED_FOR="198.51.100.99, 203.0.113.7",
        )
        self.assertEqual(get_client_ip(request), "203.0.113.7")

    def test_redirect_esterno_viene_rifiutato(self):
        request = RequestFactory().post("/", {"next": "https://evil.example/"})
        request.META["HTTP_HOST"] = "testserver"
        self.assertIsNone(
            safe_internal_redirect(request, "https://evil.example/")
        )

        response = _ApprovazioneBaseView()._redirect(
            request,
            SimpleNamespace(data=date(2026, 9, 1)),
        )
        self.assertTrue(response.url.startswith(reverse("operations:periodo-detail")))


class Step3RuntimeSecurityTests(TestCase):
    password = "Password-test-Step3-123"

    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(
            email="step3@example.com",
            password=self.password,
            ruolo=User.Ruolo.CONSULENTE,
            is_active=True,
        )

    @override_settings(
        WEB_LOGIN_RATE_LIMIT=2,
        WEB_LOGIN_IP_RATE_LIMIT=100,
        WEB_LOGIN_RATE_WINDOW_SECONDS=300,
        API_TRUST_X_FORWARDED_FOR=False,
        CACHES={
            "default": {
                "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
                "LOCATION": "step3-login-tests",
            }
        },
    )
    def test_login_web_viene_limitato_dopo_errori_ripetuti(self):
        payload = {
            "username": self.user.email,
            "password": "Password-sbagliata",
        }
        first = self.client.post(reverse("login"), payload)
        second = self.client.post(reverse("login"), payload)
        third = self.client.post(reverse("login"), payload)

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(third.status_code, 429)

    def test_readiness_non_espone_dettaglio_eccezione(self):
        with patch(
            "config.urls.connection.cursor",
            side_effect=RuntimeError("password=db-secret host=internal-db"),
        ):
            response = self.client.get(reverse("health_ready"))

        self.assertEqual(response.status_code, 503)
        payload = response.json()
        self.assertEqual(payload["database"], "unavailable")
        self.assertNotIn("detail", payload)
        self.assertEqual(response["Cache-Control"], "no-store")


class Step3PackagingSecurityTests(SimpleTestCase):
    def test_container_applicativo_non_gira_come_root(self):
        root = Path(__file__).resolve().parents[2]
        dockerfile = (root / "deploy/docker/Dockerfile").read_text(encoding="utf-8")
        self.assertIn("USER nokihub", dockerfile)

    def test_compose_inizializza_permessi_volumi_prima_del_web(self):
        root = Path(__file__).resolve().parents[2]
        compose = (root / "docker-compose.prod.yml").read_text(encoding="utf-8")
        self.assertIn("init_permissions:", compose)
        self.assertIn('user: "0:0"', compose)
        self.assertIn("condition: service_completed_successfully", compose)

    def test_nginx_non_serve_private_media(self):
        root = Path(__file__).resolve().parents[2]
        nginx = (root / "deploy/nginx/default.conf").read_text(encoding="utf-8")
        self.assertIn("location /private_media/", nginx)
        self.assertIn("return 404", nginx)
        self.assertIn("client_max_body_size 12m", nginx)

    def test_esiste_backup_completo_database_e_file(self):
        root = Path(__file__).resolve().parents[2]
        backup = root / "scripts/backup/backup_nokihub.ps1"
        restore = root / "scripts/restore/restore_nokihub.ps1"
        self.assertTrue(backup.exists())
        self.assertTrue(restore.exists())
        content = backup.read_text(encoding="utf-8")
        self.assertIn("private_media", content)
        self.assertIn("database.dump", content)
