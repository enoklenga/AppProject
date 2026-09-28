import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('tasks', '0001_initial'),
        ('phases', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='task',
            name='fase',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='tasks',
                to='phases.fasecommessa',
                help_text=(
                    "Facoltativa: un'attività può restare associata "
                    "direttamente alla commessa senza appartenere a una fase."
                ),
            ),
        ),
    ]
