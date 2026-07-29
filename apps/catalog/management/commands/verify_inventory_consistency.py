"""بررسیِ سازگاریِ موجودی — نگاه کنید به ADR-38 در ``SAAS_DOMAIN_DECISIONS.md``.

``Product.stock``/``ProductVariant.stock`` تنها منبعِ حقیقتِ موجودیِ
قابلِ‌فروش هستند؛ ``WarehouseInventory`` فقط یک شکستِ هم‌گام‌شده به‌ازای هر
انبار است. این دستور بررسی می‌کند که مجموعِ ``WarehouseInventory.on_hand``
به‌ازای هر کالا/تنوع (روی همه‌ی انبارهایش) دقیقاً با
``Product.stock``/``ProductVariant.stock`` برابر باشد — فقط‌خواندنی، هیچ
داده‌ای را تغییر نمی‌دهد.

با ``--strict``، اگر هرگونه ناسازگاری پیدا شود با کدِ خروجِ غیرصفر خارج
می‌شود (برای استفاده در CI/عملیات — دقیقاً همان قراردادِ
``validate_industry_templates --strict``)."""

import json

from django.db.models import Sum

from django.core.management.base import BaseCommand

from apps.catalog.models import Product, ProductVariant, WarehouseInventory
from apps.stores.models import Store


class Command(BaseCommand):
    help = "بررسیِ سازگاریِ Product/ProductVariant.stock با مجموعِ WarehouseInventory.on_hand (فقط‌خواندنی)."

    def add_arguments(self, parser):
        parser.add_argument("--store", default=None, help="فقط این اسلاگ فروشگاه را بررسی کن")
        parser.add_argument("--json", action="store_true", help="خروجی JSON قابل‌پردازش ماشینی")
        parser.add_argument("--strict", action="store_true", help="در صورتِ هرگونه ناسازگاری با کدِ خروجِ ۱ خارج شو")

    def handle(self, *args, **options):
        stores = Store.objects.all()
        if options["store"]:
            stores = stores.filter(slug=options["store"])

        mismatches = []

        for store in stores:
            product_totals = dict(
                WarehouseInventory.objects.filter(store=store, variant__isnull=True)
                .values("product_id").annotate(total=Sum("on_hand")).values_list("product_id", "total")
            )
            for product in Product.objects.filter(store=store):
                warehouse_total = product_totals.get(product.pk, 0)
                if warehouse_total != product.stock:
                    mismatches.append({
                        "store": store.slug, "type": "product", "id": product.pk, "name": product.name,
                        "product_stock": product.stock, "warehouse_total": warehouse_total,
                    })

            variant_totals = dict(
                WarehouseInventory.objects.filter(store=store, variant__isnull=False)
                .values("variant_id").annotate(total=Sum("on_hand")).values_list("variant_id", "total")
            )
            for variant in ProductVariant.objects.filter(store=store):
                warehouse_total = variant_totals.get(variant.pk, 0)
                if warehouse_total != variant.stock:
                    mismatches.append({
                        "store": store.slug, "type": "variant", "id": variant.pk, "name": str(variant),
                        "product_stock": variant.stock, "warehouse_total": warehouse_total,
                    })

        if options["json"]:
            self.stdout.write(json.dumps(mismatches, ensure_ascii=False, indent=2))
        elif mismatches:
            self.stdout.write(self.style.WARNING(f"{len(mismatches)} ناسازگاری یافت شد:"))
            for row in mismatches:
                self.stdout.write(
                    f"  [{row['store']}] {row['type']} #{row['id']} «{row['name']}»: "
                    f"stock={row['product_stock']} vs warehouse_total={row['warehouse_total']}"
                )
        else:
            self.stdout.write(self.style.SUCCESS("موجودیِ همه‌ی کالاها/تنوع‌ها با انبارها سازگار است."))

        if options["strict"] and mismatches:
            raise SystemExit(1)
