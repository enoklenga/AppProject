# LEF Timesheet Project — modifiche implementate

## Scope recepito

La revisione implementa solo le funzionalità richieste come applicative dopo il confronto con il TO-BE. Le attività indicate come manuali/SharePoint/altro gestionale non sono state automatizzate.

### Implementato
- Ciclo di vita della commessa e handover leggero (senza checklist di completezza).
- Skill Matrix configurabile con 3 livelli (1/2/3) per risorsa.
- Nuovi ruoli organizzativi: Responsabile consulenza/Business Unit, Amministrazione, Commerciale, Direzione Generale; Project Manager resta ruolo per commessa.
- Agenda come fonte della disponibilità: massimo 8 ore/giorno e riepilogo settimanale occupato/disponibile.
- Conferma della conclusione di ogni sessione da parte della risorsa assegnata.
- Generazione/aggancio automatico della riga timesheet alla conferma della sessione.
- Immutabilità della sessione confermata e della riga timesheet generata dall'agenda.
- Avanzamento commessa su ore e sessioni agenda confermate.
- Gate di chiusura: la commessa non si chiude se esistono sessioni agenda non confermate o non collegate al timesheet.
- Audit della conferma sessione, handover e chiusura/riapertura commessa.
- API commessa estesa con workflow/handover.

### Deliberatamente non implementato (gestione manuale secondo indicazioni)
- Checklist di completezza dell'handover.
- Creazione e permessi SharePoint.
- Milestone applicative/baseline avanzata.
- Conferma pianificazione cliente.
- Kick-off interno/cliente.
- Issue/risk/change request e relative approvazioni/versioning.
- Deliverable con workflow di approvazione cliente (resta upload documenti).
- Rendicontazione economica di chiusura.
- Closing meeting.
- Integrazioni ActiveCampaign/eSolver/ODA.

## Ruoli e permessi
I nuovi ruoli organizzativi sono stati aggiunti all'anagrafica e ai filtri. Per evitare di attribuire privilegi non definiti, la matrice autorizzativa esistente non è stata ampliata automaticamente: Admin mantiene i privilegi amministrativi; l'accesso operativo continua a dipendere dalle assegnazioni/ruolo PM di commessa.

## Migrazioni nuove
- apps/accounts/migrations/0003_roles_skill_matrix.py
- apps/projects/migrations/0005_commessa_workflow_handover.py
- apps/planning/migrations/0002_session_confirmation.py

## Debug / validazioni eseguite
- Compilazione sintattica Python dell'intero progetto: OK.
- Parsing AST di tutti i file Python: OK.
- Controllo marker di merge: OK (nessuno).
- Controllo bilanciamento tag Django principali nei template modificati: OK.
- Test aggiunto: apps/planning/tests/test_session_confirmation.py.

### Limite ambiente di collaudo
Nel container usato per la revisione non è installato Django e non è disponibile accesso a PyPI/Docker; quindi non è stato possibile eseguire `manage.py check`, le migrazioni reali e la suite Django. Prima del merge/deploy eseguire nell'ambiente del progetto:

```bash
docker compose up -d --build
docker compose exec -T web python manage.py migrate
docker compose exec -T web python manage.py check
docker compose exec -T web python manage.py test --verbosity 1
```
