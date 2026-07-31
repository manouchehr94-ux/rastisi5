"""تغییرِ نامِ دائمیِ یک فروشگاه — فقط ابزارِ مدیرِ پلتفرم (Section 11).

تا Platform Admin UI (Section 13) این عملیات را به یک صفحه‌ی وب منتقل کند،
این دستورِ مدیریتی تنها راهِ اجرایِ آن است — همیشه با یک ``--reason``ی
غیرِخالی، و همیشه حسابرسی‌شده (``AuditLogEntry``، action_code
``store.handle_renamed_by_superuser``)."""

from django.core.management.base import BaseCommand, CommandError

from apps.stores.models import Store
from apps.stores.services.handle_service import HandleError, rename_platform_handle_as_superuser


class Command(BaseCommand):
    help = "نامِ دائمیِ یک فروشگاه را تغییر می‌دهد (فقط مدیرِ پلتفرم — همیشه با دلیل)."

    def add_arguments(self, parser):
        parser.add_argument("store_slug", type=str)
        parser.add_argument("new_label", type=str)
        parser.add_argument("--reason", type=str, required=True)
        parser.add_argument("--actor-username", type=str, default="")

    def handle(self, *args, **options):
        try:
            store = Store.objects.get(slug=options["store_slug"])
        except Store.DoesNotExist as exc:
            raise CommandError(f"فروشگاهی با اسلاگِ «{options['store_slug']}» یافت نشد.") from exc

        actor = None
        if options["actor_username"]:
            from django.contrib.auth import get_user_model

            User = get_user_model()
            try:
                actor = User.objects.get(username=options["actor_username"])
            except User.DoesNotExist as exc:
                raise CommandError(f"کاربرِ «{options['actor_username']}» یافت نشد.") from exc

        try:
            new_domain = rename_platform_handle_as_superuser(
                store=store, new_label=options["new_label"], actor=actor, reason=options["reason"],
            )
        except HandleError as exc:
            raise CommandError(str(exc)) from exc

        self.stdout.write(self.style.SUCCESS(f"نامِ دائمیِ فروشگاهِ «{store.name}» به «{new_domain.hostname}» تغییر کرد."))
