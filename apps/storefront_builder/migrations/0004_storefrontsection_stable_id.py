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
#
# --------------------------------------------------------------------
# Repair note (Phase 0.5 local-validation fix, applied in-place to this
# same migration file — NOT as a new 0005):
#
# The original version of this migration's AddField carried
# `default=uuid.uuid4` on a *nullable* field. On SQLite, adding a column
# with a callable default via Django's table-rebuild strategy can
# populate that default for every existing row as part of the ALTER
# itself — i.e. `uuid.uuid4()` was called once and reused for every row
# during the AddField step (not per-row, and not by the RunPython step,
# which never even saw a NULL row to backfill because AddField had
# already filled them all with a non-distinct value). The RunPython
# step itself was never wrong — `StorefrontSection.objects.filter(pk=
# section.pk).update(stable_id=uuid.uuid4())` genuinely assigns a fresh,
# distinct UUID per matched row — but with zero rows matching
# `stable_id__isnull=True`, it silently backfilled nothing, and the
# later UniqueConstraint(version, stable_id) then failed for any version
# with more than one pre-existing section, because they all shared the
# one value that leaked in through AddField's default.
#
# The fix: AddField now adds the column as nullable *with no default at
# all* (matching the owner's required sequence exactly) — this forces
# every existing row's `stable_id` to actually be NULL after the
# AddField step, so RunPython's per-row backfill loop is the only thing
# that ever assigns a value to a pre-existing row, guaranteeing
# distinctness before the AlterField/AddConstraint steps run.
# --------------------------------------------------------------------

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
            # Deliberately NO `default=` here — see the repair note above.
            # Every existing row must land on a genuine NULL after this
            # step, so that RunPython below is the only thing that ever
            # assigns it a (distinct, per-row) value.
            field=models.UUIDField(
                editable=False, null=True, db_index=True,
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
                    "(Phase 0.5 — نگاه کنید به layout_service._clone_version_content)."
                ),
            ),
        ),
        migrations.RunPython(backfill_stable_ids, noop_reverse),
        migrations.AlterField(
            model_name="storefrontsection",
            name="stable_id",
            # Final state — now with the real, model-matching default
            # (uuid.uuid4, applied only to genuinely NEW rows created
            # from this point forward — every existing row was already
            # given its own distinct value by RunPython above) and
            # not-null. This field definition is kept byte-identical to
            # apps/storefront_builder/models.py's current declaration —
            # verified directly against the model source, not just
            # visually — so `makemigrations --check` has nothing left to
            # detect.
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
                    "(Phase 0.5 — نگاه کنید به layout_service._clone_version_content)."
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
