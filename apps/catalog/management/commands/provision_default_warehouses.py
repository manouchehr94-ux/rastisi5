"""هر Storeی که هنوز انبارِ پیش‌فرض ندارد را provision می‌کند و موجودیِ
فعلیِ کالاها/تنوع‌هایش را به‌عنوانِ موجودیِ آغازینِ همان انبار ثبت می‌کند.

idempotent — اجرای دوباره هیچ ردیفِ تکراری نمی‌سازد (نگاه کنید به
``apps.catalog.migrations.0018_provision_default_warehouses`` که همین
منطق را برای Storeهای موجود در زمانِ ارتقا اجرا می‌کند؛ این دستور همان
کار را برای Storeهایی که *بعداً* ساخته شده‌اند تکرار می‌کند)."""

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.catalog.models import Product, ProductVariant, WarehouseInventory
from apps.catalog.services.warehouse_service import provision_default_warehouse
from apps.stores.models import Store


class Command(BaseCommand):
    help = "هر Store را با یک انبارِ پیش‌فرض provision می‌کند و موجودیِ فعلی را به‌عنوانِ موجودیِ آغازین ثبت می‌کند."

    @transaction.atomic
    def handle(self, *args, **options):
        stores_provisioned = 0
        balances_created = 0

        for store in Store.objects.all():
            warehouse = provision_default_warehouse(store)
            stores_provisioned += 1

            for product in Product.objects.filter(store=store):
                _, created = WarehouseInventory.objects.get_or_create(
                    store=store, warehouse=warehouse, product=product, variant=None,
                    defaults={"on_hand": product.stock},
                )
                balances_created += int(created)

            for variant in ProductVariant.objects.filter(store=store):
                _, created = WarehouseInventory.objects.get_or_create(
                    store=store, warehouse=warehouse, product=variant.product, variant=variant,
                    defaults={"on_hand": variant.stock},
                )
                balances_created += int(created)

        self.stdout.write(self.style.SUCCESS(
            f"{stores_provisioned} فروشگاه بررسی شد — {balances_created} ردیفِ موجودیِ انبار تازه ساخته شد."
        ))
