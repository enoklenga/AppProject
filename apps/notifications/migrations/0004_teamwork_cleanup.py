import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("notifications", "0003_teamwork_notifications"),
        ("documents", "0001_initial"),
    ]

    operations = [
        migrations.AlterField(
            model_name="notification",
            name="task",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="notifiche",
                to="tasks.task",
            ),
        ),
        migrations.AlterField(
            model_name="notification",
            name="pianificazione",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="notifiche",
                to="planning.giornopianificato",
            ),
        ),
        migrations.AlterField(
            model_name="notification",
            name="fase",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="notifiche",
                to="phases.fasecommessa",
            ),
        ),
        migrations.AddField(
            model_name="notification",
            name="documento",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="notifiche",
                to="documents.documentocommessa",
            ),
        ),
        migrations.AlterField(
            model_name="notification",
            name="tipo",
            field=models.CharField(
                choices=[
                    ("TASK_ASSIGNED", "Nuova attività assegnata"),
                    ("TASK_COMMENTED", "Nuovo commento"),
                    ("TASK_DUE_SOON", "Attività in scadenza"),
                    ("TASK_OVERDUE", "Attività scaduta"),
                    ("TASK_CREATED", "Nuova attività creata"),
                    ("TASK_UPDATED", "Attività modificata"),
                    ("TASK_REASSIGNED", "Attività riassegnata"),
                    ("TASK_STATUS_CHANGED", "Cambio stato attività"),
                    ("TASK_DELETED", "Attività eliminata"),
                    ("PIANIFICAZIONE_CREATA", "Nuova pianificazione"),
                    ("PIANIFICAZIONE_AGGIORNATA", "Pianificazione modificata"),
                    ("FASE_CREATA", "Nuova fase"),
                    ("FASE_AGGIORNATA", "Fase aggiornata"),
                    ("DOCUMENTO_CARICATO", "Nuovo documento"),
                    ("DOCUMENTO_ELIMINATO", "Documento eliminato"),
                ],
                db_index=True,
                max_length=30,
            ),
        ),
        migrations.AddField(
            model_name="notificationpreference",
            name="task_modificato",
            field=models.BooleanField(
                default=True,
                verbose_name="Attività modificate",
            ),
        ),
        migrations.AddField(
            model_name="notificationpreference",
            name="documento_eliminato",
            field=models.BooleanField(
                default=True,
                verbose_name="Documento eliminato",
            ),
        ),
    ]
