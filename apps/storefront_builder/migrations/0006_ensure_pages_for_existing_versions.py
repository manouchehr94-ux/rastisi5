# Phase 1A — step B of the owner's required migration sequence: create the
# six StorefrontPage rows for EVERY existing StorefrontLayoutVersion (Draft,
# Published, and Archived alike — historical versions must remain
# internally complete enough for Restore).
#
# This must run BEFORE the StorefrontSection backfill (0007), because that
# migration needs every version's "home" StorefrontPage to already exist so
# it has somewhere to point existing sections at.

from django.db import migrations

_PAGE_TYPES = ["home", "product_detail", "listing", "collection", "search", "cart"]


def create_pages_for_existing_versions(apps, schema_editor):
    StorefrontLayoutVersion = apps.get_model("storefront_builder", "StorefrontLayoutVersion")
    StorefrontPage = apps.get_model("storefront_builder", "StorefrontPage")

    for version in StorefrontLayoutVersion.objects.all().iterator():
        existing = set(version.pages.values_list("page_type", flat=True))
        missing = [pt for pt in _PAGE_TYPES if pt not in existing]
        if missing:
            StorefrontPage.objects.bulk_create(
                [StorefrontPage(version=version, page_type=pt) for pt in missing]
            )


def delete_backfilled_pages(apps, schema_editor):
    """Reverse: remove every StorefrontPage this migration created. Safe
    to run unconditionally at this point in the migration graph because
    migration 0005 (which this depends on) had not yet let any
    StorefrontSection reference a page — 0007 (the section backfill) is
    the migration that starts relying on these pages existing, and its
    own reverse must run before this one during a `migrate` rollback
    (Django enforces this automatically via the dependency graph)."""
    StorefrontPage = apps.get_model("storefront_builder", "StorefrontPage")
    StorefrontPage.objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ("storefront_builder", "0005_storefrontpage"),
    ]

    operations = [
        migrations.RunPython(create_pages_for_existing_versions, delete_backfilled_pages),
    ]
