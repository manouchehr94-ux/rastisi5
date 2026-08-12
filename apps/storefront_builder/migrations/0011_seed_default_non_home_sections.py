# Phase 5 — retroactive backfill: every StorefrontLayoutVersion created
# before this phase has its five non-home StorefrontPage rows (product_detail/
# listing/collection/search/cart) structurally present (migration 0006) but
# completely empty of StorefrontSection rows, because until now the Builder
# UI only ever wrote to the home page. Phase 5 makes these five page types
# genuinely composable and wires the public routes to render whatever
# sections each page has — so any version left with zero sections on these
# pages would render a blank product/listing/collection/search/cart page.
#
# This migration seeds the same fixed default composition
# apps.storefront_builder.services.bootstrap_service.apply_default_non_home_sections
# now applies to every brand-new store's first draft, but only for pages
# that currently have zero sections — never touching a page a merchant (or
# an already-migrated version) already has content on. Idempotent and safe
# to re-run.

from django.db import migrations

_DEFAULT_NON_HOME_SECTION_KEYS = {
    "product_detail": ["product_main", "product_description", "product_video", "related_products"],
    "listing": ["product_listing"],
    "collection": ["collection_header", "collection_products"],
    "search": ["product_listing"],
    "cart": ["cart_items", "cart_summary"],
}


def seed_default_sections(apps, schema_editor):
    StorefrontLayoutVersion = apps.get_model("storefront_builder", "StorefrontLayoutVersion")
    StorefrontSection = apps.get_model("storefront_builder", "StorefrontSection")

    # این مایگریشن عمداً از section_registry.py (کدِ زنده‌ی پایتونی، نه
    # مدلِ تاریخی) برای default_settings() هر کلید استفاده می‌کند — دقیقاً
    # همان الگویی که apply_default_non_home_sections در سرویسِ زنده به کار
    # می‌برد؛ این تابع‌ها به مدل‌های ORM وابسته نیستند، پس import مستقیم
    # (نه apps.get_model) اینجا کاملاً امن است.
    from apps.storefront_builder import section_registry

    for version in StorefrontLayoutVersion.objects.all().iterator():
        for page in version.pages.exclude(page_type="home"):
            if page.sections.exists():
                continue
            keys = _DEFAULT_NON_HOME_SECTION_KEYS.get(page.page_type, [])
            valid_keys = [k for k in keys if section_registry.is_valid_section_key(k)]
            if not valid_keys:
                continue
            StorefrontSection.objects.bulk_create([
                StorefrontSection(
                    page=page, section_key=key, order=order,
                    settings=section_registry.get_definition(key).default_settings(),
                )
                for order, key in enumerate(valid_keys)
            ])


def remove_seeded_sections(apps, schema_editor):
    """Reverse: remove exactly the section_keys this migration could have
    created, from the five non-home page types only — never touches home
    page sections or anything a merchant added through the Builder after
    this migration ran (those aren't distinguishable from the seeded rows
    at the schema level, so a rollback after real usage is inherently lossy
    for this one direction, same caveat as migration 0006/0008's reverses)."""
    StorefrontSection = apps.get_model("storefront_builder", "StorefrontSection")
    all_seeded_keys = {key for keys in _DEFAULT_NON_HOME_SECTION_KEYS.values() for key in keys}
    StorefrontSection.objects.filter(
        page__page_type__in=list(_DEFAULT_NON_HOME_SECTION_KEYS), section_key__in=list(all_seeded_keys),
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("storefront_builder", "0010_remove_storefrontsection_version"),
    ]

    operations = [
        migrations.RunPython(seed_default_sections, remove_seeded_sections),
    ]
