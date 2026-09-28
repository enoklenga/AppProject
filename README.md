# LEFTRACK

> Sistema web LEF per la gestione integrata di consulenti, clienti, commesse, fasi, pianificazione, attività, timesheet, spese, documenti, approvazioni, reporting e controllo operativo.

**Versione applicativa dichiarata:** `0.1.0`  
**Stack principale:** Python 3.13 · Django 5.2 · PostgreSQL 18 · Django REST Framework · Gunicorn · Nginx · Docker Compose  
**Lingua applicativa:** Italiano (`it-it`)  
**Timezone:** `Europe/Rome`

---

## 1. Scopo di questo documento

Questo README è il punto di ingresso tecnico e funzionale al progetto LEFTRACK. È pensato per una persona che non ha partecipato allo sviluppo e deve poter capire:

- che cosa fa l'applicazione e quali problemi risolve;
- come è organizzato il codice;
- quali sono i ruoli e i relativi perimetri di accesso;
- come funzionano commesse, fasi, Teamwork, pianificazione, task, timesheet, spese e documenti;
- come sono strutturati database e modelli principali;
- come avviare sviluppo, staging e produzione;
- come configurare le variabili d'ambiente;
- come funzionano API, sicurezza, email e notifiche;
- come eseguire test, backup, restore e verifiche di go-live;
- dove intervenire quando è necessario modificare una specifica funzionalità.

Le informazioni qui riportate sono state ricavate dal codice presente nel repository. In caso di divergenza futura tra documentazione e codice, **il codice e le migrazioni del branch/versione effettivamente distribuita restano la fonte tecnica definitiva**.

---

## 2. Che cos'è LEFTRACK

LEFTRACK è un'applicazione Django sviluppata per gestire il ciclo operativo delle attività LEF, con particolare attenzione al lavoro dei consulenti e al controllo delle commesse.

Il sistema collega in un unico flusso:

**persone → clienti → commesse → fasi → assegnazioni → pianificazione → task → consuntivi → approvazioni → reporting**.

Oltre al timesheet tradizionale, il progetto comprende funzioni di Teamwork, Skill Matrix, workflow di commessa, documentazione riservata, notifiche, promemoria, importazioni massive, audit e API REST.

### 2.1 Funzionalità principali

- autenticazione tramite email;
- invito/attivazione degli account e cambio password obbligatorio configurabile;
- ruoli organizzativi LEF;
- anagrafica consulenti e Skill Matrix;
- clienti e commesse;
- workflow operativo della commessa;
- fasi di commessa;
- assegnazione delle risorse alle fasi/commesse;
- ruolo Project Manager definito sulla singola assegnazione;
- tariffe storicizzate per assegnazione e tipo attività;
- pianificazione giornaliera delle risorse;
- conferma delle sessioni pianificate;
- gestione task e commenti;
- registrazione ore e spese;
- approvazione/rifiuto di ore e spese;
- chiusura e riapertura dei periodi mensili;
- dashboard per differenti profili;
- report mensile ed esportazione XLSX;
- documenti di commessa con controllo degli accessi;
- notifiche applicative e preferenze utente;
- promemoria automatici timesheet;
- importazioni CSV/XLSX con validazione e anteprima;
- audit delle operazioni amministrative;
- API REST `/api/v1/`;
- gestione token API, throttling e controlli di sicurezza;
- health/readiness endpoint;
- Docker per sviluppo, staging e produzione;
- backup/restore di database e file applicativi;
- CI GitHub Actions.

---

## 3. Concetti fondamentali

### 3.1 Ruolo organizzativo e ruolo di commessa sono separati

È una distinzione fondamentale dell'architettura.

Ogni `User` possiede un **ruolo organizzativo** LEF. Separatamente, una `Assegnazione` può qualificare una risorsa come **Consulente** oppure **Project Manager** sulla specifica commessa/fase.

Essere Project Manager, quindi, **non è un ruolo globale dell'utente**. Questo impedisce che un PM di una commessa acquisisca automaticamente privilegi su altre commesse.

### 3.2 La commessa è il perimetro centrale

La `Commessa` appartiene a un `Cliente` e rappresenta il contenitore del lavoro. Al suo interno vengono organizzati:

- fasi;
- assegnazioni;
- pianificazioni;
- task;
- ore;
- spese;
- documenti;
- workflow e handover.

### 3.3 Le fasi segmentano il lavoro

`FaseCommessa` permette di suddividere una commessa in parti operative con stato e intervallo temporale propri. Assegnazioni, planning e task sono collegati alla fase.

### 3.4 Pianificato e consuntivato sono collegati

`GiornoPianificato` rappresenta una sessione pianificata. La risorsa assegnata può confermarne la conclusione; il modello mantiene anche il riferimento alla `RigaOre` eventualmente generata.

---

## 4. Architettura tecnica

```text
Browser / Client API
        |
        v
      Nginx
        |
        v
Django + Gunicorn
   |           |
   |           +--> REST API /api/v1/
   |
   +--> Web UI server-rendered
   |      Templates + CSS + JS
   |
   +--> Service / Permission / Selector layer
   |
   +--> Django ORM
              |
              v
          PostgreSQL

File pubblicabili/runtime  -> media/
Documenti riservati        -> private_media/ -> sempre autorizzati da Django
Statici raccolti           -> staticfiles/ -> serviti da Nginx
```

L'applicazione usa prevalentemente rendering server-side Django. JavaScript e CSS completano l'interfaccia, ma il backend Django resta il centro delle regole di dominio e delle autorizzazioni.

