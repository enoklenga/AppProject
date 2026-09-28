from django.db import migrations, models
import django.db.models.deletion

class Migration(migrations.Migration):
    dependencies = [
        ("documents", "0001_initial"),
        ("phases", "0002_operational_phase_dates"),
    ]
    operations = [
        migrations.AddField(
            model_name="documentocommessa",
            name="fase",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="documenti",
                to="phases.fasecommessa",
            ),
        ),
    ]
