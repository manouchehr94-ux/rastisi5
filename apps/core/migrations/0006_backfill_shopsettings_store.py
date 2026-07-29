from django.db import migrations

AKHLAGHI_SLUG = "akhlaghi"


def _get_akhlaghi_or_fail(Store):
    """Resolve the Akhlaghi Store by its stable slug — never `.first()`,
    never a hard-coded primary key. Fails loudly (raises) if Akhlaghi is
    missing or, somehow, duplicated; never silently creates a second
    Akhlaghi Store.

    ``.only("pk")``: see the matching function in
    ``apps/orders/migrations/0004_backfill_orders_store.py`` for why a bare
    ``.get(slug=...)`` here is unsafe during a backward migration."""
    try:
        return Store.objects.only("pk").get(slug=AKHLAGHI_SLUG)
    except Store.DoesNotExist:
        raise RuntimeError(
            "Cannot backfill ShopSettings.store: no Store with slug "
            f"{AKHLAGHI_SLUG!r} exists. The stores.0002_create_akhlaghi_store "
            "migration must run before this one."
        )
    except Store.MultipleObjectsReturned:
        raise RuntimeError(
            "Cannot backfill ShopSettings.store: more than one Store with "
            f"slug {AKHLAGHI_SLUG!r} exists. Refusing to guess which one is "
            "authoritative."
        )


def backfill_shop_settings_store(apps, schema_editor):
    Store = apps.get_model("stores", "Store")
    ShopSettings = apps.get_model("core", "ShopSettings")

    akhlaghi = _get_akhlaghi_or_fail(Store)

    unowned = ShopSettings.objects.filter(store__isnull=True)
    unowned_count = unowned.count()
    if unowned_count > 1:
        # The pre-tenancy model always forced pk=1 on save(), so more than
        # one row here is impossible under normal operation — this is a
        # sanity check, not an expected branch. Refuse to guess which row
        # is authoritative rather than silently picking one.
        raise RuntimeError(
            f"Cannot backfill ShopSettings.store: found {unowned_count} "
            "unowned rows, expected at most 1."
        )
    if unowned_count == 1:
        unowned.update(store=akhlaghi)
        return

    # No legacy row exists at all (a genuinely fresh database where no view
    # ever called ShopSettings.load() to bootstrap it). Provision Akhlaghi's
    # row now with the same bootstrap defaults ShopSettings.load() used to
    # apply via get_or_create(pk=1, defaults=...), so behavior is unchanged.
    from django.conf import settings as django_settings

    ShopSettings.objects.create(
        store=akhlaghi,
        name=getattr(django_settings, "SHOP_NAME", "فروشگاه اینترنتی"),
        tagline=getattr(django_settings, "SHOP_TAGLINE", ""),
        contact_phone=getattr(django_settings, "SHOP_CONTACT_PHONE", ""),
        contact_email=getattr(django_settings, "SHOP_CONTACT_EMAIL", ""),
        contact_address=getattr(django_settings, "SHOP_CONTACT_ADDRESS", ""),
        tax_percent=getattr(django_settings, "SHOP_TAX_PERCENT", 9),
        free_shipping_threshold=getattr(
            django_settings, "SHOP_FREE_SHIPPING_THRESHOLD", 500_000
        ),
    )


def unlink_shop_settings_store(apps, schema_editor):
    """Reverse: clear the store reference only. Never deletes the
    ShopSettings row itself — this is real merchant configuration data,
    not something a schema rollback should destroy."""
    Store = apps.get_model("stores", "Store")
    ShopSettings = apps.get_model("core", "ShopSettings")
    try:
        akhlaghi = Store.objects.only("pk").get(slug=AKHLAGHI_SLUG)
    except Store.DoesNotExist:
        return
    ShopSettings.objects.filter(store=akhlaghi).update(store=None)


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0005_store_scope_settings_schema"),
    ]

    operations = [
        migrations.RunPython(
            backfill_shop_settings_store, unlink_shop_settings_store
        ),
    ]
