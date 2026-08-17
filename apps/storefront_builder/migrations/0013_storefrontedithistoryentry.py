from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("storefront_builder", "0012_universal_block_row_and_lock"),
    ]

    operations = [
        migrations.CreateModel(
            name="StorefrontEditHistoryEntry",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="تاریخ ایجاد")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="تاریخ بروزرسانی")),
                ("sequence", models.PositiveIntegerField(verbose_name="شماره عملیات")),
                ("action_label", models.CharField(max_length=120, verbose_name="عنوان عملیات")),
                ("before_state", models.JSONField(verbose_name="وضعیت قبل")),
                ("after_state", models.JSONField(verbose_name="وضعیت بعد")),
                ("is_undone", models.BooleanField(default=False, verbose_name="برگشت‌خورده")),
                ("actor", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to=settings.AUTH_USER_MODEL, verbose_name="ویرایشگر")),
                ("draft_version", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="edit_history_entries", to="storefront_builder.storefrontlayoutversion", verbose_name="پیش‌نویس")),
            ],
            options={
                "verbose_name": "گام تاریخچه ویرایش سازنده",
                "verbose_name_plural": "گام‌های تاریخچه ویرایش سازنده",
                "ordering": ["sequence"],
                "indexes": [models.Index(fields=["draft_version", "is_undone", "sequence"], name="sfb_hist_draft_cursor_idx")],
                "constraints": [models.UniqueConstraint(fields=("draft_version", "sequence"), name="storefront_edit_history_unique_sequence_per_draft")],
            },
        ),
    ]
