from django.db import migrations, models
import django.db.models.deletion


def forwards(apps, schema_editor):
    Commessa = apps.get_model("projects", "Commessa")
    Fase = apps.get_model("phases", "FaseCommessa")
    Fase.objects.filter(nome="Generale", sistema=False).update(sistema=True)
    for fase in Fase.objects.filter(data_inizio__isnull=True).iterator():
        fase.data_inizio = Commessa.objects.get(pk=fase.commessa_id).data_inizio
        fase.save(update_fields=["data_inizio"])


class Migration(migrations.Migration):
    dependencies = [
        ("phases", "0001_initial"),
    ]
    operations = [
        migrations.AddField(
            model_name="fasecommessa",
            name="sistema",
            field=models.BooleanField(default=False, help_text="Fase tecnica creata dal sistema per le commesse senza scomposizione esplicita."),
        ),
        migrations.RunPython(forwards, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="fasecommessa",
            name="data_inizio",
            field=models.DateField(),
        ),
        migrations.AlterField(
            model_name="fasecommessa",
            name="creata_da",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="fasi_create",
                to="accounts.user",
            ),
        ),
    ]
