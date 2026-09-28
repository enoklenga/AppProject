from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('operations', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='periodomensile',
            name='forzatura_approvazioni_mancanti',
            field=models.BooleanField(default=False),
        ),
    ]
