"""تبدیلِ اختیاریِ «گروه دوم» (ProductTag purpose=collection) به
MerchantCollection واقعی. پیش‌فرض همیشه dry-run است — نگاه کنید به
``apps.catalog.services.legacy_collection_migration_service``."""

from django.core.management.base import BaseCommand, CommandError

from apps.catalog.services.legacy_collection_migration_service import (
    apply_legacy_conversion,
    preview_legacy_conversion,
)
from apps.stores.models import Store


class Command(BaseCommand):
    help = (
        "«گروه دوم»های فعلیِ ProductTag(purpose=collection) را به MerchantCollection واقعی تبدیل می‌کند. "
        "پیش‌فرض همیشه dry-run است؛ برای نوشتن واقعی در دیتابیس --apply را صریحاً پاس دهید."
    )

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="فقط گزارش — هیچ چیزی نوشته نمی‌شود (پیش‌فرض).")
        parser.add_argument("--apply", action="store_true", help="تغییرات واقعاً در دیتابیس ذخیره می‌شوند.")
        parser.add_argument("--store", type=str, default="", help="فقط این Store (بر اساس slug) — پیش‌فرض همه‌ی فروشگاه‌ها.")

    def handle(self, *args, **options):
        if options["apply"] and options["dry_run"]:
            raise CommandError("--dry-run و --apply هم‌زمان مجاز نیستند.")

        store = None
        if options["store"]:
            try:
                store = Store.objects.get(slug=options["store"])
            except Store.DoesNotExist:
                raise CommandError(f"فروشگاهی با slug={options['store']!r} یافت نشد.") from None

        apply_changes = bool(options["apply"])
        report = apply_legacy_conversion(store=store) if apply_changes else preview_legacy_conversion(store=store)

        mode = "APPLY (نوشته شد)" if apply_changes else "DRY-RUN (چیزی نوشته نشد)"
        self.stdout.write(self.style.NOTICE(f"حالت: {mode}"))
        self.stdout.write("")

        for result in report.results:
            line = f"  Store #{result.store_id} — «{result.tag_name}» (tag pk={result.tag_id}): {result.status}"
            if result.collection_id:
                line += f" → collection pk={result.collection_id}"
            if result.items_created or result.items_already_present:
                line += f" | کالای جدید: {result.items_created}، از‌قبل‌موجود: {result.items_already_present}"
            if result.detail:
                line += f" | {result.detail}"
            self.stdout.write(line)

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS(
            f"ساخته‌شده: {report.created_count} | استفاده‌ی‌مجدد: {report.reused_count} | "
            f"رد‌شده: {report.skipped_count} | تداخل‌یافته: {report.conflicted_count} | "
            f"مجموع کالای اضافه‌شده: {report.total_items_created}"
        ))
        if report.dry_run:
            self.stdout.write(self.style.NOTICE("این یک dry-run بود — برای اعمالِ واقعی، با --apply دوباره اجرا کنید."))
