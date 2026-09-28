from pathlib import Path

from django.test import SimpleTestCase


class PackagingSecurityTests(SimpleTestCase):
    def test_private_media_is_excluded_from_docker_build_context(self):
        project_root = Path(__file__).resolve().parents[2]
        dockerignore = project_root / ".dockerignore"

        self.assertTrue(
            dockerignore.exists(),
            ".dockerignore deve essere presente nella radice del progetto.",
        )

        patterns = {
            line.strip()
            for line in dockerignore.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        }

        self.assertIn("private_media", patterns)
        self.assertIn("private_media/**", patterns)
