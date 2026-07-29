"""رزروهای فعالِ منقضی‌شده را به ``EXPIRED`` تبدیل می‌کند — قابلِ اجرا به‌صورت
دوره‌ای (مثلاً هر چند دقیقه از یک cron/celery beat) تا موجودیِ رزروشده‌ی
سبدهای رهاشده آزاد شود.

Batch-safe: هرگز کلِ نتیجه را یک‌جا در حافظه بارگذاری نمی‌کند — نگاه کنید به
``apps.catalog.services.reservation_service.expire_inventory_reservations``."""

from django.core.management.base import BaseCommand

from apps.catalog.services.reservation_service import expire_inventory_reservations


class Command(BaseCommand):
    help = "رزروهای فعالِ منقضی‌شده (expires_at گذشته) را به وضعیتِ EXPIRED تغییر می‌دهد."

    def add_arguments(self, parser):
        parser.add_argument("--batch-size", type=int, default=500)

    def handle(self, *args, **options):
        total = expire_inventory_reservations(batch_size=options["batch_size"])
        self.stdout.write(self.style.SUCCESS(f"{total} رزرو منقضی شد."))
