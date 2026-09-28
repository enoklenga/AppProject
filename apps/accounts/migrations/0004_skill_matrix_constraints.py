from django.db import migrations, models
from django.db.models import Count
from django.db.models.functions import Lower


def merge_case_insensitive_skills(apps, schema_editor):
    Skill = apps.get_model("accounts", "Skill")
    UserSkill = apps.get_model("accounts", "UserSkill")

    gruppi = (
        Skill.objects.annotate(nome_ci=Lower("nome"))
        .values("nome_ci")
        .annotate(numero=Count("id"))
        .filter(numero__gt=1)
    )

    for gruppo in gruppi.iterator():
        skills = list(
            Skill.objects.annotate(nome_ci=Lower("nome"))
            .filter(nome_ci=gruppo["nome_ci"])
            .order_by("created_at", "id")
        )
        if not skills:
            continue
        canonica = skills[0]
        canonica.nome = canonica.nome.strip()
        canonica.save(update_fields=["nome"])

        for duplicata in skills[1:]:
            for voce in UserSkill.objects.filter(skill_id=duplicata.id).iterator():
                esistente = UserSkill.objects.filter(
                    utente_id=voce.utente_id,
                    skill_id=canonica.id,
                ).first()
                if esistente:
                    if voce.livello > esistente.livello:
                        esistente.livello = voce.livello
                        esistente.save(update_fields=["livello"])
                    voce.delete()
                else:
                    voce.skill_id = canonica.id
                    voce.save(update_fields=["skill"])
            duplicata.delete()


def noop_reverse(apps, schema_editor):
    # Il merge dei duplicati non è reversibile senza inventare dati.
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0003_roles_skill_matrix"),
    ]

    operations = [
        migrations.RunPython(merge_case_insensitive_skills, noop_reverse),
        migrations.AddConstraint(
            model_name="skill",
            constraint=models.UniqueConstraint(
                Lower("nome"),
                name="uq_skill_nome_ci",
            ),
        ),
        migrations.AddConstraint(
            model_name="userskill",
            constraint=models.CheckConstraint(
                condition=models.Q(livello__in=(1, 2, 3)),
                name="utente_skill_livello_1_3",
            ),
        ),
    ]
