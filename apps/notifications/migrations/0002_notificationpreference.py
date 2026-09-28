# Generated manually to fix an incomplete 0001_initial migration:
# il modello NotificationPreference esisteva già in models.py ma non era
# mai stato incluso nella migrazione iniziale, quindi la tabella non è
# mai stata creata nel database.

import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('notifications', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='NotificationPreference',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('task_assigned', models.BooleanField(default=True, verbose_name='Nuove attività assegnate')),
                ('task_commented', models.BooleanField(default=True, verbose_name='Commenti sulle attività')),
                ('task_due_soon', models.BooleanField(default=True, verbose_name='Attività in scadenza')),
                ('task_overdue', models.BooleanField(default=True, verbose_name='Attività scadute')),
                ('user', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='notification_preferences', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'db_table': 'notification_preference',
            },
        ),
    ]
