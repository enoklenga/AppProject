from django.db import migrations


class Migration(migrations.Migration):
    """
    Rimuove la colonna "privato" dalla tabella documento_commessa.

    Questa colonna è un residuo di una versione precedente del progetto
    (un flag di visibilità documento mai arrivato in produzione con
    questo modello): non compare in nessuna migrazione né nel modello
    Django attuali, ma è rimasta NOT NULL senza default su alcuni
    database già esistenti. Il caricamento di un nuovo documento fallisce
    quindi con:

        IntegrityError: null value in column "privato" of relation
        "documento_commessa" violates not-null constraint

    perché l'INSERT generato da Django non la valorizza (non la conosce).
    Usiamo "IF EXISTS" così la migrazione è sicura sia sui database che
    hanno ancora la colonna, sia sulle installazioni nuove dove non è
    mai esistita.
    """

    dependencies = [
        ("documents", "0004_alter_documentocommessa_file"),
    ]

    operations = [
        migrations.RunSQL(
            sql='ALTER TABLE documento_commessa DROP COLUMN IF EXISTS privato;',
            reverse_sql=migrations.RunSQL.noop,
        ),
    ]
