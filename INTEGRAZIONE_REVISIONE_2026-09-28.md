# LEFTRACK — Integrazione ragionata della revisione finale

Data: 28/09/2026

## Obiettivo

Questa versione non sostituisce alla cieca il progetto con la revisione esterna. È costruita a partire dal progetto LEFTRACK corrente fornito, mantenendo le integrazioni più recenti (in particolare il profilo utente con foto/avatar) e importando solo le correzioni tecniche e UI/UX compatibili con il comportamento applicativo attuale.

## Integrato

### Correzioni di affidabilità

- Widget condivisi `DateInput` e `MonthInput` con formato ISO (`YYYY-MM-DD` / `YYYY-MM`), applicati ai form con campi HTML5 data/mese.
- Test di regressione `tests/ui/test_date_widgets.py`.
- Storage documenti espresso come callable e migration `documents.0007`, evitando il percorso assoluto `/app/private_media` congelato nelle migration.
- CI estesa con `python manage.py makemigrations --check --dry-run`.
- `.gitattributes` per normalizzare i fine-riga dei file eseguiti in Linux.
- Test delle preferenze notifiche trasformato in un vero `TestCase` eseguito dalla suite.
- Test branding login aggiornati alla struttura reale del login.
- Correzione HTML del login: niente elemento `<main>` annidato nel `<main>` del layout guest.
- Validazione `ore > 0` mantenuta anche nel service layer, non solo nel form web.

### Prestazioni

- Precaricamento in blocco delle tariffe (`precarica_tariffe`) per dashboard, report, export e valorizzazione periodi, eliminando il pattern N+1 per riga ore.
- Cache per richiesta dei controlli di supervisione in Pianificazione, senza modificare la regola autorizzativa esistente.

### UI/UX

- Etichette form rese coerenti senza i due punti generati da `label_tag`.
- Pulsanti filtro uniformati a “Applica filtri”.
- Testi residuali in inglese tradotti (“Dashboard direzionale”, “Esci”).
- Palette semantica uniforme per badge e stati di workflow.
- Stato pianificazione distinto visivamente tra Pianificata, Da confermare e Confermata.
- Evidenza rossa per azioni/rischi distruttivi e superamento monte ore.
- Codici commessa mantenuti su una riga e indicazione visiva dello scroll orizzontale delle tabelle.
- Form Skill e cambio password riallineati al design system.
- Home Amministrazione semplificata eliminando indicatori duplicati.
- “Avanzamento ore” del Teamwork rinominato “Avanzamento agenda”, coerente con ciò che il dato misura.
- Importi mostrati con separatori locali.
- Font Inter servito localmente dal repository, con licenza OFL inclusa.
- Pulsante elimina documento mostrato solo quando `can_delete_document()` consente davvero l'operazione.

### Foto profilo — mantenuta e integrata

La versione include la funzione già validata nello staging LEFTRACK:

- `User.foto_profilo` (`ImageField`);
- Pillow dichiarato in `pyproject.toml` (`Pillow>=11,<12`);
- JPG/JPEG/PNG/WebP, massimo 3 MB;
- pagina personale `/gestione/consulenti/profilo/`;
- l'utente può modificare nome, cognome, telefono e foto, ma non email/ruolo;
- sostituzione/rimozione dell'immagine con pulizia del file precedente;
- avatar in sidebar e topbar;
- fallback all'iniziale se la foto non è presente;
- test `tests/integration/test_user_profile.py`.

## Deliberatamente NON integrato

Le seguenti modifiche della revisione esterna cambiano regole di business e non sono state applicate automaticamente, perché la revisione è stata effettuata su una specifica precedente alle ultime decisioni LEFTRACK:

1. **Divieto generalizzato di consuntivare date future per i non-Admin.** Il comportamento corrente viene preservato finché la regola non viene formalmente confermata.
2. **Blocco automatico di modifica/eliminazione di tutte le righe ore/spese appena risultano `APPROVATA`.** Restano valide le regole correnti di LEFTRACK (`bloccata_per_consulente`, periodo chiuso, audit Admin, ecc.) finché non viene definito il nuovo workflow di rettifica.
3. **Restrizione dei permessi di modifica di pianificazioni/attività dei colleghi.** Non è stata introdotta: la matrice attuale resta invariata. La cache prestazionale aggiunta non cambia l'esito dei permessi.

Di conseguenza non è stato importato `tests/timesheets/test_approved_lock.py`, perché testerebbe regole volutamente non introdotte.

## Proposte rimaste fuori da questa integrazione

Sono considerate evoluzioni separate e non fanno parte di questa patch:

- durata sessione 8–12 ore / chiusura browser;
- allegati ai giustificativi spese;
- consolidamento completo dei CSS;
- monitoraggio errori esterno (es. Sentry);
- revisione “Dashboard di progetto” Admin;
- pulizia degli warning OpenAPI;
- SSO Microsoft 365 / Google;
- PWA mobile;
- integrazioni fatturazione/paghe.

## Verifiche effettuate in questa preparazione

- confronto file-per-file tra progetto originale fornito e progetto revisionato;
- integrazione selettiva, non sostituzione completa;
- mantenimento esplicito della funzione foto profilo;
- rimozione di `__pycache__` / `.pyc` dal pacchetto;
- compilazione sintattica Python (`compileall`) completata senza errori.

La suite Django completa deve essere eseguita nello staging Docker del progetto, perché l'ambiente di preparazione del pacchetto non dispone delle dipendenze Django/PostgreSQL necessarie.

## Test consigliati prima del merge

```powershell
# branch dedicato
git checkout develop
git pull
git checkout -b review/integrazione-finale

# rebuild perché sono presenti Pillow e file statici/font
docker compose -p lef-timesheet-staging -f docker-compose.staging.yml build web scheduler

docker compose -p lef-timesheet-staging -f docker-compose.staging.yml up -d --force-recreate web scheduler

docker compose -p lef-timesheet-staging -f docker-compose.staging.yml restart nginx

# controlli Django
docker compose -p lef-timesheet-staging -f docker-compose.staging.yml exec web python manage.py check
docker compose -p lef-timesheet-staging -f docker-compose.staging.yml exec web python manage.py makemigrations --check --dry-run
docker compose -p lef-timesheet-staging -f docker-compose.staging.yml exec web python manage.py migrate

# test mirati
docker compose -p lef-timesheet-staging -f docker-compose.staging.yml exec web python manage.py test tests.ui.test_date_widgets tests.ui.test_branding_login tests.integration.test_user_profile --verbosity 2

# suite completa
docker compose -p lef-timesheet-staging -f docker-compose.staging.yml exec web python manage.py test --verbosity 1
```

Dopo i test automatici verificare manualmente: login/reset/attivazione, profilo/foto, modifica di record con date già valorizzate, dashboard/report/export, documenti, pianificazione, Teamwork e ruoli principali.
