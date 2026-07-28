"""Safely reset only the catalogue data owned by one Store."""
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.catalog.models import Brand, Category, Product, SpecificationTemplate, Vendor
from apps.stores.models import Store


class Command(BaseCommand):
    help = "حذف کامل کاتالوگ یک فروشگاه بدون حذف خود فروشگاه، کاربران یا تنظیمات"

    def add_arguments(self, parser):
        parser.add_argument("--store-slug", default="akhlaghi")
        parser.add_argument("--confirm", action="store_true")

    def handle(self, *args, **options):
        try:
            store = Store.objects.get(slug=options["store_slug"])
        except Store.DoesNotExist as exc:
            raise CommandError("فروشگاه پیدا نشد.") from exc

        products = Product.objects.filter(store=store)
        categories = Category.objects.filter(store=store)
        brands = Brand.objects.filter(store=store)
        templates = SpecificationTemplate.objects.filter(category__store=store)
        self.stdout.write(
            f"فروشگاه: {store.slug} | محصولات: {products.count()} | دسته‌ها: {categories.count()} | "
            f"برندها: {brands.count()} | قالب‌های مشخصات: {templates.count()}"
        )
        if not options["confirm"]:
            raise CommandError("هیچ داده‌ای حذف نشد. برای تأیید صریح --confirm را اضافه کنید.")

        with transaction.atomic():
            # Product cascades remove images, specifications, variants and cart links.
            product_result = products.delete()
            template_result = templates.delete()
            category_result = categories.delete()
            brand_result = brands.delete()

        self.stdout.write(self.style.SUCCESS(
            f"ریست کاتالوگ انجام شد. محصولات/وابستگی‌ها: {product_result} | "
            f"قالب‌ها: {template_result} | دسته‌ها: {category_result} | برندها: {brand_result}"
        ))
        self.stdout.write("خود فروشگاه، فروشندگان، کاربران، تنظیمات و داده‌های غیرکاتالوگی حذف نشدند.")
