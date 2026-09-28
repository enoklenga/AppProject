# NOKIHUB — Backend Audit Step 2

Data: 21/09/2026

## Obiettivo

Questo step chiude i finding P1 BK-004 → BK-011 dell'audit backend, concentrandosi su integrità storica, coerenza temporale, locking dei periodi e cambio password obbligatorio.

## Stato finding

| ID | Tema | Stato Step 2 |
|---|---|---|
| BK-004 | Modifica assegnazione con effetti retroattivi | **FIXED** |
| BK-005 | Riattivazione assegnazione senza business validation | **FIXED** |
| BK-006 | Modifica date commessa può invalidare figli | **FIXED** |
| BK-007 | Modifica date fase può invalidare figli | **FIXED** |
| BK-008 | Eliminazione fase e FK `PROTECT` | **FIXED** |
| BK-009 | Race chiusura periodo vs ore/spese/import | **FIXED** |
| BK-010 | Tariffe retroattive su mesi chiusi | **FIXED** |
| BK-011 | `deve_cambiare_password` non enforced sul web | **FIXED** |

---

## BK-004 — Integrità storica assegnazioni

Interventi:

- `AssegnazioneForm` impedisce di cambiare `consulente`, `commessa` o `fase` quando esistono ore, spese, planning o tariffe storiche.
- Le date dell'assegnazione non possono essere ristrette in modo da escludere record storici.
- `ore_previste` non può scendere sotto le ore già pianificate.
- `Assegnazione.save()` applica una difesa equivalente anche ai salvataggi diretti, non solo alla UI.
- Dopo la creazione, il campo `stato` è disabilitato nel form di modifica: conclusione/riattivazione passano dal workflow dedicato.
- Create/update da UI acquisiscono lock coerenti su Commessa → Fase → Assegnazione e rivalidano il form sotto lock.
- Creazione e modifica assegnazione da UI vengono tracciate in `AuditLog`.

Regola risultante: per cambiare l'identità operativa di una assegnazione con storia, concludere la vecchia assegnazione e crearne una nuova.

---

## BK-005 — Riattivazione assegnazione

È stato introdotto `apps/projects/services.py::set_assegnazione_stato()`.

La riattivazione verifica:

- utente attivo;
- commessa aperta;
- fase appartenente alla commessa;
- fase non completata;
- date coerenti con commessa e fase;
- assenza di altra assegnazione attiva per `consulente + fase`.

Il service usa `select_for_update()` e registra audit per conclusione/riattivazione.

---

## BK-006 — Coerenza date Commessa

Interventi:

- `CommessaForm` verifica fasi esplicite, assegnazioni, ore, spese, planning e date Task prima di restringere l'intervallo.
- `CommessaUpdateView` acquisisce lock su Commessa → Fasi → Assegnazioni e rivalida il form dentro la transazione.
- Creazioni concorrenti di Fasi/Assegnazioni/Task vengono serializzate sul medesimo perimetro di lock.
- `Commessa.save()` contiene una difesa aggiuntiva per modifiche dirette delle date.
- La fase tecnica `Generale` viene riallineata alle date della Commessa dopo un aggiornamento consentito.
- Anche Django Admin usa `CommessaForm` e riallinea `Generale`.

---

## BK-007 — Coerenza date Fase

`update_fase()` ora:

- blocca Commessa → Fase → Assegnazioni;
- impedisce di escludere assegnazioni esistenti;
- impedisce di escludere ore, spese e planning;
- impedisce di lasciare Task con inizio/scadenza fuori fase.

Inoltre:

- `FaseCommessa.save()` applica una difesa equivalente sulle modifiche dirette delle date;
- Task e Planning validano esplicitamente le date anche rispetto alla Fase;
- `create_task()` / `update_task()` condividono lock Commessa/Fase con il workflow di modifica Fase.

---

## BK-008 — Eliminazione Fase

`delete_fase()` verifica esplicitamente almeno:

- assegnazioni;
- attività;
- documenti.

