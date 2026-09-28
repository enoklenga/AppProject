from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("planning", "0001_initial"),
        ("timesheets", "0002_rigaore_approvata_da_rigaore_data_approvazione_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="giornopianificato",
            name="tipo_attivita",
            field=models.CharField(
                choices=[("FORMAZIONE", "Formazione"), ("CONSULENZA", "Consulenza")],
                default="CONSULENZA",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="giornopianificato",
            name="stato_sessione",
            field=models.CharField(
                choices=[("PIANIFICATA", "Pianificata"), ("CONFERMATA", "Conclusa e confermata")],
                db_index=True,
                default="PIANIFICATA",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="giornopianificato",
            name="confermata_il",
            field=models.DateTimeField(blank=True, editable=False, null=True),
        ),
        migrations.AddField(
            model_name="giornopianificato",
            name="confermata_da",
            field=models.ForeignKey(
                blank=True,
                editable=False,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="sessioni_agenda_confermate",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="giornopianificato",
            name="riga_ore_generata",
            field=models.OneToOneField(
                blank=True,
                editable=False,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="sessione_agenda",
                to="timesheets.rigaore",
            ),
        ),
    ]
