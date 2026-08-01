"""بسته‌های پیش‌فرضِ خریدِ اعتبارِ پیامک — مقادیرِ اولیه، بعداً از طریقِ
Django Admin (فقط superuser، ``apps.sms.admin``) قابلِ ویرایش/افزودن‌اند."""

from django.db import migrations

DEFAULT_PACKAGES = [
    {"name": "بسته‌ی آزمایشی", "credit_amount": 50, "price": 50_000, "display_order": 1},
    {"name": "بسته‌ی استاندارد", "credit_amount": 500, "price": 400_000, "display_order": 2},
    {"name": "بسته‌ی حرفه‌ای", "credit_amount": 2000, "price": 1_400_000, "display_order": 3},
]


def seed_packages(apps, schema_editor):
    SmsPackage = apps.get_model("sms", "SmsPackage")
    for row in DEFAULT_PACKAGES:
        SmsPackage.objects.get_or_create(name=row["name"], defaults=row)


def remove_seeded_packages(apps, schema_editor):
    SmsPackage = apps.get_model("sms", "SmsPackage")
    SmsPackage.objects.filter(name__in=[row["name"] for row in DEFAULT_PACKAGES]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("sms", "0005_sms_balance_and_packages"),
    ]

    operations = [
        migrations.RunPython(seed_packages, remove_seeded_packages),
    ]
