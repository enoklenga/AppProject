# Revisione LEF Timesheet V2 — 17/09/2026

## Correzioni incluse

- Calendario/pianificazione ricondotti al perimetro **Commessa → Fase**:
  - un consulente vede le pianificazioni delle sole fasi in cui ha un'assegnazione attiva;
  - il PM mantiene la supervisione sulle fasi delle commesse dove è PM;
  - Admin mantiene visibilità completa.
- Task resi coerenti con la regola **fase obbligatoria**:
  - rimosso il fallback automatico a `Generale`;
  - validazione assegnatario sulla specifica fase;
  - filtro Fase aggiunto alla lista attività.
- Elenco attività:
  - corrette le larghezze della tabella a 8 colonne;
  - corretto `colspan`;
  - azioni rese non sovrapposte.
- Documenti:
  - il filtro Commessa ora usa le commesse disponibili all'utente e non solo quelle che hanno già documenti;
  - aggiunto filtro Fase quando è selezionata una commessa.
- Navigazione Teamwork:
  - Admin: Teamwork → ritorno alle Commesse;
  - Consulente/PM: Teamwork → ritorno alla Home;
  - pagine operative aperte con `?commessa=...` → ritorno al relativo Teamwork;
  - mantenuto il contesto Commessa/Fase nei link principali.
- Home consulente:
  - avanzamento ordinato per Commessa → Fase → Consulente.
- Planning:
  - aggiunta la Fase nel dettaglio tabellare e negli eventi calendario;
  - corrette le larghezze della tabella dopo l'introduzione della colonna Fase.
- Importazione Ore/Spese:
  - la Fase è ora obbligatoria nel template;
  - l'assegnazione viene risolta per **Consulente + Commessa + Fase + validità temporale**, evitando ambiguità quando lo stesso consulente lavora su più fasi della stessa commessa.
- Dashboard/Report:
  - il filtro Fase viene applicato anche agli aggregati dashboard;
  - il report HTML mostra anche l'aggregato per Fase;
  - il dettaglio Ore riporta la Fase;
  - Excel mantiene i fogli per Fase e il dettaglio Ore/Spese con Fase.
- Audit:
  - per `PeriodoMensile` la UI mostra il periodo leggibile (es. `09/2026 – Chiuso`) invece del solo UUID tecnico.

## Verifica eseguita

- Compilazione Python dell'applicazione: OK (`compileall`).
- Non è stata eseguita una suite Django completa perché l'ambiente locale di analisi non contiene Django né il database PostgreSQL del progetto.
- Le migrazioni del database non sono state modificate da questa revisione.
