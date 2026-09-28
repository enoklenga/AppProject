from django.db import migrations, models
from django.db.models import Q

class Migration(migrations.Migration):
    dependencies = [("phases", "0002_operational_phase_dates")]
    operations = [
        migrations.AddConstraint(
            model_name="fasecommessa",
            constraint=models.CheckConstraint(
                condition=(Q(data_fine_prevista__isnull=True) | Q(data_fine_prevista__gte=models.F("data_inizio"))),
                name="fase_fine_non_precede_inizio",
            ),
        ),
    ]
