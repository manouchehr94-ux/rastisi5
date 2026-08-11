# Phase 0.5 — Correctness Lock: backfill data migration (owner decision 5,
# Part 4). For every existing HeroSlide/PromotionalBanner/StoryRailItem row
# that already has a stored image but no asset FK yet, create a
# store-scoped MediaAsset row and point the placement's asset FK at it.
#
# Deliberately does NOT re-upload or copy any image bytes — the new
# MediaAsset row's ImageField is set to the SAME storage path the legacy
# field already points at, so this migration represents "give this
# already-existing physical file an ownership row", not "duplicate the
# file". No legacy ImageField is modified or cleared by this migration.
#
# Rows with store_id IS NULL (legacy, never-assigned-to-a-store rows — see
# the store field's own help_text on HeroSlide/PromotionalBanner) are
# skipped: MediaAsset.store is NOT NULL, and these rows never render on any
# storefront anyway, so there is nothing unsafe about leaving them exactly
# as they are (correctness > forced cleanup of pre-existing legacy data,
# per the Phase 0.5 brief).
#
# Reverse migration only clears the FK fields it set (does not delete the
# MediaAsset rows it created) — safest possible reverse, consistent with
# "prefer leaving an orphan asset over deleting a file that might still be
# referenced" (Phase 0.5 Part 8 principle applied conservatively here too).

from django.db import migrations


def backfill_assets(apps, schema_editor):
    HeroSlide = apps.get_model("content", "HeroSlide")
    PromotionalBanner = apps.get_model("content", "PromotionalBanner")
    StoryRailItem = apps.get_model("content", "StoryRailItem")
    MediaAsset = apps.get_model("content", "MediaAsset")

    for slide in HeroSlide.objects.filter(store_id__isnull=False).iterator():
        updates = {}
        if slide.desktop_image and not slide.desktop_asset_id:
            asset = MediaAsset.objects.create(store_id=slide.store_id, image=slide.desktop_image.name)
            updates["desktop_asset_id"] = asset.pk
        if slide.mobile_image and not slide.mobile_asset_id:
            asset = MediaAsset.objects.create(store_id=slide.store_id, image=slide.mobile_image.name)
            updates["mobile_asset_id"] = asset.pk
        if updates:
            HeroSlide.objects.filter(pk=slide.pk).update(**updates)

    for banner in PromotionalBanner.objects.filter(store_id__isnull=False).iterator():
        updates = {}
        if banner.desktop_image and not banner.desktop_asset_id:
            asset = MediaAsset.objects.create(store_id=banner.store_id, image=banner.desktop_image.name)
            updates["desktop_asset_id"] = asset.pk
        if banner.mobile_image and not banner.mobile_asset_id:
            asset = MediaAsset.objects.create(store_id=banner.store_id, image=banner.mobile_image.name)
            updates["mobile_asset_id"] = asset.pk
        if updates:
            PromotionalBanner.objects.filter(pk=banner.pk).update(**updates)

    for item in StoryRailItem.objects.filter(store_id__isnull=False).iterator():
        if item.image and not item.image_asset_id:
            asset = MediaAsset.objects.create(store_id=item.store_id, image=item.image.name)
            StoryRailItem.objects.filter(pk=item.pk).update(image_asset_id=asset.pk)


def unlink_assets(apps, schema_editor):
    """Reverse: clear the FK fields only. Never deletes the MediaAsset rows
    this migration created — a MediaAsset row is harmless to leave behind
    (it is just a store-scoped pointer to a file that already exists
    regardless of this migration), whereas deleting it could theoretically
    race against a forward-looking write path that started depending on it
    between migrate and rollback. Prefer the conservative direction."""
    HeroSlide = apps.get_model("content", "HeroSlide")
    PromotionalBanner = apps.get_model("content", "PromotionalBanner")
    StoryRailItem = apps.get_model("content", "StoryRailItem")

    HeroSlide.objects.update(desktop_asset=None, mobile_asset=None)
    PromotionalBanner.objects.update(desktop_asset=None, mobile_asset=None)
    StoryRailItem.objects.update(image_asset=None)


class Migration(migrations.Migration):

    dependencies = [
        ("content", "0020_placement_asset_fks"),
    ]

    operations = [
        migrations.RunPython(backfill_assets, unlink_assets),
    ]
