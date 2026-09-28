from datetime import date

from django.db import migrations


AUDIT_CUTOFF = date(2026, 9, 24)


def align_legacy_workflow(apps, schema_editor):
    Commessa = apps.get_model("projects", "Commessa")

    # Le commesse già esistenti prima dell'audit non devono apparire come nuove
    # da prendere in carico dopo l'introduzione del workflow.
    legacy = Commessa.objects.filter(created_at__date__lte=AUDIT_CUTOFF)
    legacy.filter(stato="CHIUSA").update(workflow_stato="CHIUSA")
    legacy.filter(stato="APERTA").update(workflow_stato="IN_ESECUZIONE")


def reverse_alignment(apps, schema_editor):
    # Non ricostruiamo uno stato storico fittizio in reverse.
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("projects", "0005_commessa_workflow_handover"),
    ]

    operations = [
        migrations.RunPython(align_legacy_workflow, reverse_alignment),
    ]
