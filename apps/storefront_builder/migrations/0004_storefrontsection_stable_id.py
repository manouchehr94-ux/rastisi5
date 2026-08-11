# Phase 0.5 — Correctness Lock: stable logical section identity (owner
# decision 3). Adds StorefrontSection.stable_id (UUID) plus a
# UniqueConstraint(version, stable_id) — deliberately scoped to `version`,
# not globally unique, and NOT scoped to a `page` (StorefrontPage does not
# exist yet in Phase 0.5; Phase 1 may migrate this constraint to page scope
# once it does).
#
# Backfill: every existing StorefrontSection row (across every store, every
# version — Draft, Published, Archived) receives a freshly-generated,
# distinct UUID. This is safe because there is no pre-existing cross-version
# correspondence to preserve for rows created before this field existed —
# their stable_id lineage simply begins at this migration.

import uuid

from django.db import migrations, models


def backfill_stable_ids(apps, schema_editor):
    StorefrontSection = apps.get_model("storefront_builder", "StorefrontSection")
    # .iterator() to avoid loading every section across every store into
    # memory at once; individual .update() per-row because each row needs a
    # DISTINCT uuid (a single bulk .update() would give every row the same
    # value, which would immediately violate the uniqueness constraint
    # added right after this data migration runs).
    for section in StorefrontSection.objects.filter(stable_id__isnull=True).iterator():
        StorefrontSection.objects.filter(pk=section.pk).update(stable_id=uuid.uuid4())


def noop_reverse(apps, schema_editor):
    """Reverse: intentionally a no-op. Clearing stable_id back to NULL would
    require making the field nullable again first (a separate, unnecessary
    schema change) — and there is no forward-compatibility reason to ever
    need this reversed independently of the schema migrations around it."""
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("storefront_builder", "0003_storefrontlayoutversion_appearance_config"),
    ]

    operations = [
        migrations.AddField(
            model_name="storefrontsection",
            name="stable_id",
            field=models.UUIDField(
                default=uuid.uuid4, editable=False, null=True, db_index=True,
                verbose_name="شناسه منطقی پایدار",
                help_text=(
                    "هویتِ منطقیِ این بخش که مستقل از PK پایگاه‌داده است — طیِ "
                    "کلونِ نسخه (Published → Draft جدید، Restore) دقیقاً همان "
                    "مقدار حفظ می‌شود (چون همان بخشِ منطقی است، فقط در نسخه‌ی "
                    "دیگری). طیِ تکرار (Duplicate) عمداً یک UUID تازه می‌گیرد "
                    "(چون یک بخشِ منطقیِ *جدید* است)."
                ),
            ),
        ),
        migrations.RunPython(backfill_stable_ids, noop_reverse),
        migrations.AlterField(
            model_name="storefrontsection",
            name="stable_id",
            field=models.UUIDField(
                default=uuid.uuid4, editable=False, db_index=True,
                verbose_name="شناسه منطقی پایدار",
                help_text=(
                    "هویتِ منطقیِ این بخش که مستقل از PK پایگاه‌داده است — طیِ "
                    "کلونِ نسخه (Published → Draft جدید، Restore) دقیقاً همان "
                    "مقدار حفظ می‌شود (چون همان بخشِ منطقی است، فقط در نسخه‌ی "
                    "دیگری). طیِ تکرار (Duplicate) عمداً یک UUID تازه می‌گیرد "
                    "(چون یک بخشِ منطقیِ *جدید* است)."
                ),
            ),
        ),
        migrations.AddConstraint(
            model_name="storefrontsection",
            constraint=models.UniqueConstraint(
                fields=("version", "stable_id"),
                name="storefront_section_unique_stable_id_per_version",
            ),
        ),
    ]
