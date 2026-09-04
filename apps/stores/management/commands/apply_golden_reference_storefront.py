"""Management command — set up the Golden Reference Storefront (G1).

Turns the isolated ``rasti-mode-demo`` store into the first visually complete
Golden Reference Storefront: a premium multi-brand fashion/lifestyle store a
prospective merchant can visit to see what a finished RastiSi storefront looks
like.

It is a thin, reproducible orchestration over existing infrastructure:

1. Run the idempotent demo seed (``seed_ready_template_fashion_demo``) to
   establish the real catalog/content and the ``fashion_promo_catalog`` Ready
   Template baseline (Apply + Publish).
2. Apply + publish the Golden customization
   (``golden_reference_service.apply_golden_reference_storefront``): identity
   palette, premium global shell variants, and the approved commercial Home
   composition — all through the normal preset/appearance/publish contracts.

Idempotent and tenant-scoped: only the fixed ``rasti-mode-demo`` slug is ever
touched. Re-running converges to the same published state (no duplicate rows).
The destructive ``--reset`` (which deletes and rebuilds ONLY the demo store) is
forwarded to the seed and must never be used on protected/real merchant stores.

This does NOT add a Ready Template — the A8 catalog stays at exactly 50. The
store's recorded provenance remains ``fashion_promo_catalog``.
"""

from io import StringIO

from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError

from apps.storefront_builder.services import golden_reference_service
from apps.stores.management.commands.seed_ready_template_fashion_demo import (
    STORE_SLUG,
)
from apps.stores.models import Store

GOLDEN_BASELINE_TEMPLATE_KEY = golden_reference_service.GOLDEN_BASELINE_TEMPLATE_KEY


class Command(BaseCommand):
    help = (
        "برپاییِ «Golden Reference Storefront» رویِ فروشگاهِ Demoِ ایزوله "
        f"(«{STORE_SLUG}») — یک فروشگاهِ پوشاک/لایف‌استایلِ چندبرندِ premiumِ "
        "کاملاً بصری، ساخته‌شده تماماً از رویِ قراردادهایِ تولیدِ موجود. "
        "Idempotent و Tenant-scoped."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--owner-username",
            default="",
            help="یوزرنیمِ یک کاربرِ موجود که (اختیاری) مالکِ StoreMembership این فروشگاهِ Demo می‌شود.",
        )
        parser.add_argument(
            "--reset",
            action="store_true",
            help=(
                f"پیش از برپایی، فقط فروشگاهِ Demo با اسلاگِ ثابتِ «{STORE_SLUG}» را کاملاً "
                "حذف و بازسازی می‌کند (به دستورِ seed فوروارد می‌شود). هرگز روی فروشگاهِ "
                "واقعی/محافظت‌شده استفاده نشود."
            ),
        )

    def handle(self, *args, **options):
        seed_args = ["--ready-template", GOLDEN_BASELINE_TEMPLATE_KEY]
        if options.get("reset"):
            seed_args.append("--reset")
        owner_username = (options.get("owner_username") or "").strip()
        if owner_username:
            seed_args += ["--owner-username", owner_username]

        # Step 1 — real catalog/content + baseline Ready Template (idempotent).
        call_command("seed_ready_template_fashion_demo", *seed_args, stdout=StringIO())

        try:
            store = Store.objects.get(slug=STORE_SLUG)
        except Store.DoesNotExist as exc:  # pragma: no cover - seed always creates it
            raise CommandError(
                f"فروشگاهِ Demo «{STORE_SLUG}» پس از اجرای seed یافت نشد."
            ) from exc

        # Step 2 — Golden customization via existing preset/appearance/publish.
        published = golden_reference_service.apply_golden_reference_storefront(store)
        home = published.home_page()
        section_order = list(home.sections.order_by("order").values_list("section_key", flat=True))

        self.stdout.write(
            self.style.SUCCESS(
                "apply_golden_reference_storefront با موفقیت اجرا شد:\n"
                f"  Store: {store.slug}\n"
                f"  Baseline Ready Template (provenance): {GOLDEN_BASELINE_TEMPLATE_KEY}\n"
                f"  Palette: {golden_reference_service.GOLDEN_PALETTE_SLUG}\n"
                f"  Header: {golden_reference_service.GOLDEN_HEADER_VARIANT}\n"
                f"  Footer: {golden_reference_service.GOLDEN_FOOTER_VARIANT}\n"
                f"  Bottom Nav: {golden_reference_service.GOLDEN_BOTTOM_NAV_VARIANT}\n"
                f"  Home ({len(section_order)} بخش): {' → '.join(section_order)}\n"
                f"  Published version: #{published.pk}\n"
            )
        )
