# Generated for Site Delivery 2B — custom-domain routing/TLS readiness.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("stores", "0017_platform_owner_admin_gap_fill"),
    ]

    operations = [
        migrations.AddField(
            model_name="storedomain",
            name="routing_status",
            field=models.CharField(
                choices=[
                    ("unchecked", "بررسی‌نشده"),
                    ("connected", "متصل"),
                    ("not_connected", "متصل نیست"),
                ],
                db_index=True,
                default="unchecked",
                help_text="نتیجه آخرین بررسی اینکه A/CNAME دامنه واقعاً به زیرساخت RastiSi اشاره می‌کند.",
                max_length=20,
                verbose_name="وضعیت اتصال DNS",
            ),
        ),
        migrations.AddField(
            model_name="storedomain",
            name="routing_checked_at",
            field=models.DateTimeField(
                blank=True, null=True,
                verbose_name="زمان آخرین بررسی اتصال DNS",
            ),
        ),
        migrations.AddField(
            model_name="storedomain",
            name="tls_status",
            field=models.CharField(
                choices=[
                    ("unchecked", "بررسی‌نشده"),
                    ("ready", "آماده"),
                    ("not_ready", "آماده نیست"),
                ],
                db_index=True,
                default="unchecked",
                help_text="نتیجه آخرین handshake واقعی HTTPS برای همین hostname.",
                max_length=20,
                verbose_name="وضعیت TLS",
            ),
        ),
        migrations.AddField(
            model_name="storedomain",
            name="tls_checked_at",
            field=models.DateTimeField(
                blank=True, null=True,
                verbose_name="زمان آخرین بررسی TLS",
            ),
        ),
        migrations.AddField(
            model_name="storedomain",
            name="tls_certificate_expires_at",
            field=models.DateTimeField(
                blank=True, null=True,
                verbose_name="زمان انقضای گواهی TLS",
            ),
        ),
    ]
