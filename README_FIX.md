# Correzione Step 7

Corregge due errori in `apps/operations/forms.py`:

- `forms.TextChoices` sostituito con normali coppie `(valore, etichetta)` per `ChoiceField`;
- aggiunto il widget `DateInput` utilizzato dai filtri Audit.

Estrarre questo ZIP nella cartella principale del progetto con sovrascrittura.