---

## 5. Stack e dipendenze

Dal `pyproject.toml`:

| Componente | Uso |
|---|---|
| Python `>=3.13,<3.15` | runtime |
| Django `>=5.2.16,<5.3` | framework web/ORM/auth |
| PostgreSQL 18 | database relazionale |
| psycopg 3 | driver PostgreSQL |
| Django REST Framework | API REST |
| django-filter | filtri API |
| drf-spectacular | schema OpenAPI, Swagger, ReDoc |
| openpyxl | import/export Excel |
| Gunicorn | application server staging/production |
| Nginx | reverse proxy e static/media |
| Docker Compose | orchestrazione ambienti |
| coverage | dipendenza opzionale di sviluppo |

Non risultano framework frontend JavaScript pesanti: l'interfaccia usa template Django, CSS e JavaScript nativo.

---

## 6. Struttura del repository

```text
lef-timesheetProject/
├── apps/
│   ├── accounts/       # utenti, ruoli, skill, attivazione e accessi
│   ├── api/            # REST API e sicurezza API
│   ├── common/         # componenti condivisi e sicurezza file/request
│   ├── documents/      # documenti di commessa
│   ├── notifications/  # notifiche e preferenze
│   ├── operations/     # dashboard, periodi, report, import, audit, reminder
│   ├── phases/         # fasi di commessa
│   ├── planning/       # agenda/pianificazione
│   ├── projects/       # clienti, commesse, assegnazioni, tariffe, workflow
│   ├── tasks/          # task e commenti
│   └── timesheets/     # ore e spese
├── config/             # settings, URL root, WSGI/ASGI
├── deploy/
│   ├── docker/         # Dockerfile
│   └── nginx/          # configurazione Nginx
├── scripts/
│   ├── backup/
│   ├── production/
│   ├── restore/
│   └── staging/
├── static/             # CSS, JS, immagini sorgente
├── templates/          # template Django
├── tests/              # suite trasversale
├── .github/workflows/  # CI
├── docker-compose.yml
├── docker-compose.staging.yml
├── docker-compose.prod.yml
├── docker-compose.reminder.yml
├── manage.py
└── pyproject.toml
```

### 6.1 Pattern ricorrenti nei moduli

Dove presenti:

- `models.py`: struttura dati e vincoli di dominio vicini al modello;
- `forms.py`: validazione/form web;
- `views.py`: controller web;
- `urls.py`: routing;
- `permissions.py`: autorizzazioni sul dominio;
- `selectors.py`: query/lettura dati;
- `services.py`: operazioni di business e mutazioni;
- `signals.py`: eventi Django;
- `admin.py`: Django Admin;
- `tests/`: test locali del modulo;
- `migrations/`: evoluzione schema DB.

Quando si aggiunge una nuova regola di business, evitare di duplicarla nelle view: verificare prima se appartiene a `services.py`, `permissions.py`, `selectors.py` o al modello.

---

## 7. Ruoli e autorizzazioni

I ruoli organizzativi definiti in `accounts.User.Ruolo` sono:

| Ruolo | Codice | Perimetro principale dal codice |
|---|---|---|
| Admin LEF | `ADMIN` | amministrazione completa, utenti, Skill Matrix, portafoglio, finanza, audit |
| Consulente / Team esecutivo | `CONSULENTE` | operatività personale e sulle commesse assegnate |
| Responsabile consulenza / Business Unit | `RESP_CONSULENZA` | persone, Skill Matrix in lettura, planning aggregato e operatività se ingaggiato |
| Amministrazione | `AMMINISTRAZIONE` | report, ledger ore/spese, tariffe/approvazioni/periodi |
| Commerciale | `COMMERCIALE` | portafoglio clienti/commesse e gestione anagrafica commerciale |
| Direzione Generale | `DIREZIONE_GENERALE` | portafoglio, dashboard executive, report, audit e viste aggregate in lettura |

La matrice centralizzata è in `apps/accounts/access.py`.

### 7.1 Permessi trasversali principali

- gestione utenti: Admin;
- visualizzazione persone: Admin + Responsabile Consulenza;
- Skill Matrix in lettura: Admin + Responsabile Consulenza + Direzione Generale;
- gestione Skill Matrix: Admin;
- portafoglio clienti/commesse senza assegnazione: Admin + Commerciale + Direzione Generale;
- gestione clienti/commesse anagrafiche: Admin + Commerciale;
- dashboard executive: Admin + Direzione Generale;
- report: Admin + Direzione Generale + Amministrazione;
- lettura trasversale ore/spese: Admin + Amministrazione;
- gestione finanziaria: Admin + Amministrazione;
- planning aggregato: Admin + Responsabile Consulenza + Direzione Generale;
- audit: Admin + Direzione Generale;
- task di portafoglio: Admin + Direzione Generale, con limitazioni operative per DG.

### 7.2 Project Manager

Il PM è espresso da `Assegnazione.ruolo_commessa = PROJECT_MANAGER`. I controlli verificano che l'assegnazione PM sia attiva e appartenga alla commessa/fase interessata.

---

## 8. Modello dati principale

Molti modelli ereditano da `UUIDTimeStampedModel`, che fornisce:

- `id` UUID;
- `created_at`;
- `updated_at`.

### 8.1 Accounts

**User**
- autenticazione tramite `email` univoca; `username` disabilitato;
- ruolo organizzativo;
- telefono;
- flag `deve_cambiare_password`;
- tracking invito e attivazione;
- stato Django `is_active`.

