from django.db import migrations, models
import django.db.models.deletion
from django.db.models import Q


def forwards(apps, schema_editor):
    Commessa = apps.get_model("projects", "Commessa")
    FaseCommessa = apps.get_model("phases", "FaseCommessa")
    Assegnazione = apps.get_model("projects", "Assegnazione")

    for commessa in Commessa.objects.all().iterator():
        fase, _ = FaseCommessa.objects.get_or_create(
            commessa_id=commessa.pk,
            nome="Generale",
            defaults={
                "sistema": True,
                "data_inizio": commessa.data_inizio,
                "data_fine_prevista": commessa.data_fine_prevista,
                "ordine": 0,
                "stato": "DA_INIZIARE",
                "creata_da_id": None,
            },
        )
        FaseCommessa.objects.filter(pk=fase.pk, data_inizio__isnull=True).update(
            data_inizio=commessa.data_inizio
        )
        Assegnazione.objects.filter(commessa_id=commessa.pk, fase__isnull=True).update(
            fase_id=fase.pk
        )


def backwards(apps, schema_editor):
    # Il downgrade conserva le fasi, ma rimuove il vincolo di appartenenza
    # dalle assegnazioni tramite l'alter successivo.
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("projects", "0001_initial"),
        ("phases", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="assegnazione",
            name="fase",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="assegnazioni",
                to="phases.fasecommessa",
            ),
        ),
        migrations.RunPython(forwards, backwards),
        migrations.RemoveConstraint(
            model_name="assegnazione",
            name="uq_assegnazione_attiva_consulente_commessa",
        ),
        migrations.AddConstraint(
            model_name="assegnazione",
            constraint=models.UniqueConstraint(
                condition=Q(stato="ATTIVA"),
                fields=("consulente", "fase"),
                name="uq_assegnazione_attiva_consulente_fase",
            ),
        ),
        migrations.AlterField(
            model_name="assegnazione",
            name="fase",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="assegnazioni",
                to="phases.fasecommessa",
            ),
        ),
    ]
