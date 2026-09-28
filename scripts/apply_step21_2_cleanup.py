from __future__ import annotations

import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "templates"

if not (TEMPLATES / "base.html").exists():
    raise SystemExit(
        "ERRORE: eseguire lo script nel progetto LEF Timesheet. "
        "Non trovo templates/base.html."
    )

stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
backup = ROOT / f"templates_backup_step21_2_auto_{stamp}"
shutil.copytree(TEMPLATES, backup)
print(f"Backup creato: {backup}")

changed_files: set[str] = set()
warnings: list[str] = []


def read(rel: str) -> tuple[Path, str]:
    path = ROOT / rel
    if not path.exists():
        warnings.append(f"File non trovato: {rel}")
        return path, ""
    return path, path.read_text(encoding="utf-8")


def write(path: Path, text: str, rel: str) -> None:
    path.write_text(text, encoding="utf-8", newline="")
    changed_files.add(rel)


def replace_exact(rel: str, old: str, new: str) -> None:
    path, text = read(rel)
    if not text:
        return
    if old not in text:
        warnings.append(f"Testo non trovato in {rel}: {old[:80]}")
        return
    new_text = text.replace(old, new)
    if new_text != text:
        write(path, new_text, rel)


def replace_regex(rel: str, pattern: str, replacement: str, *, flags: int = re.S) -> None:
    path, text = read(rel)
    if not text:
        return
    new_text, count = re.subn(pattern, replacement, text, flags=flags)
    if count == 0:
        warnings.append(f"Pattern non trovato in {rel}: {pattern[:80]}")
        return
    if new_text != text:
        write(path, new_text, rel)


# ---------------------------------------------------------------------------
# 1. Navigazione: niente suffissi di ruolo o qualificazioni ridondanti.
# ---------------------------------------------------------------------------
replace_exact("templates/base.html", "<span>Dashboard PM</span>", "<span>Dashboard</span>")
replace_exact(
    "templates/base.html",
    "<span>Dashboard economica</span>",
    "<span>Dashboard</span>",
)

# ---------------------------------------------------------------------------
# 2. Login: logo + Area riservata + campi + pulsante. Via testi introduttivi.
# ---------------------------------------------------------------------------
replace_exact(
    "templates/registration/login.html",
    '<section class="login-stage" aria-labelledby="login-title">',
    '<section class="login-stage" aria-label="Accesso LEF Timesheet">',
)
replace_regex(
    "templates/registration/login.html",
    r'\s*<h1\s+id="login-title">Gestione Timesheet</h1>\s*',
    "\n",
)
replace_regex(
    "templates/registration/login.html",
    r'\s*<p>Accedi con le credenziali aziendali per gestire attività, ore e spese\.</p>\s*',
    "\n",
)
replace_regex(
    "templates/registration/login.html",
    r'\s*<footer class="login-card-footer">.*?</footer>\s*',
    "\n",
)

# ---------------------------------------------------------------------------
# 3. Home Admin e Consulente: titolo coerente con la voce di menu, niente
#    descrizioni da progettista o ripetizioni del ruolo.
# ---------------------------------------------------------------------------
replace_exact(
    "templates/common/home_admin.html",
    "{% block title %}Dashboard Admin | LEF Timesheet{% endblock %}",
    "{% block title %}Home | LEF Timesheet{% endblock %}",
)
replace_regex(
    "templates/common/home_admin.html",
    r'<div><div class="eyebrow">Amministrazione</div><h1>Dashboard</h1><p>Configurazione iniziale di clienti, commesse e consulenti\.</p></div>',
    '<div><h1>Home</h1></div>',
)
replace_exact(
    "templates/common/home_admin.html",
    '<div class="panel-heading"><div><h2>Commesse recenti</h2><p>Quadro sintetico delle ultime commesse configurate.</p></div>',
    '<div class="panel-heading"><div><h2>Commesse recenti</h2></div>',
)

replace_exact(
    "templates/common/home_consulente.html",
    "{% block title %}Dashboard personale | LEF Timesheet{% endblock %}",
    "{% block title %}Home | LEF Timesheet{% endblock %}",
)
replace_regex(
    "templates/common/home_consulente.html",
    r'<div class="eyebrow">Area personale</div>\s*<h1>La tua dashboard</h1>\s*<p>Ore, spese e avanzamento delle tue commesse nel periodo selezionato\.</p>',
    '<h1>Home</h1>',
)

# ---------------------------------------------------------------------------
# 4. Anagrafiche / progetti: via sottotitoli puramente descrittivi.
# ---------------------------------------------------------------------------
replace_exact(
    "templates/accounts/consulente_list.html",
    "<p>Gestione degli account dei consulenti esterni.</p>",
    "",
)
replace_exact(
    "templates/projects/cliente_list.html",
    "<p>Clienti associabili alle commesse LEF.</p>",
    "",
)
replace_exact(
    "templates/projects/commessa_list.html",
    "<p>Configurazione delle attività affidate ai consulenti.</p>",
    "",
)
replace_exact(
    "templates/projects/assegnazione_list.html",
    "<p>Consulenti coinvolti nelle singole commesse.</p>",
    "",
)
replace_exact(
    "templates/projects/assegnazione_form.html",
    "<p>Collega un consulente a una commessa e definisci il suo ruolo.</p>",
    "",
)

