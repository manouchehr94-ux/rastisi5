from django.db import migrations

AKHLAGHI_SLUG = "akhlaghi"


def _get_akhlaghi_or_fail(Store):
    """Resolve the Akhlaghi Store by its stable slug — never `.first()`,
    never a hard-coded primary key. Fails loudly if Akhlaghi is missing or
    duplicated; never silently creates a second Akhlaghi Store."""
    try:
        return Store.objects.get(slug=AKHLAGHI_SLUG)
    except Store.DoesNotExist:
        raise RuntimeError(
            "Cannot backfill catalog store ownership: no Store with slug "
            f"{AKHLAGHI_SLUG!r} exists. The stores.0002_create_akhlaghi_store "
            "migration must run before this one."
        )
    except Store.MultipleObjectsReturned:
        raise RuntimeError(
            "Cannot backfill catalog store ownership: more than one Store "
            f"with slug {AKHLAGHI_SLUG!r} exists. Refusing to guess which "
            "one is authoritative."
        )


def backfill_catalog_store(apps, schema_editor):
    Store = apps.get_model("stores", "Store")
    Vendor = apps.get_model("catalog", "Vendor")
    Category = apps.get_model("catalog", "Category")
    Brand = apps.get_model("catalog", "Brand")
    Product = apps.get_model("catalog", "Product")
    ProductVariant = apps.get_model("catalog", "ProductVariant")

    akhlaghi = _get_akhlaghi_or_fail(Store)

    # Every existing row today was created before multi-tenancy existed —
    # Akhlaghi is the only Store that could possibly have created any of
    # this data, so assigning every unowned row to it is the only
    # deterministic, correct backfill. Vendor/Category/Brand are backfilled
    # first (independent of each other); Product next (its own store is
    # independent of its vendor/category/brand FKs); ProductVariant last,
    # copying store from its already-backfilled parent Product.
    Vendor.objects.filter(store__isnull=True).update(store=akhlaghi)
    Category.objects.filter(store__isnull=True).update(store=akhlaghi)
    Brand.objects.filter(store__isnull=True).update(store=akhlaghi)
    Product.objects.filter(store__isnull=True).update(store=akhlaghi)

    for variant in ProductVariant.objects.filter(store__isnull=True).select_related("product"):
        variant.store_id = variant.product.store_id
        variant.save(update_fields=["store"])


def unlink_catalog_store(apps, schema_editor):
    """Reverse: clear the store references only. Never deletes real
    merchant catalog data (products, categories, brands, vendors, variants)."""
    Store = apps.get_model("stores", "Store")
    Vendor = apps.get_model("catalog", "Vendor")
    Category = apps.get_model("catalog", "Category")
    Brand = apps.get_model("catalog", "Brand")
    Product = apps.get_model("catalog", "Product")
    ProductVariant = apps.get_model("catalog", "ProductVariant")
    try:
        akhlaghi = Store.objects.get(slug=AKHLAGHI_SLUG)
    except Store.DoesNotExist:
        return
    ProductVariant.objects.filter(store=akhlaghi).update(store=None)
    Product.objects.filter(store=akhlaghi).update(store=None)
    Brand.objects.filter(store=akhlaghi).update(store=None)
    Category.objects.filter(store=akhlaghi).update(store=None)
    Vendor.objects.filter(store=akhlaghi).update(store=None)


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0006_store_scope_catalog_schema"),
    ]

    operations = [
        migrations.RunPython(backfill_catalog_store, unlink_catalog_store),
    ]
