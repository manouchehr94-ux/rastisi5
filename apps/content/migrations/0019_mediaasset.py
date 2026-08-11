# Phase 0.5 — Correctness Lock: introduce the minimal store-scoped
# MediaAsset model (owner decision 5). Additive only — creates a new,
# empty table. No existing data touched, no existing field removed.

import django.db.models.deletion
from django.db import migrations, models

import apps.content.models


class Migration(migrations.Migration):

    dependencies = [
        ("content", "0018_storyrailitem"),
        ("stores", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="MediaAsset",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="تاریخ ایجاد")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="تاریخ بروزرسانی")),
                ("image", models.ImageField(
                    upload_to="media-assets/",
                    validators=[apps.content.models.validate_image_size, apps.content.models.validate_image_content],
                    verbose_name="تصویر",
                )),
                ("store", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="media_assets", to="stores.store", verbose_name="فروشگاه",
                )),
            ],
            options={
                "verbose_name": "فایل رسانه",
                "verbose_name_plural": "فایل‌های رسانه",
                "ordering": ["-created_at", "-id"],
            },
        ),
    ]
