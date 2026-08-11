# Phase 0.5 — Correctness Lock: add nullable asset-FK fields to the
# existing placement models (HeroSlide, PromotionalBanner, StoryRailItem),
# ALONGSIDE their existing legacy ImageFields (desktop_image/mobile_image/
# image), per owner decision 5. Purely additive schema — no legacy field
# removed, no existing row's rendering behavior changes as a result of
# this migration alone (a separate data migration, 0021, backfills these
# new fields for existing rows; rendering code changes are a separate,
# non-migration change tracked in the write-path/render-path source).
#
# on_delete=PROTECT is deliberate: deleting a placement row must never be
# allowed to cascade into deleting a MediaAsset another placement (e.g. a
# Published one) may still reference.
#
# --------------------------------------------------------------------
# Repair note (Phase 0.5 local-validation fix): the owner's local
# `makemigrations --check --dry-run` flagged drift on
# HeroSlide.desktop_asset only. Root cause confirmed by direct
# byte-for-byte comparison against apps/content/models.py: the model's
# help_text wraps `on_delete=PROTECT` in RST double-backticks
# (``on_delete=PROTECT``); this migration's recorded help_text had the
# same sentence WITHOUT the backticks. This is pure migration-state /
# docstring metadata — it does not correspond to any different column
# type, nullability, on_delete behavior, or constraint, so it does not
# require a different physical database schema. Per the task's explicit
# instruction, this migration (already applied on the owner's local
# database as of this repair) is corrected IN PLACE rather than
# reconciled via a new migration, since the only difference is this
# non-schema metadata string. No other field on this migration (
# mobile_asset, desktop_asset/mobile_asset on PromotionalBanner,
# image_asset on StoryRailItem) showed any drift in the owner's report —
# only HeroSlide.desktop_asset's help_text is corrected below.
# --------------------------------------------------------------------

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("content", "0019_mediaasset"),
    ]

    operations = [
        migrations.AddField(
            model_name="heroslide",
            name="desktop_asset",
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="hero_placements", to="content.mediaasset",
                verbose_name="فایلِ رسانه — دسکتاپ",
                help_text=(
                    "Phase 0.5 — ارجاع به فایلِ فیزیکیِ به‌اشتراک‌گذاشته‌شده. خالی یعنی "
                    "این ردیفِ قدیمی‌تر از این فیلد است (هنوز فقط desktop_image مستقیم "
                    "دارد) — رندر همچنان از desktop_image استفاده می‌کند تا زمانی که "
                    "همه‌ی مسیرهای مصرف‌کننده به‌طورِ کامل به این فیلد منتقل شوند. "
                    "``on_delete=PROTECT``: حذفِ این Placement هرگز نباید بی‌درنگ اجازه‌ی "
                    "حذفِ فایلِ فیزیکیِ زیرِ آن را بدهد اگر Placementِ دیگری (مثلاً "
                    "نسخه‌ی Published) هنوز به همان asset اشاره می‌کند."
                ),
            ),
        ),
        migrations.AddField(
            model_name="heroslide",
            name="mobile_asset",
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="hero_mobile_placements", to="content.mediaasset",
                verbose_name="فایلِ رسانه — موبایل",
            ),
        ),
        migrations.AddField(
            model_name="promotionalbanner",
            name="desktop_asset",
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="banner_desktop_placements", to="content.mediaasset",
                verbose_name="فایلِ رسانه — دسکتاپ",
                help_text=(
                    "Phase 0.5 — همان الگویِ HeroSlide.desktop_asset. خالی یعنی "
                    "این ردیف قدیمی‌تر از این فیلد است؛ رندر همچنان از "
                    "desktop_image استفاده می‌کند."
                ),
            ),
        ),
        migrations.AddField(
            model_name="promotionalbanner",
            name="mobile_asset",
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="banner_mobile_placements", to="content.mediaasset",
                verbose_name="فایلِ رسانه — موبایل",
            ),
        ),
        migrations.AddField(
            model_name="storyrailitem",
            name="image_asset",
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="story_placements", to="content.mediaasset",
                verbose_name="فایلِ رسانه",
                help_text=(
                    "Phase 0.5 — همان الگویِ HeroSlide.desktop_asset (اینجا فقط "
                    "یک تصویرِ واحد، نه جفتِ دسکتاپ/موبایل). خالی یعنی این ردیف "
                    "قدیمی‌تر از این فیلد است؛ رندر همچنان از image استفاده "
                    "می‌کند."
                ),
            ),
        ),
    ]
