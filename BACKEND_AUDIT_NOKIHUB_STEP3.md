# Nokihub — Backend Hardening Step 3

Data revisione: 21/09/2026

## Obiettivo

Chiudere il blocco tecnico/deployment rimasto dopo Step 1 e Step 2: sicurezza upload, backup dei file, esecuzione container non-root, health/readiness, proxy/IP, redirect, export spreadsheet e limiti di upload.

## Interventi applicati

### BK-012 — Validazione reale dei file caricati
**Stato: FIXED**

I documenti non vengono più validati solo tramite estensione. È stata aggiunta una verifica del contenuto:
- PDF: firma `%PDF-`;
- JPEG/PNG: magic bytes;
- DOC/XLS/PPT legacy: firma OLE;
- DOCX/XLSX/PPTX: archivio ZIP con struttura Office coerente;
- ODT/ODS/ODP: MIME ODF interno coerente;
- ZIP: archivio ZIP realmente leggibile;
- TXT/CSV: blocco immediato dei contenuti binari con byte NUL.

Il nome file viene inoltre ridotto al solo basename e normalizzato prima del salvataggio su storage.

La stessa difesa di primo livello è stata aggiunta agli import `.xlsx`/`.csv`, anche nel service, così da coprire UI, API e chiamate dirette.

### BK-013 — Backup e restore dei documenti
**Stato: FIXED**

Il dump PostgreSQL non contiene i file fisici. Sono stati aggiunti:
- `scripts/backup/backup_nokihub.ps1`
- `scripts/backup/backup_nokihub.sh`
- `scripts/restore/restore_nokihub.ps1`

Il bundle completo contiene:
- `database.dump`
- `private_media.tar.gz`
- `media.tar.gz`
- manifest/hash di controllo

Il vecchio `backup_postgres.ps1` resta disponibile esclusivamente per backup DB.

### BK-014 — Container applicativo non-root
**Stato: FIXED**

Il Dockerfile crea ed usa l'utente `nokihub` UID/GID 10001.

Per evitare problemi con named volume già esistenti e precedentemente creati come root, production e staging includono il servizio one-shot `init_permissions`, eseguito come root esclusivamente per riallineare ownership delle directory runtime prima dell'avvio del web service.

### BK-015 — Readiness senza leak di dettagli interni
**Stato: FIXED**

`/health/ready/` non restituisce più `str(exc)` al client. In caso di errore DB espone solo stato generico e registra il dettaglio nel log server-side `lef.health`.

Gli endpoint health impostano inoltre `Cache-Control: no-store`.

### BK-016 — Rate limiting del login web
**Stato: FIXED**

Il login browser ora applica due limiti configurabili:
- bucket IP + email;
- bucket aggregato per IP.

Le impostazioni sono:
- `WEB_LOGIN_RATE_LIMIT=5`
- `WEB_LOGIN_IP_RATE_LIMIT=30`
- `WEB_LOGIN_RATE_WINDOW_SECONDS=300`

Quando il limite è superato il login restituisce HTTP 429 senza distinguere account esistente/non esistente.

### BK-017 — Gestione sicura di X-Forwarded-For
**Stato: FIXED**

Il token audit non usa più il primo valore di `X-Forwarded-For`, facilmente falsificabile dal client. Viene selezionato l'indirizzo partendo da destra in base al numero di proxy fidati configurato in `API_NUM_PROXIES`, coerentemente con il modello DRF.

Il preflight production ora richiede `API_TRUST_X_FORWARDED_FOR=True` e `API_NUM_PROXIES >= 1` nel deployment Nginx previsto dal progetto.

### BK-018 — Open redirect nelle approvazioni timesheet
**Stato: FIXED**

Il parametro POST `next` delle viste di approvazione/rifiuto non viene più passato direttamente a `HttpResponseRedirect`. È ora accettato solo se interno e coerente con host/schema della richiesta.

### BK-019 — Formula Injection CSV/XLSX
**Stato: FIXED**

È stata aggiunta una sanitizzazione condivisa per dati controllabili dall'utente che iniziano con `=`, `+`, `-`, `@`, TAB/CR/LF.

La protezione è applicata a:
- report XLSX mensile;
- aggregati XLSX;
- CSV errori importazione web/API;
- CSV audit web/API.

I valori numerici e date restano invariati.

### BK-020 — Limiti upload coerenti tra Django/Nginx/app
**Stato: FIXED**

Configurazione allineata:
- documento applicativo: 10 MB;
- import: 5 MB;
- Nginx request body: 12 MB, così da lasciare margine all'overhead multipart;
- `DJANGO_DATA_UPLOAD_MAX_MEMORY_SIZE`: 12 MB;
- `DJANGO_FILE_UPLOAD_MAX_MEMORY_SIZE`: 5 MB (soglia memoria, non limite totale file).

I valori sono ora espliciti negli `.env.*.example`.

### BK-021 — Scope documenti su commessa/fase
**Stato: FIXED**

La pagina upload con `?commessa=...` non carica più una commessa arbitraria per UUID: la commessa deve appartenere al queryset gestibile dall'utente.

Anche l'elenco fasi del filtro documenti per utenti non Admin è limitato alle fasi con assegnazione attiva dell'utente, evitando esposizione di nomi di fasi non accessibili.

## Hardening deployment aggiuntivo

- Nginx restituisce esplicitamente `404` per `/private_media/` come difesa aggiuntiva.
- `verifica_go_live` controlla scrivibilità di `PRIVATE_MEDIA_ROOT` e coerenza della configurazione proxy.
- `preflight_production.ps1` verifica anche limiti upload, rate limit login e proxy trust.
- README aggiornato con backup completo e regole di sicurezza operative.

## Test aggiunti

- `tests/integration/test_security_hardening_step3.py`
  - file mascherato da PDF;
  - formula spreadsheet;
  - X-Forwarded-For spoofing;
  - redirect esterno;
  - rate limit login web;
  - readiness senza leak;
  - container non-root;
  - init permissions dei volumi;
  - Nginx private media;
  - presenza backup completo.
- `tests/operations/test_export_security.py`
  - neutralizzazione formula nel CSV audit.
- `tests/operations/test_reports.py`
  - neutralizzazione formula nel report XLSX.

## Verifiche eseguite nell'ambiente di revisione

- compilazione Python `compileall`: OK;
- parsing YAML di `docker-compose.prod.yml` e `docker-compose.staging.yml`: OK;
- nessuna modifica ai modelli/migrazioni: nuove migration non previste.

La suite Django/PostgreSQL deve essere eseguita nel container del progetto dell'utente, come per Step 1 e Step 2.

## Comandi di validazione consigliati

```powershell
docker compose exec web python manage.py test tests.integration.test_security_hardening_step3 tests.operations.test_export_security tests.operations.test_reports --keepdb -v 2
```

Poi:

```powershell
docker compose exec web python manage.py check
docker compose exec web python manage.py makemigrations --check --dry-run
```

Infine tutta la suite backend:

```powershell
docker compose exec web python manage.py test apps.documents.tests apps.notifications.tests apps.phases.tests apps.planning.tests apps.tasks.tests tests.api tests.domain tests.integration tests.operations tests.timesheets --keepdb -v 1
```

Per verificare anche la nuova identità del container dopo rebuild:

```powershell
docker compose build web
docker compose run --rm --no-deps web id
```

L'output deve mostrare UID/GID 10001 (`nokihub`) e non `root`.

## Nota UI

Lo Step 3 non modifica volutamente i 5 test UI/branding già noti. La loro sistemazione resta separata dal backend hardening.
