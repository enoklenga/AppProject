# Revisione funzionale LEFTRACK — 29/09/2026

Intervento ragionato sulla versione corrente validata.

## Correzioni incluse
- Login: unico toggle password LEFTRACK; compatibilità con il reveal nativo Edge/Windows.
- Pianificazione: il form di creazione espone solo assegnazioni realmente pianificabili dall'utente; la vista di portafoglio non concede automaticamente poteri di modifica.
- Agenda commessa: terminologia orientata a ore/sessioni completate e chiusura operativa, distinta dalla chiusura mensile amministrativa.
- Amministrazione: area CONTROLLO ampliata (dashboard, ore, spese, chiusura mese, promemoria, importazioni, audit, report) e GESTIONE con tariffe + clienti/commesse/assegnazioni in lettura.
- Clienti/commesse/assegnazioni: per Amministrazione nessuna azione di modifica; i link che porterebbero al Teamwork non autorizzato non vengono proposti.
- Home Amministrazione: aggiunto il valore economico delle ore del periodo.
- Notifiche: mantenuta la pipeline esistente, già coperta da test dedicati; rimosso un template duplicato e non referenziato sotto `templates/documents/`.
- Regressioni: aggiornati test matrice ruoli e aggiunti test sul perimetro selezionabile in pianificazione.

## Regole preservate
- Admin resta l'unico profilo con configurazione completa e gestione eccezioni.
- Amministrazione non crea/modifica clienti, commesse o assegnazioni.
- PM/Consulente/Responsabile pianificano solo nel proprio perimetro operativo.
- La validazione backend resta attiva oltre al filtro UI.
