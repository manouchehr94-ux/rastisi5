"""پاک‌سازیِ نهاییِ فروشگاه‌هایی که دوره‌ی نگهداریِ حذفِ نرم‌شان تمام شده
(Section 14). پیش‌فرض یک dry-run است — فقط گزارش می‌دهد، هیچ‌چیز پاک
نمی‌شود؛ فقط با ``--execute`` صریح واقعاً حذف می‌کند."""

from django.core.management.base import BaseCommand

from apps.stores.services.deletion_service import purge_due_stores


class Command(BaseCommand):
    help = "فروشگاه‌های رسیده به تاریخِ پاک‌سازیِ نهایی را حذف می‌کند. پیش‌فرض dry-run است."

    def add_arguments(self, parser):
        parser.add_argument(
            "--execute", action="store_true",
            help="بدونِ این پرچم، فقط گزارش می‌دهد (dry-run) و هیچ‌چیز واقعاً حذف نمی‌شود.",
        )
        parser.add_argument("--actor-username", type=str, default="")

    def handle(self, *args, **options):
        actor = None
        if options["actor_username"]:
            from django.contrib.auth import get_user_model

            User = get_user_model()
            actor = User.objects.filter(username=options["actor_username"]).first()

        dry_run = not options["execute"]
        results = purge_due_stores(dry_run=dry_run, actor=actor)

        if not results:
            self.stdout.write(self.style.SUCCESS("هیچ فروشگاهی برایِ پاک‌سازی آماده نیست."))
            return

        for row in results:
            label = f"{row['name']} ({row['slug']}, {row['platform_code']})"
            if dry_run:
                self.stdout.write(f"[dry-run] برایِ پاک‌سازی آماده است: {label}")
            elif row["purged"]:
                self.stdout.write(self.style.SUCCESS(f"پاک شد: {label}"))
            else:
                self.stderr.write(self.style.ERROR(f"شکست در پاک‌سازیِ {label}: {row['error']}"))

        succeeded = sum(1 for r in results if r.get("purged"))
        failed = sum(1 for r in results if r.get("error"))
        if dry_run:
            self.stdout.write(self.style.WARNING(f"{len(results)} فروشگاه در انتظارِ پاک‌سازی (dry-run، هیچ‌چیز حذف نشد)."))
        else:
            self.stdout.write(self.style.SUCCESS(f"{succeeded} پاک شد، {failed} شکست خورد."))
