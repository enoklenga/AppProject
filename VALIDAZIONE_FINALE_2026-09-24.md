# LEFTRACK — validazione finale 2026-09-24

## Stato verificato nello staging utente

- `python manage.py check`: nessun problema rilevato.
- Suite audit `tests.domain.test_audit_20260924_regressions`: 12/12 test OK.
- Suite completa: 314 test eseguiti, con un solo failure residuo prima di questa correzione.

## Ultima correzione

Il test API `test_admin_can_exceed_eight_hours_and_creates_audit` era rimasto allineato alla regola precedente: tentava di portare il totale giornaliero Admin da 8 a 10 ore senza inviare una motivazione.

La regola LEFTRACK corrente, introdotta dall'audit M4, richiede invece una motivazione esplicita quando un Admin supera 8 ore giornaliere. Il service applicativo risponde correttamente `400` quando la motivazione manca.

Il test è stato quindi aggiornato per:

1. inviare `motivazione="Eccezione amministrativa oltre 8 ore."`;
2. attendersi `201`;
3. verificare l'avviso `limite_giornaliero_superato`;
4. verificare il blocco della riga per il consulente;
5. verificare che l'`AuditLog` contenga anche la motivazione fornita.

Non sono state introdotte nuove migrazioni.

## Comandi di verifica consigliati

```powershell
docker compose -p lef-timesheet-staging `
  --env-file .env.staging `
  -f docker-compose.staging.yml `
  exec web python manage.py test `
  tests.api.test_api_write.ApiWriteTests.test_admin_can_exceed_eight_hours_and_creates_audit `
  --verbosity 2
```

Poi:

```powershell
docker compose -p lef-timesheet-staging `
  --env-file .env.staging `
  -f docker-compose.staging.yml `
  exec web python manage.py test --verbosity 1
```

Il risultato atteso della suite completa è `OK` su 314 test.
