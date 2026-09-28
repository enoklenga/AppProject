# Generated for Nokihub API

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("api", "0001_initial"),
        ("authtoken", "0003_tokenproxy"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="ApiTokenMetadata",
            fields=[
                (
                    "token",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        primary_key=True,
                        related_name="lef_metadata",
                        serialize=False,
                        to="authtoken.token",
                    ),
                ),
                (
                    "expires_at",
                    models.DateTimeField(),
                ),
                (
                    "last_used_at",
                    models.DateTimeField(
                        blank=True,
                        null=True,
                    ),
                ),
                (
                    "last_used_ip_hash",
                    models.CharField(
                        blank=True,
                        max_length=64,
                    ),
                ),
                (
                    "rotated_at",
                    models.DateTimeField(
                        blank=True,
                        null=True,
                    ),
                ),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="token_api_creati",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "db_table": "api_token_metadata",
                "indexes": [
                    models.Index(
                        fields=["expires_at"],
                        name="idx_api_token_expires",
                    ),
                ],
            },
        ),
    ]
