from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase


class ContentSimplificationTests(SimpleTestCase):
    def test_project_descriptions_are_not_exposed_in_ui(self):
        templates = Path(settings.BASE_DIR) / "templates"
        forbidden = (
            "Gestione Timesheet",
            "Accedi con le credenziali aziendali per gestire attività, ore e spese.",
            "Configurazione iniziale di clienti, commesse e consulenti.",
            "Gestione degli account dei consulenti esterni.",
            "Clienti associabili alle commesse LEF.",
            "Ogni tariffa vale dalla data indicata.",
            "Ore, avanzamento, spese e valorizzazione del periodo selezionato.",
            "Il promemoria viene destinato ai consulenti attivi",
            "Storico in sola lettura delle operazioni amministrative",
            "Riepilogo economico e operativo con dettaglio di ore e spese.",
            "Dashboard PM",
            "Dashboard economica",
        )

        content = "\n".join(
            path.read_text(encoding="utf-8")
            for path in templates.rglob("*.html")
        )
        for text in forbidden:
            with self.subTest(text=text):
                self.assertNotIn(text, content)
