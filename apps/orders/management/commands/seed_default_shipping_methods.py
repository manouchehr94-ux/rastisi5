"""بارگذاریِ idempotent روش‌های ارسالِ رایج برای همه‌ی Storeها (یا یک Store
مشخص) — نگاه کنید به ``apps.orders.services.shipping_service.
ensure_default_shipping_methods`` برای منطقِ واقعیِ ساخت (کلید طبیعیِ
``(store, slug)``؛ اجرای دوباره هرگز رکورد تکراری نمی‌سازد و هیچ روشِ
ویرایش‌شده‌ی مرچنت را دست‌نمی‌زند).

این دستور معمولاً لازم نیست دستی اجرا شود — صفحه‌ی سادهٔ راه‌اندازیِ ارسال
(``dashboard:shipping-setup``) همین تابع را در لحظه‌ی بازدید فراخوانی
می‌کند، پس هر Store به‌محض بازکردنِ آن صفحه این روش‌ها را می‌بیند. این
دستور فقط برایِ backfill دستیِ Storeهای موجود (مثلاً پیش از استقرار) یا
اسکریپت‌های عملیاتی است."""

from django.core.management.base import BaseCommand

from apps.orders.services.shipping_service import ensure_default_shipping_methods
from apps.stores.models import Store


class Command(BaseCommand):
    help = "بارگذاریِ idempotent روش‌های ارسالِ رایج برای همه‌ی Storeها (یا یک Store با --store-slug)"

    def add_arguments(self, parser):
        parser.add_argument("--store-slug", default="", help="فقط برایِ این Store (پیش‌فرض: همه‌ی Storeها)")

    def handle(self, *args, **options):
        store_slug = options["store_slug"]
        stores = Store.objects.filter(slug=store_slug) if store_slug else Store.objects.all()

        if store_slug and not stores.exists():
            self.stderr.write(self.style.ERROR(f"فروشگاهی با اسلاگِ «{store_slug}» یافت نشد."))
            return

        total = 0
        for store in stores:
            ensure_default_shipping_methods(store)
            total += 1

        self.stdout.write(self.style.SUCCESS(f"روش‌های ارسالِ رایج برایِ {total} فروشگاه بررسی/ساخته شد."))
