# LEFTRACK — Correzioni test/runtime 24/09/2026

## Origine
Secondo passaggio dopo l'allineamento dell'audit backend. La suite staging ha eseguito 314 test con 59 failure e 4 errori.

## Cause radice corrette

### 1. Policy cambio password durante i test
Lo staging abilita correttamente `WEB_REQUIRE_PASSWORD_CHANGED=True` e `API_REQUIRE_PASSWORD_CHANGED=True`.
La suite generale, però, crea numerosi utenti di test con `deve_cambiare_password=True` per default: ne risultavano redirect 302 lato web e 401 lato API prima che il test raggiungesse la funzionalità realmente verificata.

Correzione: in `config/settings.py` le due policy sono disabilitate esclusivamente quando il comando Django è `test`. I test dedicati alla password obbligatoria continuano ad abilitarla esplicitamente tramite `override_settings`, quindi la regola di sicurezza resta coperta e rimane attiva nello staging/prod reali.

### 2. `agenda_progress()`
L'alias aggregato `ore_pianificate` coincideva con il campo del modello. Nella stessa `aggregate()` Django 5.2 risolveva i successivi `Sum("ore_pianificate")` come riferimento a un aggregato, generando `FieldError`.

Correzione: alias rinominato in `ore_pianificate_totali`.

### 3. Test periodo chiuso
Il test audit creava una sessione planning, che inizializza già il periodo mensile, e poi tentava di creare un secondo `PeriodoMensile` con stessa coppia anno/mese.

Correzione: il test usa il periodo già esistente (`get_or_create`) e lo porta a `CHIUSO`.

### 4. Test attivazione account
Il form corrente richiede il nuovo campo `ruolo` organizzativo, mentre i test precedenti non lo inviavano. I test sono stati riallineati inviando `CONSULENTE` in creazione e il ruolo corrente in modifica. Aggiornati inoltre i riferimenti di branding da Nokihub a LEFTRACK e la verifica del testo del recupero password.

### 5. Test UI/branding obsoleti
I test statici facevano riferimento alla precedente UI (`lef-logo.png`, vecchio login, gruppo `Anagrafiche`). Sono stati riallineati alla UI corrente (`leftrack-mark.png`, `auth-login`, gruppo `Gestione`) senza ripristinare componenti legacy.

### 6. Contratti UI e refuso HTML
- canonicalizzata `font-variant-numeric: tabular-nums` nel CSS;
- rimosso il wording legacy `Dashboard PM` da titolo/commento sorgente in favore di `Dashboard di progetto`;
- corretto `<th scope="col"ead>` in `<thead>` nel partial degli aggregati.

## Verifiche disponibili nell'ambiente di modifica
- `python -m compileall -q .`: OK
- parsing AST di tutti i file Python: OK
- marker conflitto Git: nessuno
- contratti statici UI interessati: verificati localmente

## Verifica runtime richiesta in staging
L'ambiente di modifica non dispone di Django/Docker, quindi la suite completa deve essere rieseguita nel container staging:

```powershell
docker compose -p lef-timesheet-staging `
  --env-file .env.staging `
  -f docker-compose.staging.yml `
  up -d --build --force-recreate web

docker compose -p lef-timesheet-staging `
  --env-file .env.staging `
  -f docker-compose.staging.yml `
  exec web python manage.py check

docker compose -p lef-timesheet-staging `
  --env-file .env.staging `
  -f docker-compose.staging.yml `
  exec web python manage.py test tests.domain.test_audit_20260924_regressions --verbosity 2

docker compose -p lef-timesheet-staging `
  --env-file .env.staging `
  -f docker-compose.staging.yml `
  exec web python manage.py test --verbosity 1
```

Non sono state aggiunte nuove migrazioni in questo passaggio.
