from django.core.management.base import BaseCommand

from apps.notifications.services.notification_service import deliver_pending


class Command(BaseCommand):
    help = "اعلان‌هایِ در-انتظارِ صف را واقعاً ارسال می‌کند (پیامک/ایمیل؛ درون‌برنامه‌ای نیازی به ارسال ندارد)."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=200)

    def handle(self, *args, **options):
        result = deliver_pending(limit=options["limit"])
        self.stdout.write(self.style.SUCCESS(
            f"{result['processed']} اعلان پردازش شد — {result['sent']} ارسال‌شده، {result['failed']} ناموفق."
        ))
