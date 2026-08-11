# Phase 1A — steps C (finalize) and G of the owner's required migration
# sequence:
#   - StorefrontSection.page becomes NOT NULL (every existing row was
#     backfilled by 0008; every new row created from this point forward is
#     required to specify a page).
#   - The stable_id uniqueness constraint moves from (version, stable_id)
#     to (page, stable_id) — same logical meaning, now scoped one level
#     deeper because a version can have multiple pages.
#   - stable_id's help_text is extended to explain the new page-scoped
#     uniqueness semantics — a genuine, deliberate model edit for Phase 1A
#     (not a metadata-drift accident like the Phase 0.5 repair), so it
#     gets its own explicit AlterField here rather than silently
#     rewriting the already-applied migration 0004.
#
# This migration does NOT yet remove StorefrontSection.version — see 0010
# for that step, kept deliberately separate per the owner's instruction not
# to combine unrelated schema changes in one migration.

import uuid

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("storefront_builder", "0008_backfill_section_page"),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="storefrontsection",
            name="storefront_section_unique_stable_id_per_version",
        ),
        migrations.AlterField(
            model_name="storefrontsection",
            name="page",
            field=models.ForeignKey(
                on_delete=models.deletion.CASCADE,
                related_name="sections", to="storefront_builder.storefrontpage",
                verbose_name="صفحه",
            ),
        ),
        migrations.AlterField(
            model_name="storefrontsection",
            name="stable_id",
            field=models.UUIDField(
                default=uuid.uuid4, editable=False, db_index=True,
                verbose_name="شناسه منطقی پایدار",
                help_text=(
                    "هویتِ منطقیِ این بخش که مستقل از PK پایگاه‌داده است — طیِ کلونِ "
                    "نسخه (Published → Draft جدید، Restore) دقیقاً همان مقدار حفظ "
                    "می‌شود (چون همان بخشِ منطقی است، فقط در نسخه‌ی دیگری). طیِ "
                    "تکرار (Duplicate) عمداً یک UUID تازه می‌گیرد (چون یک بخشِ "
                    "منطقیِ *جدید* است). این فیلد اجازه می‌دهد ردیف‌های رسانه‌ی "
                    "مقیّد به section (HeroSlide/PromotionalBanner/StoryRailItem) "
                    "طیِ کلون بتوانند section مقابلِ خودشان را در نسخه‌ی جدید پیدا "
                    "کنند — بدون اینکه هرگز به PKِ بخشِ منتشرشده دست بزنند "
                    "(Phase 0.5 — نگاه کنید به layout_service._clone_version_content). "
                    "Phase 1A: محدوده‌یِ یکتاییِ این فیلد از (نسخه، stable_id) به "
                    "(صفحه، stable_id) تغییر کرده — همان معنایِ منطقی، فقط یک سطح "
                    "دقیق‌تر (چون اکنون یک نسخه می‌تواند چند صفحه داشته باشد)."
                ),
            ),
        ),
        migrations.AddConstraint(
            model_name="storefrontsection",
            constraint=models.UniqueConstraint(
                fields=("page", "stable_id"),
                name="storefront_section_unique_stable_id_per_page",
            ),
        ),
    ]
