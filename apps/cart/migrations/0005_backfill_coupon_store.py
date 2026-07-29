from django.db import migrations

AKHLAGHI_SLUG = "akhlaghi"


def _get_akhlaghi_or_fail(Store):
    """Resolve the Akhlaghi Store by its stable slug — never `.first()`,
    never a hard-coded primary key. Mirrors
    ``apps/catalog/migrations/0007_backfill_catalog_store.py``."""
    try:
        return Store.objects.only("pk").get(slug=AKHLAGHI_SLUG)
    except Store.DoesNotExist:
        raise RuntimeError(
            "Cannot backfill coupon store ownership: no Store with slug "
            f"{AKHLAGHI_SLUG!r} exists. The stores.0002_create_akhlaghi_store "
            "migration must run before this one."
        )
    except Store.MultipleObjectsReturned:
        raise RuntimeError(
            "Cannot backfill coupon store ownership: more than one Store "
            f"with slug {AKHLAGHI_SLUG!r} exists. Refusing to guess which "
            "one is authoritative."
        )


def backfill_coupon_store(apps, schema_editor):
    Store = apps.get_model("stores", "Store")
    Coupon = apps.get_model("cart", "Coupon")

    # Every Coupon created before this migration was created back when the
    # model had no store field at all — i.e. before multi-tenancy existed
    # for this model — so Akhlaghi (the platform's only pre-existing Store)
    # is the only deterministic, correct owner to assign. Any Coupon a
    # human later decides was meant for a different Store must be
    # reassigned explicitly after this migration — this is a backfill, not
    # a guess about intent.
    Coupon.objects.filter(store__isnull=True).update(store=_get_akhlaghi_or_fail(Store))


def unlink_coupon_store(apps, schema_editor):
    """Reverse: clear the store reference only. Never deletes real coupon data."""
    Store = apps.get_model("stores", "Store")
    Coupon = apps.get_model("cart", "Coupon")
    try:
        akhlaghi = Store.objects.only("pk").get(slug=AKHLAGHI_SLUG)
    except Store.DoesNotExist:
        return
    Coupon.objects.filter(store=akhlaghi).update(store=None)


class Migration(migrations.Migration):

    dependencies = [
        ("cart", "0004_coupon_store_scope_schema"),
    ]

    operations = [
        migrations.RunPython(backfill_coupon_store, unlink_coupon_store),
    ]
