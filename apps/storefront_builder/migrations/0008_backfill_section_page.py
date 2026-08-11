# Phase 1A — step D of the owner's required migration sequence: backfill
# every existing StorefrontSection onto the HOME page of its current
# version. This mapping is deterministic — every StorefrontSection that
# exists today was created by the pre-Phase-1A homepage-only Builder, so
# "home" is unambiguously correct for all of them, with no heuristic or
# guesswork involved.
#
# section ordering/settings/is_active/stable_id are NOT touched by this
# migration at all — only the new `page` FK is set. Nothing else about an
# existing section changes.

from django.db import migrations


def backfill_section_pages(apps, schema_editor):
    StorefrontSection = apps.get_model("storefront_builder", "StorefrontSection")
    StorefrontPage = apps.get_model("storefront_builder", "StorefrontPage")

    # Build a {version_id: home_page_id} map once, rather than querying it
    # per-section — every version was guaranteed a "home" page by migration
    # 0006, so this dict is complete for every version that could possibly
    # own a pre-existing section.
    home_page_id_by_version_id = dict(
        StorefrontPage.objects.filter(page_type="home").values_list("version_id", "id")
    )

    for section in StorefrontSection.objects.filter(page__isnull=True).select_related(None).iterator():
        home_page_id = home_page_id_by_version_id.get(section.version_id)
        if home_page_id is None:
            # Should not happen (0006 guarantees a home page for every
            # existing version) — but if some inconsistent historical row
            # somehow has no matching version, skip rather than crash; a
            # missing page assignment is loudly visible later (constraint
            # violation when page is made NOT NULL in 0009), not silently
            # incorrect.
            continue
        StorefrontSection.objects.filter(pk=section.pk).update(page_id=home_page_id)


def unlink_section_pages(apps, schema_editor):
    """Reverse: only clears the `page` FK back to NULL — never deletes
    any StorefrontSection row, and never deletes the StorefrontPage rows
    themselves (that is migration 0006's reverse's responsibility, which
    Django runs after this one during a rollback, per the dependency
    graph)."""
    StorefrontSection = apps.get_model("storefront_builder", "StorefrontSection")
    StorefrontSection.objects.update(page=None)


class Migration(migrations.Migration):

    dependencies = [
        ("storefront_builder", "0007_storefrontsection_page"),
    ]

    operations = [
        migrations.RunPython(backfill_section_pages, unlink_section_pages),
    ]
