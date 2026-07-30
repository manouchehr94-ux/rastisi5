"""سازگاریِ صورتحساب را *فقط می‌خواند* و گزارش می‌دهد (هرگز چیزی نمی‌نویسد).
با ``--strict`` اگر مشکلی پیدا شود با کدِ خروجِ غیرِصفر خارج می‌شود."""

from django.core.management.base import BaseCommand, CommandError

from apps.billing.services.consistency_service import check_billing_consistency


class Command(BaseCommand):
    help = "سازگاریِ صورتحساب را بررسی می‌کند (فقط‌خواندنی). --strict برایِ کدِ خروجِ غیرِصفر."

    def add_arguments(self, parser):
        parser.add_argument("--strict", action="store_true", help="اگر هر مشکلی پیدا شد با کدِ ۱ خارج شو.")

    def handle(self, *args, **options):
        issues = check_billing_consistency()
        errors = [i for i in issues if i["severity"] == "error"]
        warnings = [i for i in issues if i["severity"] == "warning"]

        for issue in errors:
            self.stderr.write(self.style.ERROR(f"[error] {issue['message']}"))
        for issue in warnings:
            self.stdout.write(self.style.WARNING(f"[warning] {issue['message']}"))

        if not issues:
            self.stdout.write(self.style.SUCCESS("هیچ ناسازگاریِ صورتحسابی یافت نشد."))
            return

        summary = f"{len(errors)} خطا، {len(warnings)} هشدار."
        if errors or (options["strict"] and warnings):
            raise CommandError(f"بررسیِ سازگاریِ صورتحساب ناموفق: {summary}")
        self.stdout.write(self.style.WARNING(summary))
