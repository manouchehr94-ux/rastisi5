# Generated for RastiSi pre-launch eNamad technical verification readiness.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("portal", "0006_platform_owner_admin_gap_fill"),
    ]

    operations = [
        migrations.AddField(
            model_name="platformconfiguration",
            name="enamad_verification_meta_tag",
            field=models.TextField(
                blank=True,
                default="",
                help_text=(
                    "متاتگی که سامانه اینماد برای احراز دسترسی فنی دامنه rastisi.ir "
                    "می‌دهد. فقط یک <meta name=... content=...> امن پذیرفته می‌شود."
                ),
                verbose_name="متاتگ احراز فنی اینماد",
            ),
        ),
    ]
