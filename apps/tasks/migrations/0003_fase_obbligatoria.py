from django.db import migrations, models
import django.db.models.deletion


def forwards(apps, schema_editor):
    Task = apps.get_model("tasks", "Task")
    Fase = apps.get_model("phases", "FaseCommessa")
    Assegnazione = apps.get_model("projects", "Assegnazione")

    for task in Task.objects.filter(fase__isnull=True).iterator():
        fase = (
            Assegnazione.objects.filter(
                commessa_id=task.commessa_id,
                consulente_id=task.assegnato_a_id,
                stato="ATTIVA",
            ).values_list("fase_id", flat=True).first()
        )

        if fase is None:
            fase = Fase.objects.filter(
                commessa_id=task.commessa_id,
                sistema=True,
            ).values_list("pk", flat=True).first()

        if fase is None:
            # Database migrati da una versione precedente possono avere
            # una fase di default con un nome diverso da "Generale" e
            # senza il flag sistema=True (es. "Fase unica"). Se la
            # commessa ha comunque delle fasi, usiamo la prima in
            # ordine invece di bloccare la migrazione — è comunque una
            # scelta più sensata che lasciare il task senza fase, cosa
            # che non è più permessa.
            fase = Fase.objects.filter(
                commessa_id=task.commessa_id,
            ).order_by("ordine", "created_at").values_list(
                "pk", flat=True
            ).first()

        if fase is None:
            raise RuntimeError(
                f"Impossibile determinare la fase del task {task.pk}: "
                f"la commessa {task.commessa_id} non ha nessuna fase "
                f"associata. Crearne almeno una manualmente su quella "
                f"commessa prima di riprovare la migrazione."
            )

        Task.objects.filter(pk=task.pk).update(fase_id=fase)


class Migration(migrations.Migration):
    dependencies = [
        ("tasks", "0002_task_fase"),
        ("projects", "0003_repair_fase_migration_state"),
        ("phases", "0002_operational_phase_dates"),
    ]
    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="task",
            name="fase",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="tasks",
                to="phases.fasecommessa",
            ),
        ),
    ]
