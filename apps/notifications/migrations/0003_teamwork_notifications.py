import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('notifications', '0002_notificationpreference'),
        ('planning', '0001_initial'),
        ('phases', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='notification',
            name='tipo',
            field=models.CharField(
                choices=[
                    ('TASK_ASSIGNED', 'Nuova attività assegnata'),
                    ('TASK_COMMENTED', 'Nuovo commento'),
                    ('TASK_DUE_SOON', 'Attività in scadenza'),
                    ('TASK_OVERDUE', 'Attività scaduta'),
                    ('TASK_CREATED', 'Nuova attività creata'),
                    ('TASK_REASSIGNED', 'Attività riassegnata'),
                    ('TASK_STATUS_CHANGED', 'Cambio stato attività'),
                    ('TASK_DELETED', 'Attività eliminata'),
                    ('PIANIFICAZIONE_CREATA', 'Nuova pianificazione'),
                    ('PIANIFICAZIONE_AGGIORNATA', 'Pianificazione modificata'),
                    ('FASE_CREATA', 'Nuova fase'),
                    ('FASE_AGGIORNATA', 'Fase aggiornata'),
                    ('DOCUMENTO_CARICATO', 'Nuovo documento'),
                ],
                db_index=True,
                max_length=30,
            ),
        ),
        migrations.AddField(
            model_name='notification',
            name='pianificazione',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='notifiche', to='planning.giornopianificato'),
        ),
        migrations.AddField(
            model_name='notification',
            name='fase',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='notifiche', to='phases.fasecommessa'),
        ),
        migrations.AddField(
            model_name='notificationpreference',
            name='task_creato',
            field=models.BooleanField(default=True, verbose_name='Nuove attività create sulle mie commesse'),
        ),
        migrations.AddField(
            model_name='notificationpreference',
            name='task_riassegnato',
            field=models.BooleanField(default=True, verbose_name='Attività riassegnate'),
        ),
        migrations.AddField(
            model_name='notificationpreference',
            name='task_cambio_stato',
            field=models.BooleanField(default=True, verbose_name="Cambio stato di un'attività"),
        ),
        migrations.AddField(
            model_name='notificationpreference',
            name='task_eliminato',
            field=models.BooleanField(default=True, verbose_name='Attività eliminate'),
        ),
        migrations.AddField(
            model_name='notificationpreference',
            name='pianificazione_creata',
            field=models.BooleanField(default=True, verbose_name='Nuova pianificazione di un collega'),
        ),
        migrations.AddField(
            model_name='notificationpreference',
            name='pianificazione_aggiornata',
            field=models.BooleanField(default=True, verbose_name='Pianificazione modificata o eliminata'),
        ),
        migrations.AddField(
            model_name='notificationpreference',
            name='fase_creata',
            field=models.BooleanField(default=True, verbose_name='Nuova fase di commessa'),
        ),
        migrations.AddField(
            model_name='notificationpreference',
            name='fase_aggiornata',
            field=models.BooleanField(default=True, verbose_name='Fase modificata o eliminata'),
        ),
        migrations.AddField(
            model_name='notificationpreference',
            name='documento_caricato',
            field=models.BooleanField(default=True, verbose_name='Nuovo documento caricato'),
        ),
    ]
