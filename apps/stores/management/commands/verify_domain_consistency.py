"""ناسازگاری‌هایِ دامنه/زیردامنه را *فقط می‌خواند* و گزارش می‌دهد (هرگز چیزی
نمی‌نویسد). با ``--strict`` اگر حتی یک مشکل پیدا شود با کدِ خروجِ غیرِصفر
خارج می‌شود — مناسبِ اجرا در CI/health-check، دقیقاً مطابق
``verify_subscription_consistency``/``verify_billing_consistency``."""

from django.core.management.base import BaseCommand, CommandError

from apps.stores.services.domain_consistency_service import check_domain_consistency


class Command(BaseCommand):
    help = "سازگاریِ دامنه‌ها/زیردامنه‌ها را بررسی می‌کند (فقط‌خواندنی). --strict برایِ کدِ خروجِ غیرِصفر."

    def add_arguments(self, parser):
        parser.add_argument(
            "--strict", action="store_true",
            help="اگر هر مشکلی (error یا warning) پیدا شد با کدِ خروجِ ۱ خارج شو.",
        )

    def handle(self, *args, **options):
        issues = check_domain_consistency()
        errors = [i for i in issues if i["severity"] == "error"]
        warnings = [i for i in issues if i["severity"] == "warning"]

        for issue in errors:
            self.stderr.write(self.style.ERROR(f"[error] {issue['message']}"))
        for issue in warnings:
            self.stdout.write(self.style.WARNING(f"[warning] {issue['message']}"))

        if not issues:
            self.stdout.write(self.style.SUCCESS("هیچ ناسازگاری‌ای یافت نشد."))
            return

        summary = f"{len(errors)} خطا، {len(warnings)} هشدار."
        if errors or (options["strict"] and warnings):
            raise CommandError(f"بررسیِ سازگاری ناموفق: {summary}")
        self.stdout.write(self.style.WARNING(summary))
