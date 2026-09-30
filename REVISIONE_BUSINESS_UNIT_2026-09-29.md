# LEFTRACK — Gestione Business Unit e revisione dei ruoli
Data: 29/09/2026 · Riferimento: flusso TO-BE Consulenza

## 1. Modello dei ruoli

| Profilo | Cosa gestisce | Perimetro |
|---|---|---|
| **Admin LEF** | **Piattaforma** (account, ruoli, inviti, nomina dei Responsabili BU, token API) + tutta la gestione | Tutta l'azienda |
| **Amministrazione** | Tutto ciò che gestisce l'Admin **tranne la piattaforma**: clienti, commesse (apertura/chiusura), assegnazioni, tariffe, approvazioni, chiusura del mese, pianificazione, attività, documenti, report, promemoria, importazioni, audit, Business Unit e appartenenze, catalogo skill | Tutta l'azienda |
| **Responsabile Business Unit** | La stessa interfaccia di gestione dell'Admin **più** la sezione "La mia Business Unit" | Solo commesse e persone della propria BU |
| Commerciale, Direzione Generale | Invariati (portafoglio / lettura direzionale); la DG vede anche le Business Unit | Tutta l'azienda |
| Consulente / PM | Invariati | Le proprie assegnazioni |

- Il Responsabile BU, fuori dalla sua BU, è una **normale risorsa**: può essere consulente o PM di commesse di altre BU (es. Roberta: Responsabile di Consulenza, consulente in Formazione).
- Sulle **proprie** ore e spese anche il Responsabile agisce come consulente: niente blocco "modificato dall'Admin" e **nessuno può approvare le proprie ore/spese**.
- La **chiusura del mese resta aziendale** (Admin e Amministrazione): il Responsabile BU vede la pagina "Approvazioni" filtrata sulla sua BU.
- Avere il ruolo "Responsabile Business Unit" non basta: serve la **nomina** su una BU (Business Unit › Appartenenze, solo l'Admin). Senza nomina la persona vede l'interfaccia da consulente con un avviso.

Tutte le regole sono in un solo file, `apps/accounts/access.py` (`is_platform_admin`, `is_global_manager`, `managed_business_unit_ids`, `can_manage_commessa`, `commesse_in_scope`, `persone_in_scope`, `perimetro_business_unit`…). I circa 85 controlli `is_admin_lef` sparsi nel codice sono stati sostituiti da queste funzioni; `is_admin_lef` resta solo dove si parla di piattaforma.

## 2. Nuove funzioni

- **Cruscotto Business Unit** (`/gestione/consulenti/business-unit/<id>/`): responsabili, indicatori del mese (persone, PM abilitati, commesse aperte, commesse senza PM, handover da completare, ore pianificate e consuntivate, da approvare), team con carico rispetto alla capacità (giorni lavorativi × 8 h), commesse della BU con azioni "Team" e "Modifica", "Aggiungi persona" e "Nuova commessa" già precompilate sulla BU.
- **Home del Responsabile BU**: KPI della BU, commesse aperte (evidenzia quelle senza PM), carico delle persone, link al proprio lavoro da consulente/PM.
- **Home di Admin e Amministrazione** unificate: indicatori generali, controllo del mese, schede di tutte le BU, avviso sulle commesse aperte senza BU, commesse recenti con la loro BU.
- **Menu laterale unico guidato dai permessi**: un solo menu per tutti i profili (gruppi "La mia Business Unit", Operatività, Portafoglio, Organizzazione, Controllo). Una voce compare solo se l'utente può davvero aprire la pagina.
- **Filtro Business Unit** su Commesse, Dashboard, Chiusura/Approvazioni e Report mensile (per il Responsabile è sempre forzato sulla sua BU, anche se prova a chiederne un'altra).
- Ogni **nuova commessa deve avere una BU** (le commesse storiche restano modificabili e sono segnalate come "Da classificare").
- **Dashboard di progetto** disponibile anche per Admin, Amministrazione e Responsabile BU (prima risultava vuota per l'Admin).
- **API**: back office e dashboard aperti ad Admin e Amministrazione; i token API restano all'Admin; le liste ore/spese/assegnazioni includono le commesse della BU per il Responsabile.

## 3. Errori trovati e corretti

| Problema | Effetto | Correzione |
|---|---|---|
| Le pagine Business Unit non erano nella configurazione della navigazione | Errore 500 (KeyError) all'apertura di elenco, modifica e appartenenze BU | Sezione "Business Unit" aggiunta con etichette e percorso di ritorno |
| I form riconoscevano la "creazione" con `instance.pk`, ma gli id UUID esistono già prima del salvataggio | Nella nuova assegnazione il campo Stato era sempre bloccato con un messaggio pensato per la modifica; alcune verifiche "solo in modifica" giravano anche in creazione | Uso di `_state.adding` in Commessa, Assegnazione e Persona |
| Date di inizio/fine delle appartenenze BU senza widget data | Date mostrate vuote in modifica e cancellate al salvataggio (stesso difetto già corretto negli altri form) | Widget ISO condiviso |
| Test BU con fase "Generale" creata due volte | 2 test in errore | Uso della fase di sistema già creata con la commessa |
| Parametri GET non validi (`?bu=abc`, `?commessa=abc`) | Errore 500 in Documenti e nei nuovi filtri | Validazione UUID (`uuid_valido`) |
| Link "Gestisci skill" e "Valuta" mostrati a chi non poteva usarli | Link che portavano a 403/404 | Visibili solo con il permesso corrispondente |
| Icona Android con percorso sbagliato (`branding/…` invece di `images/branding/…`) | Icona non trovata | Percorso corretto + `site.webmanifest` |

## 4. Branding
Il kit LEF (favicon 16/32, `favicon.ico`, apple-touch, android 192/512, `leftrack-logo`, `leftrack-mark` in PNG/SVG) è installato in `static/images/branding/` con **gli stessi nomi** dei file precedenti: non è stato necessario toccare i template.

## 5. Verifica
- **360 test**, di cui 23 nuovi in `tests/integration/test_business_unit_scope.py`. Passano tutti tranne i 3 già noti (`collauda_ambiente`, `verifica_go_live`), che richiedono PostgreSQL e vanno eseguiti in staging.
- `makemigrations --check`: nessuna migrazione necessaria (nessuna modifica al database).
- Esplorazione automatica delle pagine con 9 utenti (Admin, Amministrazione, 2 Responsabili BU, Commerciale, DG, 3 consulenti/PM): nessun errore 500 e nessun link visibile che porti a un 403.
- Accessi incrociati tra BU: il Responsabile di Formazione riceve 404/403 su commesse, assegnazioni, appartenenze, ore, spese, Teamwork, handover, workflow e dashboard di Consulenza; le approvazioni e i cambi di stato fuori perimetro vengono rifiutati.

## 6. Da fare al rilascio
1. Creare le BU reali (es. Consulenza, Formazione), dare il ruolo "Responsabile Business Unit" ai responsabili e nominarli in Business Unit › Appartenenze.
2. Classificare le commesse aperte "Da classificare" (la home Admin/Amministrazione le segnala).
3. `collectstatic` (nuovo `css/business-unit.css`, icone e manifest).

## 7. Proposte dal flusso TO-BE (non implementate)
- **Approvazione offerte con margine ≤ 20%** da parte della DG: oggi l'offerta non è nel sistema; si può aggiungere uno stato "Offerta" con margine e approvazione DG prima dell'apertura della commessa.
- **ODA / eSolver / SharePoint**: campi per il numero ODA e il codice eSolver sulla commessa e link alla cartella SharePoint, oppure un'esportazione verso eSolver.
- **Disponibilità risorse per il Responsabile BU**: vista calendario del carico del team (i dati ci sono già in pianificazione) e richiesta di risorse a un'altra BU.
- **Riunione di chiusura e deliverable**: checklist di chiusura della commessa (verbale, deliverable consegnati) prima della chiusura amministrativa.
- **Segregazione dei compiti**: valutare se anche l'Amministrazione debba poter creare account per il solo ruolo Consulente (oggi resta all'Admin, come richiesto: "l'Admin gestisce la piattaforma").
