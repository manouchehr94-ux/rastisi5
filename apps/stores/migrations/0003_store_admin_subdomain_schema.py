from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("stores", "0002_create_akhlaghi_store"),
    ]

    operations = [
        migrations.AddField(
            model_name="store",
            name="admin_subdomain",
            field=models.CharField(
                max_length=63,
                null=True,
                unique=True,
                verbose_name="زیردامنه‌ی مدیریت",
                help_text=(
                    "بخش پایدار زیردامنه‌ی پنل مدیریت، مستقل از دامنه‌ی عمومی "
                    "فروشگاه (مثل «digilool» در https://digilool.rastisi.ir/"
                    "admin-portal/). برخلاف slug، همیشه ASCII و DNS-safe است — "
                    "چون این مقدار مستقیماً بخشی از یک Host واقعی می‌شود، نه "
                    "فقط یک URL path."
                ),
            ),
        ),
    ]