**Skill**
- nome univoco anche case-insensitive;
- categoria;
- descrizione;
- stato attivo.

**UserSkill**
- collega utente e skill;
- livelli 1, 2, 3;
- una sola riga per coppia utente/skill.

### 8.2 Projects

**Cliente**
- ragione sociale;
- partita IVA univoca;
- referente;
- note;
- attivo/non attivo.

**Commessa**
- cliente;
- codice univoco;
- descrizione;
- budget ore opzionale;
- data inizio/fine prevista;
- stato tecnico `APERTA/CHIUSA`;
- stato workflow;
- handover e relative informazioni;
- note.

La modifica delle date della commessa verifica che non vengano esclusi dati figli già esistenti: fasi, assegnazioni, planning, task, ore e spese.

**Assegnazione**
- risorsa/consulente;
- commessa;
- fase;
- ore previste;
- ruolo sulla commessa (`CONSULENTE` / `PROJECT_MANAGER`);
- stato (`ATTIVA` / `CONCLUSA`);
- intervallo temporale.

**TariffaAssegnazione**
- assegnazione;
- tipo attività (`FORMAZIONE` / `CONSULENZA`);
- tariffa oraria;
- decorrenza `valida_dal`;
- autore della creazione.

### 8.3 Phases

**FaseCommessa**
- commessa;
- nome e descrizione;
- ordine;
- flag `sistema`;
- stato: `DA_INIZIARE`, `IN_CORSO`, `COMPLETATA`, `SOSPESA`;
- data inizio/fine prevista;
- autore.

### 8.4 Planning

**GiornoPianificato**
- assegnazione;
- data;
- ore pianificate;
- tipo attività;
- stato sessione;
- tracking conferma;
- eventuale `RigaOre` generata;
- autore e ultima modifica;
- flag modifica Admin.

Stati sessione previsti:
- `PIANIFICATA`;
- `CONFERMATA`;
- `STORICO_ALLINEATO`;
- `STORICO_ESENTE`.

### 8.5 Tasks

**Task**
- commessa e fase;
- titolo e descrizione;
- assegnatario;
- creatore;
- stato `DA_FARE`, `IN_CORSO`, `COMPLETATA`;
- priorità `BASSA`, `NORMALE`, `ALTA`;
- data inizio/scadenza;
- data completamento.

**TaskComment**
- task;
- autore;
- testo.

### 8.6 Timesheets

**RigaOre**
- assegnazione;
- data;
- tipo attività;
- ore;
- nota;
- autore/ultima modifica;
- flag modifica Admin;
- blocco per consulente;
- versione;
- stato approvazione;
- nota approvazione;
- approvatore e data approvazione.

**SpesaTrasferta**
- assegnazione;
- data;
- categoria (`VIAGGIO`, `VITTO`, `ALLOGGIO`, `ALTRO`);
- importo;
- nota;
- stessi metadati di modifica/blocco/approvazione della riga ore.

Stati di approvazione condivisi:
- `IN_ATTESA`;
- `APPROVATA`;
- `RIFIUTATA`.

### 8.7 Operations

**PeriodoMensile**
- anno/mese;
- stato `APERTO` / `CHIUSO`;
- chiusura/riapertura e relativi attori;
- flag di forzatura per tariffe/approvazioni mancanti;
- motivazione della forzatura.

**AuditLog**
- utente;
- entità e relativo UUID;
- azione;
- valore precedente/nuovo JSON;
- motivazione;
- timestamp.

**ConfigurazionePromemoria**
- giorno e ora di invio;
- attivazione;
- modalità “solo assenza totale ore”;
- ultimo autore modifica.

**InvioPromemoria**
- configurazione;
- consulente;
- anno/mese;
- esito `INVIATO/ERRORE`;
- data tentativo ed eventuale errore.

**Importazione / ErroreImportazione**
- traccia caricamento, hash, stato e conteggi;
- registra errori puntuali per riga/campo con dati originali serializzati.

---

## 9. Workflow della commessa

`Commessa.workflow_stato` può assumere:

```text
DA_PRENDERE_IN_CARICO
        |
        v
      HANDOVER
        |
        v
   PIANIFICAZIONE
        |
        v
   IN_ESECUZIONE
        |
        v
    IN_CHIUSURA
        |
        v
      CHIUSA
```

È inoltre previsto lo stato `SOSPESA`.

Il campo `stato` (`APERTA/CHIUSA`) è uno stato tecnico distinto dal workflow.

### 9.1 Stati bloccanti

Dal codice di `apps/projects/workflow.py`:

- `SOSPESA` e `CHIUSA` bloccano l'operatività;
- `IN_CHIUSURA` blocca la creazione di nuovo lavoro, ma può consentire operazioni necessarie a completare lavoro già esistente;
- una fase `COMPLETATA` o `SOSPESA` blocca nuovo lavoro sulla fase.

### 9.2 Handover

Il workflow comprende un handover commerciale. Alcune transizioni richiedono che l'handover sia completato. Le modifiche del lifecycle passano dai servizi centralizzati in `apps/projects/services.py`.

### 9.3 Chiusura e riapertura

La chiusura/riapertura della commessa è protetta da regole di servizio; dal codice la chiusura amministrativa è riservata all'Admin LEF.

---

## 10. Pianificazione

Il modulo `apps/planning` governa l'agenda operativa.

Regole evidenti dai servizi:

