"""Non-destructive ownership assignment for legacy global content rows.

Migration 0014 added a nullable ``store`` FK to ``ContentPage``, ``HeroSlide``,
``PromotionalBanner``, ``SocialLink`` and ``Menu`` (``MenuItem`` is scoped
transitively through its ``Menu``, so it needs no field of its own). Those
rows predate per-store storefront content and carry no reliable ownership
signal (no ``created_by``, no per-row store hint anywhere in the schema).

Safe strategy (documented in
``docs/reports/STOREFRONT_VISUAL_BUILDER_AUDIT.md`` open decision #6, and
mandated by the Phase 2 task spec):

* If the platform has **exactly one** Store, every legacy row unambiguously
  belongs to it (this mirrors the existing single-store development
  fallback in ``apps.stores.resolution.resolve_compatibility_store``) — all
  null-store rows across the five models are assigned to that Store.
* If the platform has **zero or more than one** Store, there is no safe way
  to guess ownership. Rows are left with ``store=NULL`` — never deleted,
  never guessed, never copied to every store. They simply stay invisible to
  every store's storefront (the same "no fallback ever renders unowned
  content" rule already documented in ``apps/content/README.md``) until a
  platform operator manually assigns them a Store through the Django admin.

This migration is idempotent — re-running it only ever touches rows that
still have ``store_id IS NULL``.
"""
from django.db import migrations


LEGACY_MODELS = ["ContentPage", "HeroSlide", "PromotionalBanner", "SocialLink", "Menu"]


def assign_legacy_ownership(apps, schema_editor):
    Store = apps.get_model("stores", "Store")
    store_count = Store.objects.count()
    single_store = Store.objects.first() if store_count == 1 else None

    for model_name in LEGACY_MODELS:
        Model = apps.get_model("content", model_name)
        orphaned = Model.objects.filter(store__isnull=True)
        orphaned_count = orphaned.count()
        if orphaned_count == 0:
            continue
        if single_store is not None:
            orphaned.update(store_id=single_store.pk)
            print(
                f"  [content 0015] {model_name}: assigned {orphaned_count} legacy "
                f"row(s) to the single existing store ({single_store.pk})."
            )
        else:
            print(
                f"  [content 0015] {model_name}: left {orphaned_count} legacy "
                f"row(s) unassigned (store_id=NULL) — {store_count} stores exist, "
                f"ownership is ambiguous. Assign manually via Django admin."
            )


def noop_reverse(apps, schema_editor):
    """Deliberately a no-op: reversing must not un-assign ownership decisions
    a human may have made after this migration ran once."""


class Migration(migrations.Migration):

    dependencies = [
        ("content", "0014_storefront_builder_store_scoping"),
    ]

    operations = [
        migrations.RunPython(assign_legacy_ownership, noop_reverse),
    ]
