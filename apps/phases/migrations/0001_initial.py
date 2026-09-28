import uuid

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
            name='FaseCommessa',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('nome', models.CharField(max_length=255)),
                ('descrizione', models.TextField(blank=True)),
                ('ordine', models.PositiveIntegerField(default=0, help_text='Ordine di visualizzazione tra le fasi della stessa commessa.')),
                ('stato', models.CharField(choices=[('DA_INIZIARE', 'Da iniziare'), ('IN_CORSO', 'In corso'), ('COMPLETATA', 'Completata'), ('SOSPESA', 'Sospesa')], default='DA_INIZIARE', max_length=20)),
                ('data_inizio', models.DateField(blank=True, null=True)),
                ('data_fine_prevista', models.DateField(blank=True, null=True)),
                ('commessa', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='fasi', to='projects.commessa')),
                ('creata_da', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='fasi_create', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'db_table': 'fase_commessa',
                'ordering': ('commessa', 'ordine', 'nome'),
            },
        ),
        migrations.AddConstraint(
            model_name='fasecommessa',
            constraint=models.UniqueConstraint(fields=('commessa', 'nome'), name='uq_fase_commessa_nome'),
        ),
        migrations.AddIndex(
            model_name='fasecommessa',
            index=models.Index(fields=['commessa', 'stato'], name='idx_fase_commessa_stato'),
        ),
    ]