- la data deve ricadere negli intervalli di commessa, assegnazione e fase;
- le ore pianificate devono essere intere;
- sono ammesse da 1 a 8 ore;
- esiste un controllo sul limite giornaliero;
- viene verificato il budget dell'assegnazione;
- non si possono creare pianificazioni su date già trascorse;
- le pianificazioni passate sono congelate per la normale modifica;
- viene evitata la duplicazione della pianificazione per lo stesso perimetro/data;
- solo la risorsa pianificata può confermare la conclusione della propria sessione;
- la conferma è soggetta allo stato di assegnazione, commessa e data.

Le autorizzazioni sono centralizzate in `apps/planning/permissions.py` e la logica transazionale in `apps/planning/services.py`.

---

## 11. Task e Teamwork

Il modulo `apps/tasks` gestisce il lavoro operativo collegato a commessa e fase.

Permessi principali dal codice:

- Admin può operare trasversalmente;
- membri attivi della fase e PM attivi possono avere capacità operative nel proprio perimetro;
- la Direzione Generale può avere visibilità di portafoglio ma non commentare come partecipante operativo;
- non si crea/modifica nuovo lavoro se commessa o fase sono in stato bloccante.

Il Teamwork di commessa aggrega le funzioni operative legate al progetto. Il routing è sotto `/gestione/commesse/...` e i moduli operativi hanno anche percorsi dedicati.

---

## 12. Timesheet, spese e approvazioni

Il modulo `apps/timesheets` gestisce ore e spese.

Le mutazioni principali passano da `apps/timesheets/services.py`, dove vengono applicati controlli su attore, assegnazione, periodo, modificabilità e approvazione.

Sono previste operazioni dedicate per:

- creazione/modifica delle ore;
- creazione/modifica delle spese;
- approvazione ore;
- rifiuto ore con motivazione;
- approvazione spese;
- rifiuto spese con motivazione.

Il modello conserva `versione`, ultima modifica, flag di intervento Admin e blocco per il consulente, così da supportare controllo e tracciabilità.

---

## 13. Periodi mensili e valorizzazione economica

`apps/operations/services/periodi.py` gestisce:

- individuazione della tariffa vigente;
- valorizzazione delle righe del periodo;
- conteggio stati di approvazione;
- identificazione delle righe senza tariffa;
- chiusura del periodo;
- riapertura del periodo.

La chiusura può registrare forzature per tariffe o approvazioni mancanti, insieme alla motivazione. Questo è importante per l'audit amministrativo.

---

## 14. Dashboard e report

Il modulo Operations contiene dashboard amministrative e PM.

Il codice definisce strutture dati per:

- aggregati economici;
- avanzamento commessa;
- dashboard Admin;
- avanzamento consulente/PM;
- dashboard PM.

Il reporting mensile supporta filtri su ore/spese e generazione XLSX tramite `openpyxl`.

Percorsi principali web sotto `/controllo/`; API equivalenti sotto `/api/v1/dashboard/` e `/api/v1/report/`.

---

## 15. Documenti

`apps/documents` gestisce documenti associati al lavoro di commessa/fase.

Azioni disponibili:

- elenco;
- upload;
- selezione/lettura fasi;
- download;
- eliminazione.

### 15.1 Sicurezza dei documenti

I documenti riservati sono conservati in `private_media`, directory separata da `MEDIA_ROOT`.

Nginx risponde `404` a `/private_media/`: il file riservato **non deve essere servito direttamente dal web server**. Il download passa da una view Django che può verificare i permessi.

Sono presenti utility dedicate in:

- `apps/common/file_security.py`;
- `apps/common/export_security.py`.

Il limite applicativo predefinito dei documenti è 10 MB; Nginx accetta richieste fino a 12 MB per consentire l'overhead multipart.

---

## 16. Notifiche

`apps/notifications` comprende:

- elenco notifiche;
- apertura della notifica;
- marca letta/non letta;
- marca tutte lette;
- preferenze utente;
- generazione automatica di notifiche task.

Il comando:

```bash
python manage.py generate_task_notifications
```

viene eseguito periodicamente nel servizio `reminder` della produzione.

---

## 17. Promemoria timesheet ed email

Il servizio `apps/operations/services/promemoria.py` gestisce:

- configurazione corrente;
- individuazione consulenti senza ore;
- controllo periodo chiuso;
- verifica della scadenza programmata;
- composizione/invio email;
- tracciamento degli esiti;
- email di test.

Comando principale:

```bash
python manage.py invia_promemoria_timesheet
```

### 17.1 Email per ambiente

**Development:** backend console di default.  
**Staging:** può usare `StagingRedirectEmailBackend`, che devia tutte le email verso destinatari di test.  
**Production:** SMTP configurato tramite variabili d'ambiente.

Se si abilita il backend di redirect staging, `EMAIL_REDIRECT_ALL_TO` deve contenere almeno un destinatario.

---

## 18. Importazioni massive

`apps/operations/import_services.py` supporta file CSV/XLSX.

Il flusso è progettato in due fasi:

1. lettura e validazione/anteprima;
2. conferma dell'importazione.

Sono presenti:

- normalizzazione header/valori;
- parsing date, interi e decimali;
- validazione assegnazioni;
- validazione righe ore/spese;
- serializzazione anteprima;
- commit dell'importazione;
- template XLSX;
- esportazione errori CSV.

La dimensione massima import predefinita è 5 MB (`IMPORT_MAX_UPLOAD_SIZE_MB`).

---

## 19. Audit

`AuditLog` registra operazioni rilevanti con:

