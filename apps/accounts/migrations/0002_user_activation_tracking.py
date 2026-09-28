from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="attivato_il",
            field=models.DateTimeField(blank=True, editable=False, null=True),
        ),
        migrations.AddField(
            model_name="user",
            name="invito_inviato_il",
            field=models.DateTimeField(blank=True, editable=False, null=True),
        ),
    ]
