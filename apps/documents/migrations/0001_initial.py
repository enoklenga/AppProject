import uuid

import apps.documents.models
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('projects', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='DocumentoCommessa',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('file', models.FileField(storage=apps.documents.models.documenti_storage, upload_to=apps.documents.models.percorso_documento)),
                ('nome_originale', models.CharField(max_length=255)),
                ('categoria', models.CharField(choices=[('CONTRATTO', 'Contratto'), ('OBIETTIVO', 'Obiettivo'), ('ALTRO', 'Altro')], default='ALTRO', max_length=20)),
                ('descrizione', models.TextField(blank=True)),
                ('dimensione_byte', models.PositiveIntegerField()),
                ('caricato_da', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='documenti_caricati', to=settings.AUTH_USER_MODEL)),
                ('commessa', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='documenti', to='projects.commessa')),
            ],
            options={
                'db_table': 'documento_commessa',
                'ordering': ('-created_at',),
            },
        ),
        migrations.AddIndex(
            model_name='documentocommessa',
            index=models.Index(fields=['commessa', 'categoria'], name='idx_documento_commessa_cat'),
        ),
    ]
