from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0006_business_units"),
        ("projects", "0006_align_legacy_workflow"),
    ]

    operations = [
        migrations.AddField(
            model_name="commessa",
            name="business_unit",
            field=models.ForeignKey(
                blank=True,
                help_text="Business Unit responsabile della commessa. Il campo resta facoltativo per consentire la classificazione graduale delle commesse esistenti.",
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="commesse",
                to="accounts.businessunit",
                verbose_name="Business Unit owner",
            ),
        ),
    ]