- attore;
- entità;
- ID entità;
- azione;
- stato precedente;
- stato nuovo;
- motivazione;
- timestamp.

Sono disponibili interfacce web e API, oltre a export CSV. La visibilità trasversale dell'audit è prevista per Admin e Direzione Generale.

---

## 20. Autenticazione e sicurezza web

### 20.1 Login

- identificativo: email;
- sessioni Django;
- rate limiting login configurabile;
- password validator Django con lunghezza minima 10;
- middleware per cambio password obbligatorio;
- reset password;
- attivazione account tramite invito.

### 20.2 Header/cookie di sicurezza

Le impostazioni comprendono:

- `X_FRAME_OPTIONS = DENY`;
- `SECURE_CONTENT_TYPE_NOSNIFF = True`;
- `SECURE_REFERRER_POLICY = same-origin`;
- `SESSION_COOKIE_HTTPONLY = True`;
- SameSite `Lax`;
- cookie Secure configurabili;
- HSTS configurabile;
- redirect HTTPS configurabile;
- supporto `X-Forwarded-Proto` solo quando esplicitamente abilitato.

Con `DEBUG=False`, una `DJANGO_SECRET_KEY` non configurata e host mancanti provocano errore di configurazione invece di avviare l'app in modo insicuro.

---

## 21. API REST

Base path:

```text
/api/v1/
```

### 21.1 Risorse CRUD/router

- `clienti`;
- `commesse`;
- `assegnazioni`;
- `ore`;
- `spese`;
- `periodi`.

### 21.2 Autenticazione API

Endpoint principali:

```text
POST /api/v1/auth/token/
POST /api/v1/auth/logout/
GET  /api/v1/auth/me/
GET  /api/v1/auth/token/status/
POST /api/v1/auth/token/rotate/
```

Sono presenti metadati/token services, TTL, rotazione opzionale, touch interval, revoca e comandi amministrativi.

### 21.3 Dashboard/report API

```text
/api/v1/dashboard/me/
/api/v1/dashboard/admin/
/api/v1/dashboard/pm/
/api/v1/report/mensile/
/api/v1/report/mensile.xlsx
```

### 21.4 Operations API

Comprende endpoint per:

- configurazione/anteprima/invio/storico promemoria;
- importazioni e conferma;
- template XLSX;
- errori import CSV;
- audit ed export CSV;
- security status e gestione token.

### 21.5 Documentazione OpenAPI

Per utenti autenticati:

```text
/api/v1/schema/
/api/v1/docs/      # Swagger UI
/api/v1/redoc/     # ReDoc
```

### 21.6 Throttling e proxy

Sono configurabili separatamente limiti per:

- anonimi;
- burst utente;
- sustained utente;
- login;
- mutation;
- operazioni sensibili;
- import;
- export.

Quando `API_TRUST_X_FORWARDED_FOR=True`, `API_NUM_PROXIES` deve riflettere il numero reale di proxy fidati davanti all'applicazione.

---

## 22. URL web principali

Routing root rilevante:

```text
/                         home per ruolo
/login/                   login
/logout/                  logout
/admin/                   Django Admin
/gestione/consulenti/     persone, skill, Skill Matrix
/gestione/                clienti, commesse, assegnazioni, tariffe/workflow
/timesheet/               ore e spese
/controllo/               dashboard, report, periodi, audit, import, promemoria
/api/v1/                  API REST
/health/                  health
/health/ready/            readiness
```

Sono inoltre montati i moduli planning, task, notifiche, documenti e fasi tramite `config/urls.py`.

---

## 23. Variabili d'ambiente

**Non versionare mai i file reali `.env`, `.env.staging`, `.env.production`.** Versionare esclusivamente gli example privi di segreti.

### 23.1 Database

```text
POSTGRES_DB
POSTGRES_USER
POSTGRES_PASSWORD
POSTGRES_HOST
POSTGRES_PORT
```

### 23.2 Django

```text
DJANGO_SECRET_KEY
DJANGO_DEBUG
DJANGO_ALLOWED_HOSTS
DJANGO_CSRF_TRUSTED_ORIGINS
DJANGO_SESSION_COOKIE_NAME
DJANGO_CSRF_COOKIE_NAME
SITE_URL
```

### 23.3 HTTPS/security

```text
DJANGO_SECURE_SSL_REDIRECT
DJANGO_SESSION_COOKIE_SECURE
DJANGO_CSRF_COOKIE_SECURE
DJANGO_SECURE_HSTS_SECONDS
DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS
DJANGO_SECURE_HSTS_PRELOAD
DJANGO_TRUST_PROXY_SSL_HEADER
```

### 23.4 Upload

```text
DJANGO_DATA_UPLOAD_MAX_MEMORY_SIZE
DJANGO_FILE_UPLOAD_MAX_MEMORY_SIZE
DOCUMENTS_MAX_UPLOAD_SIZE_MB
IMPORT_MAX_UPLOAD_SIZE_MB
```

### 23.5 Login

```text
WEB_LOGIN_RATE_LIMIT
WEB_LOGIN_IP_RATE_LIMIT
WEB_LOGIN_RATE_WINDOW_SECONDS
WEB_REQUIRE_PASSWORD_CHANGED
```

### 23.6 Email

```text
EMAIL_BACKEND
EMAIL_REAL_BACKEND
EMAIL_REDIRECT_ALL_TO
EMAIL_STAGING_SUBJECT_PREFIX
DEFAULT_FROM_EMAIL
EMAIL_HOST
EMAIL_PORT
EMAIL_HOST_USER
EMAIL_HOST_PASSWORD
EMAIL_USE_TLS
EMAIL_USE_SSL
EMAIL_TIMEOUT
```