È inoltre presente una cattura finale di `ProtectedError`, convertita in `ValidationError`, così eventuali nuove FK `PROTECT` non si trasformano in HTTP 500.

---

## BK-009 — Protocollo unico per PeriodoMensile

Nuovo modulo: `apps/operations/period_lock.py`.

Protocollo:

1. ogni mese operativo dispone di una riga `PeriodoMensile`;
2. mutazioni ore/spese acquisiscono `select_for_update()` sul periodo prima della scrittura;
3. spostamenti tra mesi bloccano entrambi i periodi in ordine stabile;
4. approvazioni/rifiuti/cancellazioni usano lo stesso lock;
5. gli import massivi passano già per `inserisci_ore()` / `inserisci_spesa()`, quindi ereditano il protocollo;
6. `chiudi_periodo()` acquisisce il lock **prima** di ricalcolare e validare il riepilogo.

Questo elimina la finestra in cui una riga poteva entrare nel mese dopo i controlli ma prima della chiusura.

---

## BK-010 — Tariffe e periodi chiusi

Policy implementata: **una nuova decorrenza non può cambiare la valorizzazione di ore appartenenti a periodi già chiusi**.

Interventi:

- `TariffaAssegnazioneForm` individua le righe che verrebbero rivalorizzate e blocca l'operazione se coinvolgono mesi chiusi;
- `TariffaCreateView` ripete il controllo sotto lock transazionale;
- il model `TariffaAssegnazione` contiene una difesa anche per salvataggi diretti;
- Django Admin usa lo stesso form e il controllo con lock.

Per cambiare una tariffa che impatta un mese chiuso, il periodo deve prima essere riaperto tramite il workflow auditato.

---

## BK-011 — Cambio password obbligatorio

Aggiunti:

- `apps/accounts/middleware.py::ForcePasswordChangeMiddleware`;
- `NokihubPasswordChangeView`;
- `NokihubPasswordResetConfirmView`;
- setting `WEB_REQUIRE_PASSWORD_CHANGED`.

Quando la policy è attiva e `deve_cambiare_password=True`, l'utente web viene reindirizzato al cambio password fino al completamento corretto. Cambio e reset azzerano il flag.

Configurazione:

- development example: policy web/API disattivabile;
- staging: web/API abilitate;
- production: web/API abilitate;
- il preflight production verifica che entrambe siano realmente abilitate.

---

## Test aggiunti

- `tests/domain/test_backend_integrity_step2.py`
  - identità storica assegnazioni;
  - restrizione date;
  - riattivazione con commessa/fase non valida;
  - coerenza Commessa/Fase;
  - `ProtectedError` fase;
  - tariffa vs periodo chiuso;
  - creazione/lock periodo aperto;
  - Task fuori intervallo fase;
  - protezione anche su salvataggi diretti;
  - stato assegnazione modificabile solo tramite workflow;
  - riallineamento fase `Generale`.
- `tests/integration/test_password_enforcement.py`
  - redirect obbligatorio;
  - azzeramento flag dopo cambio password.

## Verifiche eseguite qui

- `python -m compileall`: **OK**.
- Nessuna modifica di schema/modelli DB che richieda migration: sono stati modificati metodi/validazioni, non campi o constraint.

La suite Django/PostgreSQL deve essere eseguita nel container del progetto, come già fatto per Step 1.

## Comandi di verifica consigliati

```powershell
docker compose exec web python manage.py test tests.domain.test_backend_integrity_step2 tests.integration.test_password_enforcement --keepdb -v 2

docker compose exec web python manage.py check
docker compose exec web python manage.py makemigrations --check --dry-run

docker compose exec web python manage.py test apps.documents.tests apps.notifications.tests apps.phases.tests apps.planning.tests apps.tasks.tests tests.api tests.domain tests.integration tests.operations tests.timesheets --keepdb -v 1
```

Dopo il backend mirato, eseguire anche la suite completa; i failure UI/branding già noti sono separati dallo Step 2.
