# LEF Timesheet — revisione Commessa → Fase

Questa revisione parte dalla versione Teamwork già implementata e consolida il modello gestionale sul principio:

**Commessa → Fasi → Operatività**

La Commessa resta il contenitore generale/contrattuale. La Fase è l'unità operativa e di controllo.

## Regole consolidate

- Ogni commessa dispone sempre di una fase tecnica `Generale`. Serve alle commesse che non richiedono una scomposizione esplicita e rende la Fase sempre disponibile senza obbligare l'utente a creare una struttura complessa.
- Le assegnazioni operative sono riferite a una fase. Un consulente può quindi essere assegnato a Fase A e non a Fase B della stessa commessa.
- `ore_previste`, planning e tariffe seguono l'assegnazione e quindi sono automaticamente riferiti alla fase.
- Il calendario è il calendario operativo della squadra della singola fase.
- Un consulente vede e opera sui task della fase a cui appartiene.
- I task hanno una fase obbligatoria e la fase deve appartenere alla stessa commessa del task.
- Tutti i membri della fase possono creare, modificare, cambiare stato e cancellare i task secondo le regole Teamwork già definite; le azioni generano notifiche.
- I documenti possono essere riferiti a una fase oppure restare documenti generali della commessa (es. contratto).
- Le pianificazioni passate restano congelate anche per Admin.
- Le date della fase sono coerenti con le date della commessa; la data di inizio della fase è obbligatoria.
- Una fase conclusa può essere modificata da PM/Admin finché la commessa resta aperta.
- Dashboard, report e periodo mantengono il livello Commessa ma espongono anche il dettaglio Fase.
- I promemoria mantengono la logica mensile esistente ma riportano anche le fasi operative assegnate.

## Migrazione dati

Le migrazioni creano una fase `Generale` per le commesse esistenti che ne sono prive e collegano le vecchie assegnazioni alla fase tecnica. I task esistenti senza fase vengono ricondotti alla fase dell'assegnatario; in assenza di una corrispondenza viene usata `Generale`.

## Principio di progettazione

Non viene duplicata la logica economica a livello Fase: la Commessa continua ad aggregare i dati delle proprie fasi. Il dettaglio operativo viene invece mantenuto alla dimensione Fase, così da poter calcolare:

- ore assegnate / pianificate / consuntivate;
- residui e scostamenti;
- valore delle ore tramite tariffa;
- spese;
- attività aperte/completate;
- documenti;
- composizione del team;
- andamento della singola fase e aggregazione sulla commessa.
