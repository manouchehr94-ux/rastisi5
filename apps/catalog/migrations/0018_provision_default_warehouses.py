from django.db import migrations


def provision_default_warehouses(apps, schema_editor):
    """هر Store موجود یک انبارِ پیش‌فرض می‌گیرد و موجودیِ فعلیِ هر
    Product/ProductVariant به‌عنوانِ موجودیِ آغازینِ همان انبار ثبت می‌شود.

    idempotent: با ``get_or_create`` روی (store, code) برای انبار و
    (warehouse, product[, variant]) برای موجودی — اجرای دوباره‌ی این
    مهاجرت هیچ ردیفِ تکراری نمی‌سازد و مقدارِ موجودیِ موجود را دست‌نخورده
    نگه می‌دارد (موجودیِ فعلی هرگز بازنویسی نمی‌شود، فقط اگر ردیفی نبود
    ساخته می‌شود). نگاه کنید به ADR-37/ADR-38.
    """
    Store = apps.get_model("stores", "Store")
    Warehouse = apps.get_model("catalog", "Warehouse")
    WarehouseInventory = apps.get_model("catalog", "WarehouseInventory")
    Product = apps.get_model("catalog", "Product")
    ProductVariant = apps.get_model("catalog", "ProductVariant")

    for store in Store.objects.all():
        warehouse, _ = Warehouse.objects.get_or_create(
            store=store, code="main",
            defaults={"name": "انبار اصلی", "is_default": True, "is_active": True},
        )
        if not warehouse.is_default:
            warehouse.is_default = True
            warehouse.save(update_fields=["is_default"])

        for product in Product.objects.filter(store=store):
            WarehouseInventory.objects.get_or_create(
                store=store, warehouse=warehouse, product=product, variant=None,
                defaults={"on_hand": product.stock},
            )

        for variant in ProductVariant.objects.filter(store=store):
            WarehouseInventory.objects.get_or_create(
                store=store, warehouse=warehouse, product=variant.product, variant=variant,
                defaults={"on_hand": variant.stock},
            )


def unprovision_default_warehouses(apps, schema_editor):
    """Reverse: هیچ داده‌ای حذف نمی‌کند — انبارها و موجودیِ ثبت‌شده رکوردهای
    واقعیِ عملیاتی‌اند، نه صرفاً حالتِ این مهاجرت. مطابق قراردادِ سایرِ
    مهاجرت‌های backfill این کدبیس (مثلاً 0002_create_akhlaghi_store)."""


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0017_alter_stockmovement_reason_warehouse_and_more"),
    ]

    operations = [
        migrations.RunPython(provision_default_warehouses, unprovision_default_warehouses),
    ]