# ---------------------------------------------------------------------------
# 5. Tariffe: mostrare dati e azioni, non la logica storica nell'interfaccia.
# ---------------------------------------------------------------------------
replace_exact(
    "templates/projects/tariffa_list.html",
    "<h1>Tariffe storiche</h1>",
    "<h1>Tariffe</h1>",
)
replace_regex(
    "templates/projects/tariffa_list.html",
    r'\s*<p>\s*Ogni tariffa vale dalla data indicata\.\s*Le decorrenze precedenti\s*rimangono conservate e continuano a valorizzare lo storico\.\s*</p>',
    "",
)
replace_regex(
    "templates/projects/tariffa_list.html",
    r'\s*<div class="notice notice-info">\s*Le tariffe non vengono sovrascritte: per una variazione si aggiunge una\s*nuova decorrenza\.\s*</div>',
    "",
)
replace_exact(
    "templates/projects/tariffa_form.html",
    "<h1>Nuova tariffa storica</h1>",
    "<h1>Nuova tariffa</h1>",
)
replace_regex(
    "templates/projects/tariffa_form.html",
    r'\s*<p>\s*La tariffa sarà applicata alle ore dalla data di decorrenza fino\s*all’eventuale tariffa successiva dello stesso tipo\.\s*</p>',
    "",
)

# ---------------------------------------------------------------------------
# 6. Dashboard Admin: un solo nome, niente sottotitolo esplicativo.
# ---------------------------------------------------------------------------
replace_exact(
    "templates/operations/dashboard_admin.html",
    "{% block title %}Dashboard economica | LEF Timesheet{% endblock %}",
    "{% block title %}Dashboard | LEF Timesheet{% endblock %}",
)
replace_exact(
    "templates/operations/dashboard_admin.html",
    "<h1>Dashboard economica</h1>",
    "<h1>Dashboard</h1>",
)
replace_exact(
    "templates/operations/dashboard_admin.html",
    "<p>Ore, avanzamento, spese e valorizzazione del periodo selezionato.</p>",
    "",
)

# ---------------------------------------------------------------------------
# 7. Dashboard Project Manager: niente suffisso PM o spiegazioni dei permessi.
# ---------------------------------------------------------------------------
replace_exact(
    "templates/operations/dashboard_pm.html",
    "{% block title %}Dashboard PM | LEF Timesheet{% endblock %}",
    "{% block title %}Dashboard | LEF Timesheet{% endblock %}",
)
replace_exact(
    "templates/operations/dashboard_pm.html",
    "<h1>Dashboard PM</h1>",
    "<h1>Dashboard</h1>",
)
replace_exact(
    "templates/operations/dashboard_pm.html",
    "<p>Avanzamento operativo delle sole commesse su cui hai un ruolo Project Manager attivo.</p>",
    "",
)
replace_exact(
    "templates/operations/dashboard_pm.html",
    'aria-label="Indicatori principali PM"',
    'aria-label="Indicatori principali"',
)
replace_exact(
    "templates/operations/dashboard_pm.html",
    ". La dashboard PM mostra dati operativi del team e non espone tariffe o valori economici degli altri consulenti.",
    ".",
)
replace_exact(
    "templates/operations/dashboard_pm.html",
    "<p>Il PM può leggere ore e note, senza modificare le righe degli altri consulenti.</p>",
    "",
)

# ---------------------------------------------------------------------------
# 8. Controllo Admin: via spiegazioni di business già incorporate nella logica.
# ---------------------------------------------------------------------------
replace_regex(
    "templates/operations/promemoria.html",
    r'\s*<p>\s*Il promemoria viene destinato ai consulenti attivi che hanno\s*almeno un’assegnazione attiva ma nessuna ora nel mese\.\s*</p>',
    "",
)
replace_exact(
    "templates/operations/promemoria.html",
    "<h1>Promemoria compilazione ore</h1>",
    "<h1>Promemoria</h1>",
)
replace_regex(
    "templates/operations/audit_list.html",
    r'\s*<p>\s*Storico in sola lettura delle operazioni amministrative e delle\s*modifiche rilevanti\.\s*</p>',
    "",
)
replace_regex(
    "templates/operations/report_mensile.html",
    r'\s*<p>\s*Riepilogo economico e operativo con dettaglio di ore e spese\.\s*</p>',
    "",
)

# ---------------------------------------------------------------------------
# 9. Consulente: rimuovere una regola economica non necessaria alla compilazione.
#    Restano invece le istruzioni operative utili (es. limite ore giornaliero).
# ---------------------------------------------------------------------------
replace_exact(
    "templates/timesheets/spesa_form.html",
    "<p>Le spese sono ribaltate al cliente senza maggiorazione.</p>",
    "",
)

# ---------------------------------------------------------------------------
# Verifica finale dei testi che l'utente ha chiesto esplicitamente di eliminare.
# ---------------------------------------------------------------------------
forbidden = [
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
]

leftovers: list[str] = []
for path in TEMPLATES.rglob("*.html"):
    text = path.read_text(encoding="utf-8")
    for item in forbidden:
        if item in text:
            leftovers.append(f"{path.relative_to(ROOT)} -> {item}")

print("\nFile modificati:")
for rel in sorted(changed_files):
    print(f"  - {rel}")

if warnings:
    print("\nAvvisi (non bloccanti):")
    for warning in warnings:
        print(f"  - {warning}")

if leftovers:
    print("\nERRORE: sono rimasti testi da eliminare:")
    for item in leftovers:
        print(f"  - {item}")
    print(f"\nBackup disponibile in: {backup}")
    sys.exit(2)

print("\nStep 21.2 applicato correttamente.")
print(f"Backup disponibile in: {backup}")
