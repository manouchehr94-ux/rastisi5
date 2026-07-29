"""اعتبارسنجیِ ساختاری/معناییِ قالب(های) صنف — بدون تغییر داده مگر با --apply.

نگاه کنید به ADR-26. این دستور فقط لایه‌ی نازک CLI روی
``apps.catalog.services.template_validation_service`` است — هیچ منطق
اعتبارسنجی این‌جا تکرار نمی‌شود.
"""
import json

from django.core.management.base import BaseCommand

from apps.catalog.models import IndustryTemplate
from apps.catalog.services.template_validation_service import validate_and_persist, validate_industry_template


class Command(BaseCommand):
    help = "اعتبارسنجی قالب(های) صنف؛ به‌طور پیش‌فرض فقط گزارش می‌دهد (تغییری در داده نمی‌دهد مگر با --apply)"

    def add_arguments(self, parser):
        parser.add_argument("--industry", default=None, help="فقط این اسلاگ صنف را اعتبارسنجی کن")
        parser.add_argument(
            "--template-version", type=int, default=None, dest="template_version",
            help="فقط این نسخه را اعتبارسنجی کن (با --industry)",
        )
        parser.add_argument("--json", action="store_true", help="خروجی JSON قابل‌پردازش ماشینی")
        parser.add_argument("--strict", action="store_true", help="هشدار هم مانع production_ready شود (با --apply)")
        parser.add_argument("--errors-only", action="store_true", help="فقط خطاها را نمایش بده، نه هشدار/اطلاعات")
        parser.add_argument(
            "--apply", action="store_true",
            help="نتیجه را ذخیره کن و آمادگیِ قالب را طبق نتیجه به‌روزرسانی کن (بدون این پرچم، دستور فقط‌خواندنی است)",
        )

    def handle(self, *args, **options):
        queryset = IndustryTemplate.objects.all().order_by("slug", "version")
        if options["industry"]:
            queryset = queryset.filter(slug=options["industry"])
        if options["template_version"] is not None:
            queryset = queryset.filter(version=options["template_version"])

        templates = list(queryset)
        if not templates:
            self.stderr.write(self.style.WARNING("هیچ قالبی با این فیلتر یافت نشد."))
            self.exit_code = 1
            return

        results = []
        any_invalid = False
        for template in templates:
            if options["apply"]:
                result = validate_and_persist(template, strict=options["strict"])
            else:
                result = validate_industry_template(template)
            results.append(result)
            if not result.is_valid:
                any_invalid = True

        if options["json"]:
            payload = [r.as_dict() for r in results]
            self.stdout.write(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            self._print_human(results, errors_only=options["errors_only"])

        total = len(results)
        valid_count = sum(1 for r in results if r.is_valid)
        total_errors = sum(len(r.errors) for r in results)
        total_warnings = sum(len(r.warnings) for r in results)
        if not options["json"]:
            self.stdout.write("")
            self.stdout.write(
                f"خلاصه: {valid_count}/{total} قالب معتبر — {total_errors} خطا، {total_warnings} هشدار در مجموع."
            )

        if any_invalid:
            raise SystemExit(1)

    def _print_human(self, results, *, errors_only):
        for result in results:
            template = result.template
            status = "✅ معتبر" if result.is_valid else "❌ نامعتبر"
            self.stdout.write(
                f"{template.slug} v{template.version} ({template.name}) — {status} — امتیاز کیفیت: "
                f"{result.quality_score}"
            )
            for issue in result.errors:
                self.stdout.write(self.style.ERROR(f"  [ERROR] {issue.code}: {issue.message}"))
            if not errors_only:
                for issue in result.warnings:
                    self.stdout.write(self.style.WARNING(f"  [WARN]  {issue.code}: {issue.message}"))
                for issue in result.infos:
                    self.stdout.write(f"  [INFO]  {issue.code}: {issue.message}")
