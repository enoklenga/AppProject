from django.db import migrations


def backfill_fase_mancante(apps, schema_editor):
    """
    Ricollega ad una fase ogni assegnazione che ne è ancora priva.

    Serve per i database che avevano già applicato una versione
    precedente di questa migrazione (stesso nome, contenuto diverso):
    Django la considerava "già fatta" e non ha mai eseguito la logica
    di questa versione, lasciando alcune assegnazioni (tipicamente
    quelle da Project Manager) senza fase.
    """

    Assegnazione = apps.get_model("projects", "Assegnazione")
    FaseCommessa = apps.get_model("phases", "FaseCommessa")

    for assegnazione in Assegnazione.objects.filter(fase__isnull=True).iterator():
        fase_id = (
            FaseCommessa.objects.filter(
                commessa_id=assegnazione.commessa_id,
                sistema=True,
            ).values_list("pk", flat=True).first()
        )

        if fase_id is None:
            fase_id = (
                FaseCommessa.objects.filter(
                    commessa_id=assegnazione.commessa_id,
                )
                .order_by("ordine", "created_at")
                .values_list("pk", flat=True)
                .first()
            )

        if fase_id is None:
            raise RuntimeError(
                f"Impossibile determinare la fase per l'assegnazione "
                f"{assegnazione.pk}: la commessa {assegnazione.commessa_id} "
                f"non ha nessuna fase. Crearne almeno una su quella "
                f"commessa prima di riprovare la migrazione."
            )

        Assegnazione.objects.filter(pk=assegnazione.pk).update(fase_id=fase_id)


class Migration(migrations.Migration):

    # PostgreSQL non permette di creare un indice sulla stessa tabella
    # appena dopo un UPDATE che lascia eventi trigger differiti in
    # sospeso (il caso qui: il backfill del campo fase, che tocca una
    # chiave esterna, seguito subito dalla creazione dell'indice unico).
    # Disattivando l'unica transazione che avvolge tutta la migrazione,
    # ogni operazione ha la propria: il backfill si conclude ed è
    # visibile prima che parta l'operazione SQL successiva.
    atomic = False

    dependencies = [
        ("projects", "0002_assegnazione_fase"),
        ("phases", "0002_operational_phase_dates"),
    ]

    operations = [
        migrations.RunPython(
            backfill_fase_mancante,
            migrations.RunPython.noop,
        ),
        # Le due righe seguenti sistemano la parte di schema (vincoli e
        # NOT NULL) usando SQL diretto con IF EXISTS, così l'operazione
        # è sicura sia se il database ha ancora i nomi/vincoli della
        # versione precedente, sia se è già nello stato corretto (un
        #'installazione nuova, dove questa migrazione non deve
        # rompere nulla).
        migrations.RunSQL(
            sql="""
                DROP INDEX IF EXISTS uq_pm_attivo_per_commessa;
                DROP INDEX IF EXISTS uq_consulente_attivo_per_fase;
                DROP INDEX IF EXISTS uq_assegnazione_attiva_consulente_fase;
                CREATE UNIQUE INDEX uq_assegnazione_attiva_consulente_fase
                    ON assegnazione (consulente_id, fase_id)
                    WHERE (stato = 'ATTIVA');
                ALTER TABLE assegnazione ALTER COLUMN fase_id SET NOT NULL;
            """,
            reverse_sql=migrations.RunSQL.noop,
        ),
    ]
