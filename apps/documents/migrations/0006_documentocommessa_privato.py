from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("documents", "0005_drop_legacy_privato_column"),
    ]

    operations = [
        migrations.AddField(
            model_name="documentocommessa",
            name="privato",
            field=models.BooleanField(
                default=False,
                help_text=(
                    "Se selezionato, il documento è visibile solo agli "
                    "Admin LEF (es. contratti riservati): non compare né "
                    "nell'elenco né nel download per PM e consulenti, "
                    "anche se hanno un'assegnazione attiva sulla commessa."
                ),
            ),
        ),
    ]