### 23.7 API

```text
API_TOKEN_TTL_HOURS
API_TOKEN_TOUCH_INTERVAL_MINUTES
API_ROTATE_TOKEN_ON_LOGIN
API_REQUIRE_PASSWORD_CHANGED
API_ANON_THROTTLE_RATE
API_USER_BURST_THROTTLE_RATE
API_USER_SUSTAINED_THROTTLE_RATE
API_LOGIN_THROTTLE_RATE
API_MUTATION_THROTTLE_RATE
API_SENSITIVE_THROTTLE_RATE
API_IMPORT_THROTTLE_RATE
API_EXPORT_THROTTLE_RATE
API_NUM_PROXIES
API_TRUST_X_FORWARDED_FOR
API_LOG_LEVEL
API_SECURITY_LOG_LEVEL
API_SECURITY_LOG_MUTATIONS
```

---

## 24. Avvio ambiente di sviluppo

### Prerequisiti

- Git;
- Docker Desktop / Docker Engine con Compose;
- porte richieste libere.

### Procedura

Da PowerShell nella root del repository:

```powershell
Copy-Item .env.example .env
```

Modificare almeno le credenziali di sviluppo se necessario, quindi:

```powershell
docker compose up -d --build
```

Migrazioni:

```powershell
docker compose exec -T web python manage.py migrate
```

Creazione superuser iniziale:

```powershell
docker compose exec web python manage.py createsuperuser
```

Applicazione:

```text
http://localhost:8000/
```

Health:

```text
http://localhost:8000/health/
```

### Comandi utili sviluppo

```powershell
docker compose ps
docker compose logs -f web
docker compose exec -T web python manage.py check
docker compose exec -T web python manage.py test --verbosity 1
docker compose down
```

Il compose di sviluppo monta la repository in `/app`, quindi le modifiche locali sono visibili al container.

---

## 25. Ambiente staging

Lo staging è isolato dal production database e usa:

```text
.env.staging
docker-compose.staging.yml
```

Nel setup attuale la porta HTTP predefinita è **8081**.

### 25.1 Avvio consigliato

Il repository contiene:

```powershell
.\scripts\staging\start_staging.ps1
```

Per operazioni Docker manuali, usare sempre un project name esplicito per evitare stack duplicati:

```powershell
docker compose -p lef-timesheet-staging -f docker-compose.staging.yml up -d --build
```

URL:

```text
http://localhost:8081/
```

### 25.2 Servizi staging

- `db`: PostgreSQL staging;
- `init_permissions`: prepara ownership dei volumi;
- `web`: migrate + collectstatic + Gunicorn;
- `scheduler`: esegue il comando promemoria periodicamente;
- `nginx`: reverse proxy e static/media.

### 25.3 Test staging

```powershell
.\scripts\staging\smoke_test_staging.ps1
.\scripts\staging\test_email_staging.ps1
```

È presente anche `test_restore_staging.ps1`, pensato per collaudare un backup in un database staging isolato senza modificare il database operativo originale.

---

## 26. Produzione

Configurazione:

```text
.env.production
docker-compose.prod.yml
```

Il compose dichiara il project name:

```text
lef-timesheet-prod
```

### 26.1 Prima configurazione

```powershell
Copy-Item .env.production.example .env.production
```

Sostituire **tutti** i placeholder, in particolare:

- password PostgreSQL;
- `DJANGO_SECRET_KEY` lunga e casuale;
- dominio reale;
- trusted origins;
- SMTP;
- impostazioni HTTPS/proxy coerenti con l'infrastruttura.

### 26.2 Preflight

```powershell
.\scripts\production\preflight_production.ps1
```

### 26.3 Avvio

```powershell
.\scripts\production\start_production.ps1
```

oppure manualmente:

```powershell
docker compose --env-file .env.production -f docker-compose.prod.yml up -d --build
```

### 26.4 Verifica

```powershell
.\scripts\production\check_production.ps1
```

Il controllo esegue anche `manage.py verifica_go_live`.

### 26.5 Log

```powershell
.\scripts\production\logs_production.ps1
```

### 26.6 Arresto applicativo

```powershell
.\scripts\production\stop_production.ps1
```

Lo script arresta i servizi applicativi conservando database e volumi.

### 26.7 Servizi production

- `db`;
- `init_permissions`;
- `web`;
- `reminder`;
- `nginx`.

`web` esegue automaticamente `migrate`, `collectstatic` e Gunicorn. Il servizio ha un healthcheck su `/health/ready/`. Nginx e reminder dipendono dalla salute del web.

---

## 27. Nginx e file statici

Nginx:

- inoltra l'app a `web:8000`;
- serve `/static/` dal volume static;
- serve `/media/` dal volume media;
- **nega `/private_media/`**;
- inoltra gli header proxy;
- usa `client_max_body_size 12m`;
- ha timeout di lettura proxy di 90 secondi.

In staging/production `collectstatic` viene eseguito all'avvio del web.

---

## 28. Health e readiness

Endpoint:

```text
/health/
/health/ready/
/api/v1/health/
```

`/health/ready/` è usato dall'healthcheck Docker production per stabilire quando il servizio web è realmente pronto.

---

## 29. Test

La suite è suddivisa per area:

```text
tests/api/
tests/domain/
tests/integration/
tests/operations/
tests/timesheets/
tests/ui/
```

