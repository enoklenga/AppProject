from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0002_user_activation_tracking"),
    ]

    operations = [
        migrations.AlterField(
            model_name="user",
            name="ruolo",
            field=models.CharField(
                choices=[
                    ("ADMIN", "Admin LEF"),
                    ("CONSULENTE", "Consulente / Team esecutivo"),
                    ("RESP_CONSULENZA", "Responsabile consulenza / Business Unit"),
                    ("AMMINISTRAZIONE", "Amministrazione"),
                    ("COMMERCIALE", "Commerciale"),
                    ("DIREZIONE_GENERALE", "Direzione Generale"),
                ],
                default="CONSULENTE",
                max_length=30,
            ),
        ),
        migrations.CreateModel(
            name="Skill",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("nome", models.CharField(max_length=120, unique=True)),
                ("categoria", models.CharField(blank=True, max_length=120)),
                ("descrizione", models.TextField(blank=True)),
                ("attiva", models.BooleanField(default=True)),
            ],
            options={
                "db_table": "skill",
                "ordering": ("categoria", "nome"),
            },
        ),
        migrations.CreateModel(
            name="UserSkill",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("livello", models.PositiveSmallIntegerField(choices=[(1, "Livello 1"), (2, "Livello 2"), (3, "Livello 3")])),
                ("skill", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="livelli_utenti", to="accounts.skill")),
                ("utente", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="skill_matrix", to="accounts.user")),
            ],
            options={
                "db_table": "utente_skill",
                "ordering": ("utente__last_name", "utente__first_name", "skill__nome"),
            },
        ),
        migrations.AddConstraint(
            model_name="userskill",
            constraint=models.UniqueConstraint(fields=("utente", "skill"), name="uq_utente_skill"),
        ),
    ]
