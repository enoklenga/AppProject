from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("projects", "0004_alter_assegnazione_fase"),
    ]

    operations = [
        migrations.AddField(
            model_name="commessa",
            name="workflow_stato",
            field=models.CharField(
                choices=[
                    ("DA_PRENDERE_IN_CARICO", "Da prendere in carico"),
                    ("HANDOVER", "Handover commerciale"),
                    ("PIANIFICAZIONE", "Pianificazione"),
                    ("IN_ESECUZIONE", "In esecuzione"),
                    ("IN_CHIUSURA", "In chiusura"),
                    ("SOSPESA", "Sospesa"),
                    ("CHIUSA", "Chiusa"),
                ],
                default="DA_PRENDERE_IN_CARICO",
                max_length=30,
            ),
        ),
        migrations.AddField(
            model_name="commessa",
            name="handover_note",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="commessa",
            name="handover_completato",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="commessa",
            name="handover_completato_il",
            field=models.DateTimeField(blank=True, editable=False, null=True),
        ),
        migrations.AddField(
            model_name="commessa",
            name="handover_completato_da",
            field=models.ForeignKey(
                blank=True,
                editable=False,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="handover_commesse_completati",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AlterField(
            model_name="commessa",
            name="stato",
            field=models.CharField(
                choices=[("APERTA", "Aperta"), ("CHIUSA", "Chiusa")],
                default="APERTA",
                help_text="Stato tecnico usato per bloccare/sbloccare l'operatività.",
                max_length=20,
            ),
        ),
    ]
