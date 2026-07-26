from django.db import migrations

AKHLAGHI_SLUG = "akhlaghi"


def _get_akhlaghi_or_fail(Store):
    """Resolve the Akhlaghi Store by its stable slug — never `.first()`,
    never a hard-coded primary key. Fails loudly if Akhlaghi is missing or
    duplicated; never silently creates a second Akhlaghi Store.

    Intentionally duplicated from
    apps/catalog/migrations/0007_backfill_catalog_store.py rather than
    imported — migrations must never import another migration module."""
    try:
        return Store.objects.get(slug=AKHLAGHI_SLUG)
    except Store.DoesNotExist:
        raise RuntimeError(
            "Cannot backfill orders Store ownership: no Store with slug "
            f"{AKHLAGHI_SLUG!r} exists. The stores.0002_create_akhlaghi_store "
            "migration must run before this one."
        )
    except Store.MultipleObjectsReturned:
        raise RuntimeError(
            "Cannot backfill orders Store ownership: more than one Store "
            f"with slug {AKHLAGHI_SLUG!r} exists. Refusing to guess which "
            "one is authoritative."
        )


def backfill_order_store(apps, schema_editor):
    """Order.store is backfilled from Order.vendor.store — NOT from an
    Akhlaghi guess. Unlike catalog's original Vendor/Category/Brand backfill
    (which had no prior Store relationship to draw on at all), every
    existing Order already has a required, non-null Vendor
    (Order.vendor is NOT NULL), and every Vendor already has a required,
    non-null Store (enforced since apps.catalog's
    0008_store_scope_catalog_enforce_not_null) — so the authoritative Store
    for an existing Order is always already unambiguously determined by its
    own Vendor, never a guess. This is deliberately stricter/safer than a
    fallback assignment: it fails loudly instead of silently picking a Store
    if that invariant is ever violated."""
    Order = apps.get_model("orders", "Order")

    for order in Order.objects.filter(store__isnull=True).select_related("vendor"):
        if order.vendor_id is None or order.vendor.store_id is None:
            raise RuntimeError(
                f"Cannot backfill Order {order.code!r}: its Vendor has no Store. "
                "This should be impossible — Order.vendor and Vendor.store are "
                "both NOT NULL by this point in the migration history. Refusing "
                "to guess a Store for this Order."
            )
        order.store_id = order.vendor.store_id
        order.save(update_fields=["store"])


def unlink_order_store(apps, schema_editor):
    """Reverse: clear the store references only. Never deletes real Order
    data — Orders are financial/historical records."""
    Order = apps.get_model("orders", "Order")
    Order.objects.exclude(store__isnull=True).update(store=None)


def backfill_gateway_shipping_store(apps, schema_editor):
    """PaymentGateway/ShippingMethod have no pre-existing relationship to
    Store (unlike Order, above) — exactly the same situation catalog's
    Vendor/Category/Brand were in. Every existing row predates multi-tenancy
    entirely, so Akhlaghi is the only Store that could possibly have created
    any of it — the same deterministic backfill catalog used."""
    Store = apps.get_model("stores", "Store")
    PaymentGateway = apps.get_model("orders", "PaymentGateway")
    ShippingMethod = apps.get_model("orders", "ShippingMethod")

    akhlaghi = _get_akhlaghi_or_fail(Store)

    PaymentGateway.objects.filter(store__isnull=True).update(store=akhlaghi)
    ShippingMethod.objects.filter(store__isnull=True).update(store=akhlaghi)


def unlink_gateway_shipping_store(apps, schema_editor):
    """Reverse: clear the store references only. Never deletes merchant
    payment-gateway/shipping-method configuration."""
    Store = apps.get_model("stores", "Store")
    PaymentGateway = apps.get_model("orders", "PaymentGateway")
    ShippingMethod = apps.get_model("orders", "ShippingMethod")
    try:
        akhlaghi = Store.objects.get(slug=AKHLAGHI_SLUG)
    except Store.DoesNotExist:
        return
    PaymentGateway.objects.filter(store=akhlaghi).update(store=None)
    ShippingMethod.objects.filter(store=akhlaghi).update(store=None)


class Migration(migrations.Migration):

    dependencies = [
        ("orders", "0003_store_scope_orders_schema"),
        ("catalog", "0008_store_scope_catalog_enforce_not_null"),
    ]

    operations = [
        migrations.RunPython(backfill_order_store, unlink_order_store),
        migrations.RunPython(backfill_gateway_shipping_store, unlink_gateway_shipping_store),
    ]
