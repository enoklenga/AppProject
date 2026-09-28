# Generated for Nokihub API

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("operations", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="ApiImportazioneAnteprima",
            fields=[
                (
                    "importazione",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        primary_key=True,
                        related_name="api_anteprima",
                        serialize=False,
                        to="operations.importazione",
                    ),
                ),
                (
                    "tipo_importazione",
                    models.CharField(max_length=20),
                ),
                ("dati_sessione", models.JSONField()),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "db_table": "api_importazione_anteprima",
            },
        ),
    ]
