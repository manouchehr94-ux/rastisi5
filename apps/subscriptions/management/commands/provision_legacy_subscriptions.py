"""پلن/نسخه/Entitlement/اشتراک‌هایِ Legacy را برایِ همه‌ی فروشگاه‌هایِ موجود
idempotent می‌سازد (ADR-65). همان منطقی که data migration اجرا می‌کند، اینجا
برایِ اجرایِ دستی/تعمیری در دسترس است — اجرایِ دوباره هیچ فروشگاهی را محدود
نمی‌کند و ردیفِ تکراری نمی‌سازد."""

from django.core.management.base import BaseCommand

from apps.subscriptions.services.legacy_service import provision_legacy_real


class Command(BaseCommand):
    help = "اشتراکِ نامحدودِ Legacy را برایِ فروشگاه‌هایِ بدونِ اشتراکِ جاری می‌سازد (idempotent)."

    def handle(self, *args, **options):
        counts = provision_legacy_real()
        self.stdout.write(self.style.SUCCESS(
            "Legacy provisioning انجام شد: "
            f"plan={counts['plan']}, version={counts['version']}, "
            f"entitlements={counts['entitlements']}, subscriptions={counts['subscriptions']}."
        ))
