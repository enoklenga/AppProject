# LEFTRACK — UI/UX FINAL ALIGNMENT
Data: 24/09/2026

## Obiettivo
Allineamento completo del frontend LEFTRACK a un unico sistema visivo, mantenendo invariati backend, permessi, workflow e regole applicative.

## Standard globale introdotto
È stato aggiunto `static/css/ui-final.css`, caricato dopo tutti i CSS specifici delle singole pagine. Il file normalizza:
- gerarchia tipografica;
- H1/H2/eyebrow/topbar;
- spaziature verticali e orizzontali;
- superfici, card, pannelli, bordi e ombre;
- pulsanti primary/secondary/ghost/danger;
- campi input/select/textarea;
- form e footer dei form;
- filtri e relative griglie;
- badge e stati;
- tabelle e colonne Azioni;
- KPI e metric card;
- empty state;
- responsive desktop/tablet/mobile.

## Sezioni riallineate
### Home consulente
- eliminata microcopy ridondante;
- KPI resi coerenti con Home Admin;
- grafici e quick card più puliti;
- mantenuti soltanto dati e azioni utili.

### Ore e Spese
- filtri uniformati;
- form e tabelle allineati al sistema globale;
- azioni e badge coerenti;
- totale periodo mantenuto come informazione contestuale.

### Fasi
- filtro Commessa normalizzato;
- pannelli e tabella uniformati;
- eliminate descrizioni generiche;
- pagina di eliminazione trasformata in confirmation pattern compatto.

### Clienti / Commesse / Assegnazioni / Tariffe
- filtri e tabelle allineati;
- ridotte etichette secondarie non utili;
- azioni rese coerenti;
- rimosso testo tecnico sulla fase automatica nelle tariffe.

### Skill Matrix
- tabella dedicata con allineamenti coerenti;
- livelli L1/L2/L3 visualizzati con intensità cromatica progressiva e semantica;
- topbar e titoli corretti per Catalogo Skill, Matrix e valutazione risorsa.

### Pianificazione
- mantenute le correzioni precedenti su colonne, azioni e percentuali;
- rimossa ulteriore business-copy non necessaria;
- pagina di eliminazione uniformata al confirmation pattern.

### Attività
- KPI, filtri, lista e bacheca portati allo stesso ritmo visivo;
- Bacheca a tre colonne coerenti;
- eliminata microcopy generica;
- dettaglio e conferma eliminazione allineati.

### Documenti
- upload e lista uniformati;
- rimossa spiegazione ridondante sul comportamento del form;
- eliminazione documento allineata alle altre conferme distruttive.

### Dashboard Admin / Dashboard di progetto
- eliminate descrizioni ripetitive sotto grafici e sezioni;
- mantenuti dati, contesto e cliente;
- denominazione `Dashboard di progetto` al posto del wording legacy `Dashboard PM` nella topbar.

### Chiusura mese
- KPI e pannelli operativi riallineati;
- rimosse spiegazioni tecniche ridondanti;
- conservati soltanto warning e conseguenze operative necessarie per chiusura/riapertura.

### Promemoria
- eliminata microcopy descrittiva ripetitiva;
- mantenuti numero destinatari, configurazione e registro;
- form e filtri allineati.

### Importazioni
- template card, dettaglio, anteprima e conferma uniformati;
- eliminate spiegazioni interne di business/audit non necessarie nell'interfaccia;
- mantenuti errori, conteggi e informazioni di validazione.

### Audit
- lista eventi e filtri uniformati;
- eliminata descrizione generica della sezione;
- motivazioni reali degli eventi mantenute.

### Report
- KPI semplificati;
- filtri e pannelli di aggregazione uniformati;
- tabelle coerenti con il resto dell'app.

### Notifiche
- lista notifiche integrata nel sistema di pannelli;
- preferenze notifica trasformate in righe compatte e uniformi;
- descrizioni mantenute solo dove servono a distinguere il significato dei toggle.

## Form
Tutti i form applicativi condividono ora:
- larghezza massima coerente;
- field spacing uniforme;
- label, help, errori e focus coerenti;
- stessa altezza dei controlli;
- stessi raggi;
- stesso footer azioni;
- confirmation pattern dedicato per operazioni distruttive.

## Navigazione / Topbar
Aggiunte o riallineate etichette per:
- Persone e ruoli;
- Catalogo skill;
- Nuova/Modifica skill;
- Skill Matrix;
- Valutazione skill;
- Teamwork;
- Preferenze notifiche;
- Dashboard di progetto.

## Pulizia UI
- nessun file UI `*_BACKUP` rimasto;
- rimossi ulteriori testi di business logic non necessari;
- rimosso inline style dalla conferma eliminazione fase;
- mantenuti soltanto testi utili a warning, conferme, dati dinamici o conseguenze operative.

## Backend
- nessuna nuova migrazione;
- nessuna modifica alle regole di dominio;
- nessuna modifica ai servizi di business;
- modifiche limitate a template, CSS e label di navigazione.

## Controlli statici eseguiti
- AST Python: 260 file, OK;
- CSS: 22 file, parentesi graffe bilanciate;
- conflict marker: assenti;
- file UI BACKUP: assenti;
- vecchio refuso `<th scope="col"ead>`: assente;
- content simplification check: OK;
- metodi `test_*` rilevati nel progetto: 316.

La suite Django completa deve essere rilanciata nello staging Docker, dove sono disponibili tutte le dipendenze runtime.
