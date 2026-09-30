import uuid

from django.db import migrations, models
import django.db.models.deletion
from django.db.models.functions import Lower


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0005_user_foto_profilo"),
    ]

    operations = [
        migrations.CreateModel(
            name="BusinessUnit",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("nome", models.CharField(max_length=120, unique=True)),
                ("codice", models.CharField(max_length=40, unique=True)),
                ("descrizione", models.TextField(blank=True)),
                ("attiva", models.BooleanField(default=True)),
            ],
            options={"db_table": "business_unit", "ordering": ("nome",)},
        ),
        migrations.CreateModel(
            name="UserBusinessUnit",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("responsabile", models.BooleanField(default=False)),
                ("puo_essere_pm", models.BooleanField(default=False)),
                ("attiva", models.BooleanField(default=True)),
                ("data_inizio", models.DateField(blank=True, null=True)),
                ("data_fine", models.DateField(blank=True, null=True)),
                ("business_unit", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="membership", to="accounts.businessunit")),
                ("utente", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="membership_business_unit", to="accounts.user")),
            ],
            options={
                "db_table": "utente_business_unit",
                "ordering": ("business_unit__nome", "utente__last_name", "utente__first_name"),
            },
        ),
        migrations.AddField(
            model_name="user",
            name="business_units",
            field=models.ManyToManyField(blank=True, related_name="utenti", through="accounts.UserBusinessUnit", to="accounts.businessunit"),
        ),
        migrations.AddConstraint(
            model_name="businessunit",
            constraint=models.UniqueConstraint(Lower("nome"), name="uq_business_unit_nome_ci"),
        ),
        migrations.AddConstraint(
            model_name="businessunit",
            constraint=models.UniqueConstraint(Lower("codice"), name="uq_business_unit_codice_ci"),
        ),
        migrations.AddConstraint(
            model_name="userbusinessunit",
            constraint=models.UniqueConstraint(fields=("utente", "business_unit"), name="uq_utente_business_unit"),
        ),
        migrations.AddConstraint(
            model_name="userbusinessunit",
            constraint=models.CheckConstraint(
                condition=(
                    models.Q(data_fine__isnull=True)
                    | models.Q(data_inizio__isnull=True)
                    | models.Q(data_fine__gte=models.F("data_inizio"))
                ),
                name="utente_bu_fine_non_precede_inizio",
            ),
        ),
    ]