Sono inoltre presenti test dentro alcuni moduli applicativi.

### 29.1 Esecuzione in Docker

```powershell
docker compose exec -T web python manage.py check
docker compose exec -T web python manage.py test --verbosity 1
```

### 29.2 Esecuzione locale Python

Con PostgreSQL configurato e dipendenze installate:

```bash
python -m pip install ".[dev]"
python manage.py check
python manage.py migrate --noinput
python manage.py test --verbosity 1
```

### 29.3 CI GitHub Actions

`.github/workflows/ci.yml` viene eseguito su `push` e `pull_request`.

La pipeline:

1. avvia PostgreSQL 18;
2. configura Python 3.13;
3. installa `.[dev]`;
4. esegue `manage.py check`;
5. applica le migrazioni;
6. esegue l'intera suite Django.

---

## 30. Management commands importanti

### Operations

```text
invia_promemoria_timesheet
collauda_ambiente
verifica_go_live
verifica_rilascio
```

### Notifications

```text
create_notification_preferences
generate_task_notifications
```

### API/security

```text
gestisci_token_api
pulisci_token_api
verifica_sicurezza_api
```

Per vedere gli argomenti esatti di un comando:

```powershell
docker compose exec web python manage.py help NOME_COMANDO
```

---

## 31. Backup

### 31.1 Backup completo raccomandato

Il database da solo **non contiene i file caricati**. Per disaster recovery usare il backup completo:

```powershell
.\scripts\backup\backup_nokihub.ps1 -ComposeFile docker-compose.prod.yml
```

Il bundle contiene:

- dump PostgreSQL;
- `private_media`;
- `media`.

### 31.2 Backup solo database

```powershell
.\scripts\backup\backup_postgres.ps1
```

Questo è utile per esigenze specifiche, ma **non è un backup completo dell'applicazione**.

---

## 32. Restore

Il restore è un'operazione potenzialmente distruttiva. Prima di eseguirlo verificare ambiente, backup e target.

### 32.1 Restore completo

```powershell
.\scripts\restore\restore_nokihub.ps1 `
  -BackupDirectory .\backups\nokihub_YYYYMMDD_HHMMSS `
  -ComposeFile docker-compose.prod.yml `
  -ConfirmRestore
