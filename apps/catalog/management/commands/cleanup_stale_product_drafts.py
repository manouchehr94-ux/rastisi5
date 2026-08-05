"""پیش‌نویس‌های رهاشده‌ی «افزودنِ کالا» (``Product.is_draft_placeholder=True``)
را که مدتی طولانی دست‌نخورده مانده‌اند حذف می‌کند — قابلِ اجرا به‌صورت دوره‌ای
(مثلاً هر چند ساعت از یک cron/celery beat).

Idempotent: بر رویِ ``updated_at`` فیلتر می‌کند (نگاه کنید به
``apps.catalog.services.product_draft_service.cleanup_stale_product_drafts``)،
پس پیش‌نویسی که merchant هنوز رویش کار می‌کند (هر GETِ صفحه‌ی ویرایش این
فیلد را تازه می‌کند) هرگز حذف نمی‌شود؛ اجرایِ دوباره روی همان داده چیزی
بیشتر حذف نمی‌کند."""

from django.core.management.base import BaseCommand

from apps.catalog.services.product_draft_service import cleanup_stale_product_drafts


class Command(BaseCommand):
    help = "پیش‌نویس‌های داخلیِ رهاشده‌ی «افزودنِ کالا» را که قدیمی‌تر از N ساعت‌اند حذف می‌کند."

    def add_arguments(self, parser):
        parser.add_argument(
            "--older-than-hours", type=int, default=48,
            help="فقط پیش‌نویس‌هایی که updated_at آن‌ها قدیمی‌تر از این تعداد ساعت است حذف می‌شوند (پیش‌فرض ۴۸).",
        )

    def handle(self, *args, **options):
        result = cleanup_stale_product_drafts(older_than_hours=options["older_than_hours"])
        if result.deleted_count:
            ids = ", ".join(str(pk) for pk in result.deleted_ids)
            self.stdout.write(self.style.SUCCESS(f"{result.deleted_count} پیش‌نویسِ رهاشده حذف شد (pk: {ids})."))
        else:
            self.stdout.write("هیچ پیش‌نویسِ رهاشده‌ای برای حذف پیدا نشد.")
