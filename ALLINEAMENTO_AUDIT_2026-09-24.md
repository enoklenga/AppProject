# LEFTRACK — Allineamento audit backend 24/09/2026

## Obiettivo

Questa revisione riallinea il progetto completo alle invarianti evidenziate in `LEFTRACK_BACKEND_AUDIT_2026-09-24.md`, preservando le funzionalità già coerenti e rendendo consistenti agenda, timesheet, chiusure, workflow, permessi, Skill Matrix e Django Admin.

Decisioni applicate:

- **Planning storico allineabile:** sì.
- **Modifiche strutturali consentite:** sì, quando necessarie per rimuovere incoerenze o bypass del dominio.
- **Go-live della nuova semantica agenda:** 24/09/2026.
- **Ingaggiabilità V1:** capacità agenda giornaliera standard di 8 ore; il planning resta il gate definitivo sulla disponibilità.
- **Workflow:** vincolante sugli stati operativi. `SOSPESA`/`CHIUSA` bloccano l'operatività; `IN_CHIUSURA` blocca nuovo lavoro ma consente le operazioni necessarie a consolidare quanto già eseguito.

## Correzioni applicate

| Audit | Stato | Implementazione |
|---|---|---|
| C1 | RISOLTO | La chiusura mensile blocca sessioni agenda non risolte o incoerenti con il timesheet. |
| C2 | RISOLTO | Un'assegnazione non può essere conclusa con sessioni da confermare o confermate/allineate senza link timesheet. |
| C3 | RISOLTO | Disattivazione utente centralizzata in service transazionale; blocco su assegnazioni attive/PM e sessioni aperte. |
| C4 | RISOLTO | Planning nel Django Admin solo diagnostico: no add/change/delete/actions. |
| C5 | RISOLTO | Ore e spese nel Django Admin solo diagnostiche: no add/change/delete/actions. |
| C6 | RISOLTO | `riga_ore_generata` usa `PROTECT`; aggiunto vincolo DB di coerenza stato/metadati/link. |
| C7 | RISOLTO | Migrazione forward dello storico planning con `STORICO_ALLINEATO` / `STORICO_ESENTE`; nessuna falsa conferma utente. |
| C8 | RISOLTO | Migrazione forward workflow: storico chiuso -> `CHIUSA`, storico aperto -> `IN_ESECUZIONE`. |
| H1 | RISOLTO | PM cross-phase su planning, sia permission/service sia form/queryset. |
| H2 | RISOLTO | PM cross-phase su Task, inclusi create/update/delete. |
| H3 | RISOLTO | Regole lifecycle centralizzate in `apps/projects/workflow.py`; stati sospesi/chiusi governano realmente l'operatività. |
| H4 | RISOLTO | Handover rimosso dal form generale; mutazioni solo tramite service auditato. Workflow gestito da service dedicato con transizioni e motivazione. |
| H5 | RISOLTO V1 | Ingaggiabilità date-aware su agenda giornaliera; capacità 8h/giorno; assegnazione usa la disponibilità della data di avvio e il planning applica il limite effettivo. |
| H6 | RAFFORZATO | Aggiunti test di regressione audit per chiusure, assegnazioni, disattivazione, PM cross-phase, PROTECT, periodo chiuso, idempotenza, Admin, skill e ingaggiabilità. |
| M1 | RISOLTO | Utente inattivo non è ingaggiabile. |
| M2 | RISOLTO | Check DB livelli Skill Matrix 1/2/3 e unicità case-insensitive del nome skill, con merge dati preesistenti. |
| M3 | RISOLTO | Fasi `COMPLETATA`/`SOSPESA` bloccano nuovo planning, task e assegnazioni attive. |
| M4 | RISOLTO | Superamento Admin >8h richiede motivazione obbligatoria a livello service; propagata a UI/API/import. |
| M5 | RISOLTO | Rimossi fallback/commenti legacy `Coordinamento PM`; modello phase-scoped mantenuto fail-fast. |

## Strategia planning storico

Per le sessioni con data **precedente al 24/09/2026**:

1. se esiste **un solo match univoco** in `RigaOre` con stessa assegnazione, data, ore e tipologia, la sessione diventa `STORICO_ALLINEATO` e viene collegata alla riga;
2. se il match è assente o ambiguo, la sessione diventa `STORICO_ESENTE`;
3. nessuna sessione storica viene marcata come `CONFERMATA` dall'utente senza un'effettiva conferma;
4. eventuali stati `CONFERMATA` parziali/incoerenti vengono normalizzati prima dell'applicazione del nuovo `CheckConstraint`.

Le metriche della commessa distinguono ora le **sessioni risolte** dalle **conferme effettivamente effettuate dalla risorsa**, evitando di rappresentare lo storico esente come una conferma utente.

## Lock e concorrenza agenda

Le mutazioni del planning acquisiscono il lock del `PeriodoMensile` prima delle righe operative, coerentemente con la chiusura mese. In particolare:

- non si può creare planning in un mese già chiuso;
- non si può spostare/modificare/eliminare planning attraversando periodi chiusi;
- la conferma agenda usa lo stesso ordine di lock della chiusura mensile;
- la conferma è idempotente: un retry della stessa risorsa non genera una seconda `RigaOre`;
- il retry di una sessione già consolidata resta innocuo anche se il mese viene chiuso successivamente.

## Migrazioni aggiunte

- `apps/accounts/migrations/0004_skill_matrix_constraints.py`
- `apps/planning/migrations/0003_planning_integrity_legacy_alignment.py`
- `apps/projects/migrations/0006_align_legacy_workflow.py`

Queste migrazioni sono **forward migrations**: non modificare manualmente le precedenti già presenti in ambienti condivisi.

## Verifiche eseguite in questo ambiente

- `python -m compileall -q .`: **OK**
- parsing AST di tutti i file Python: **260/260 OK**
- marker di conflitto Git reali: **nessuno**
- metodi `test_*` presenti: **316**
- revisione statica dei punti audit e dei caller interessati: completata

### Limite dell'ambiente di revisione

In questo ambiente non sono disponibili né Django né Docker. Di conseguenza **non sono stati eseguiti** `manage.py check`, le migrazioni reali su PostgreSQL o la suite Django. Il progetto non va promosso in produzione finché i comandi sotto non passano nello staging reale.

## Gate obbligatorio in staging

```powershell
docker compose -p lef-timesheet-staging --env-file .env.staging -f docker-compose.staging.yml up -d --build --force-recreate web

docker compose -p lef-timesheet-staging --env-file .env.staging -f docker-compose.staging.yml exec web python manage.py makemigrations --check --dry-run

docker compose -p lef-timesheet-staging --env-file .env.staging -f docker-compose.staging.yml exec web python manage.py migrate

docker compose -p lef-timesheet-staging --env-file .env.staging -f docker-compose.staging.yml exec web python manage.py check

docker compose -p lef-timesheet-staging --env-file .env.staging -f docker-compose.staging.yml exec web python manage.py test --verbosity 1
```

## Criterio di rilascio

Procedere al deploy di produzione solo se:

- `makemigrations --check --dry-run` non rileva migrazioni mancanti;
- tutte le migrazioni vengono applicate correttamente sul clone/staging del DB reale;
- `manage.py check` passa senza errori;
- l'intera suite Django passa;
- viene verificato manualmente almeno un caso per: conferma agenda -> timesheet, chiusura mese, PM cross-phase, sospensione workflow, disattivazione utente e storico planning.
