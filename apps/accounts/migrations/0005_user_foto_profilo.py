from django.core.validators import FileExtensionValidator
from django.db import migrations, models

import apps.accounts.models


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0004_skill_matrix_constraints"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="foto_profilo",
            field=models.ImageField(
                blank=True,
                help_text="JPG, PNG o WebP. Dimensione massima 3 MB.",
                null=True,
                upload_to="avatars/%Y/%m/",
                validators=[
                    FileExtensionValidator(
                        allowed_extensions=("jpg", "jpeg", "png", "webp")
                    ),
                    apps.accounts.models.validate_profile_photo_size,
                ],
                verbose_name="foto profilo",
            ),
        ),
    ]