```

Ripristina database + file riservati + media.

### 32.2 Restore solo PostgreSQL

È disponibile:

```text
scripts/restore/restore_postgres.ps1
```

### 32.3 Strategia raccomandata

Prima di un restore production:

1. verificare il backup in staging con `test_restore_staging.ps1`;
2. verificare health e login;
3. eseguire i controlli applicativi;
4. solo dopo pianificare il restore production.

---

## 33. Git e gestione del codice

File che **non devono essere committati**:

```text
.env
.env.production
.env.staging
*.sql
staticfiles/
media/
private_media/
backups/
logs/
__pycache__/
.venv/
```

Gli example `.env.*.example` devono invece rimanere versionati perché documentano la configurazione richiesta.

### Workflow semplice consigliato

- `main`: versione stabile;
- `develop`: integrazione delle modifiche, se si decide di adottarlo;
- `feature/...`: nuove funzionalità;
- `fix/...`: correzioni;
- `hotfix/...`: correzioni urgenti production.

Prima di ogni merge/rilascio:

```powershell
python manage.py check
python manage.py test --verbosity 1
```

oltre ai test staging previsti dal progetto.

---

## 34. Dove intervenire per modifiche comuni

| Esigenza | File/modulo da controllare per primo |
|---|---|
| Ruoli e permessi globali | `apps/accounts/access.py` |
| Utenti/Skill Matrix | `apps/accounts/` |
| Login/attivazione/reset | `apps/accounts/auth_views.py`, `templates/registration/` |
| Clienti/commesse | `apps/projects/` |
| Lifecycle commessa | `apps/projects/workflow.py`, `apps/projects/services.py` |
| Fasi | `apps/phases/` |
| Assegnazioni/tariffe | `apps/projects/models.py`, `forms.py`, `services.py` |
| Planning/calendario | `apps/planning/` |
| Task/Teamwork | `apps/tasks/`, template `projects/commessa_teamwork.html` |
| Ore/spese | `apps/timesheets/` |
| Periodi/approvazioni | `apps/operations/services/periodi.py` |
| Dashboard | `apps/operations/services/dashboard.py` |
| Report Excel | `apps/operations/report_services.py` |
| Import | `apps/operations/import_services.py` |
| Promemoria | `apps/operations/services/promemoria.py` |
| Documenti | `apps/documents/`, `apps/common/file_security.py` |
| Notifiche | `apps/notifications/` |
| API | `apps/api/` |
| Configurazione Django | `config/settings.py` |
| Routing root | `config/urls.py` |
| UI globale | `templates/base.html`, `static/css/` |
| Login UI | `templates/registration/login.html`, `static/css/login.css` |
| Docker | `docker-compose*.yml`, `deploy/docker/Dockerfile` |
| Nginx | `deploy/nginx/default.conf` |
| CI | `.github/workflows/ci.yml` |
| Backup/restore | `scripts/backup/`, `scripts/restore/` |

---

## 35. Convenzioni per sviluppare senza rompere il dominio

1. **Non bypassare i service layer** per operazioni che hanno già un servizio dedicato.
2. **Non duplicare i permessi nelle sole view**: usare/estendere le funzioni centralizzate.
3. **Non confondere ruolo organizzativo e PM di commessa**.
4. **Non servire `private_media` direttamente da Nginx**.
5. **Non modificare retroattivamente migrazioni già distribuite**: crearne una nuova.
6. **Non inserire segreti nel repository**.
7. Prima di modificare date di commessa/fase/assegnazione, considerare i vincoli sui dati figli.
8. Rispettare gli stati workflow bloccanti prima di creare planning/task/nuovo lavoro.
9. Eseguire test e `manage.py check` prima del commit.
10. Provare modifiche infrastrutturali in staging prima della produzione.

---

## 36. Checklist prima di un rilascio

- working tree Git pulito;
- migrazioni create e versionate;
- `python manage.py check` OK;
- suite test OK;
- CI GitHub OK;
- `.env.production` completo e non versionato;
- secret/password reali non presenti nel repository;
- backup recente disponibile;
- restore del backup provato periodicamente in staging;
- `preflight_production.ps1` OK;
- staging avviato e smoke test OK;
- login e ruoli principali verificati;
- health/readiness OK;
- email verificate senza invii accidentali da staging;
- documenti privati non accessibili direttamente;
- procedure di rollback/restore disponibili;
- dopo deploy: `check_production.ps1` e controllo log.

---

## 37. Troubleshooting rapido

### Docker usa lo stack sbagliato

In staging usare esplicitamente:

```powershell
docker compose -p lef-timesheet-staging -f docker-compose.staging.yml ps
```

Questo evita di creare accidentalmente uno stack con il nome derivato dalla directory.

### Staging non risponde

```powershell
docker compose -p lef-timesheet-staging -f docker-compose.staging.yml ps
docker compose -p lef-timesheet-staging -f docker-compose.staging.yml logs web --tail 100
docker compose -p lef-timesheet-staging -f docker-compose.staging.yml logs nginx --tail 100
```

### Migrazioni

```powershell
docker compose exec -T web python manage.py showmigrations
docker compose exec -T web python manage.py migrate
```

### Statici non aggiornati in staging/production

Il container web esegue `collectstatic` all'avvio. Ricostruire/riavviare lo stack corretto e verificare i log.

### Errore database

Controllare:

- container `db` healthy;
- `POSTGRES_DB`;
- `POSTGRES_USER`;
- `POSTGRES_PASSWORD`;
- `POSTGRES_HOST=db` dentro Docker;
- migrazioni.

### Email staging

Non usare destinatari reali senza controllo. Preferire il backend console o il backend di redirect staging configurato con `EMAIL_REDIRECT_ALL_TO`.

---

## 38. Stato della documentazione nel repository analizzato

Il README precedente faceva riferimento a una directory `docs/` con documenti quali architettura, modello di dominio, ruoli, API e deployment. **Quella directory non è presente nell'archivio Git analizzato**. Per questo motivo questo README è stato reso intenzionalmente autosufficiente e non contiene collegamenti a file `docs/*.md` inesistenti.

Nel repository sono invece presenti diversi documenti storici/audit alla root (`ALLINEAMENTO_AUDIT_...`, `BACKEND_AUDIT_...`, `REVISIONE_...`, `VALIDAZIONE_FINALE_...`, ecc.). Sono utili come cronologia tecnica, ma non vanno considerati sostitutivi del codice corrente.

---

## 39. Sicurezza e gestione dei segreti

Non pubblicare mai:

- `DJANGO_SECRET_KEY` reale;
- password PostgreSQL;
- credenziali SMTP;
- token API;
- dump del database;
- documenti caricati dagli utenti;
- backup applicativi;
- file `.env` reali.

Se un segreto viene accidentalmente committato e soprattutto pubblicato su un remote, **rimuoverlo dal file non basta**: va considerato compromesso, ruotato e, se necessario, eliminato dalla cronologia Git.

---

## 40. Note per il passaggio di consegne

Una nuova persona che prende in carico LEFTRACK dovrebbe seguire questo ordine:

1. leggere questo README;
2. avviare l'ambiente development;
3. leggere `config/settings.py` e `config/urls.py`;
4. comprendere `apps/accounts/access.py`;
5. leggere i modelli in `accounts`, `projects`, `phases`, `planning`, `tasks`, `timesheets`, `operations`;
6. studiare `apps/projects/workflow.py` e i service layer;
7. eseguire l'intera suite di test;
8. avviare lo staging isolato;
9. verificare backup/restore e comandi di go-live prima di operare sulla produzione.

Questa sequenza permette di comprendere prima il dominio e poi l'infrastruttura, riducendo il rischio di introdurre modifiche che aggirino permessi, workflow o vincoli esistenti.

---

## 41. Licenza e proprietà

Nel repository analizzato non è presente una licenza software definitiva. Prima di rendere il repository pubblico o distribuire il codice al di fuori del perimetro autorizzato LEF, la titolarità e le condizioni di utilizzo devono essere definite dal titolare dei diritti.

---

## 42. Riepilogo operativo

Per lavorare sul progetto in sicurezza:

```text
SVILUPPO
.env + docker-compose.yml
        |
        v
modifica -> test -> commit
        |
        v
STAGING
.env.staging + docker-compose.staging.yml
        |
        v
smoke test / test funzionali / restore test
        |
        v
PRODUCTION
.env.production + docker-compose.prod.yml
        |
        v
preflight -> backup -> deploy -> health/go-live check
```

**Principio guida:** sviluppo e staging possono cambiare frequentemente; la produzione deve ricevere solo modifiche versionate, testate e accompagnate da una possibilità concreta di ripristino.
