"""Phase 3 — دستور idempotent برای ساختِ دیتای قطعی (deterministic) و
مستقل از دادهٔ Production، برایِ اجرایِ مجموعه‌تست‌هایِ Locust
(``loadtest/``) رویِ یک محیطِ staging.

هرگز روی دیتابیسِ واقعیِ Production اجرا نشود — این دستور چند Storeِ
جعلی، کالا، و یک حسابِ staff با پسوردِ شناخته‌شده می‌سازد. یک نگهبانِ
صریح (``_guard_not_real_production``) قبل از هر نوشتنی، پیکربندیِ دامنهٔ
این محیط را بررسی می‌کند: اگر ``RASTISI_ADMIN_DOMAIN_SUFFIX`` دقیقاً
همانِ دامنهٔ واقعیِ Production (``rastisi.ir``) باشد و ``DEBUG=False``
باشد — یعنی این محیط از نظرِ پیکربندی قابلِ‌تشخیص از Productionِ واقعی
نیست — دستور بدونِ ``--confirm-not-production`` صریح متوقف می‌شود.

Idempotent: مثلِ ``seed_rastisi_fashion_demo``، همه‌جا از
``get_or_create``/``update_or_create`` رویِ فیلدِ یکتا استفاده می‌شود.

استفاده:
    python manage.py seed_loadtest_fixtures
    python manage.py seed_loadtest_fixtures --stores 5 --products-per-store 100
    python manage.py seed_loadtest_fixtures --confirm-not-production   # فقط اگر واقعاً لازم بود

نگاه کنید به ``loadtest/README.md`` برایِ گردشِ کارِ کامل.
"""

from __future__ import annotations

from decimal import Decimal

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.catalog.models import Category, Product, Vendor
from apps.core.models import ShopSettings
from apps.stores.hostnames import normalize_admin_subdomain
from apps.stores.models import Store, StoreDomain, StoreMembership

User = get_user_model()

ADMIN_USERNAME = "09120000001"
ADMIN_PASSWORD_DEFAULT = "LoadTest!Pass123"  # noqa: S105 - staging-only fixture credential, never production
STORE_SLUG_PREFIX = "loadtest"


class Command(BaseCommand):
    help = (
        "Creates deterministic, disposable multi-tenant fixture data "
        "(stores, categories, products, one shared admin user) for the "
        "Phase 3 Locust suite to run against. Never targets or touches "
        "production data — see the in-file docstring and "
        "loadtest/README.md."
    )

    def add_arguments(self, parser):
        parser.add_argument("--stores", type=int, default=3, help="Number of storefronts to create/update.")
        parser.add_argument(
            "--products-per-store", type=int, default=50,
            help="Products per store. Every store always gets a product with the fixed slug "
            "'loadtest-product-1', which loadtest/locustfile.py hardcodes.",
        )
        parser.add_argument(
            "--admin-password", default=ADMIN_PASSWORD_DEFAULT,
            help="Password for the single shared load-test admin user (owner of every seeded store).",
        )
        parser.add_argument(
            "--confirm-not-production", action="store_true",
            help="Required only if this environment's domain configuration is indistinguishable "
            "from real RastiSi production (RASTISI_ADMIN_DOMAIN_SUFFIX=rastisi.ir and DEBUG=False).",
        )

    def handle(self, *args, **options):
        self._guard_not_real_production(options["confirm_not_production"])

        store_count = options["stores"]
        products_per_store = options["products_per_store"]
        if store_count < 1 or products_per_store < 1:
            raise CommandError("--stores and --products-per-store must both be >= 1.")

        with transaction.atomic():
            admin_user = self._seed_admin_user(options["admin_password"])
            hosts = []
            for index in range(1, store_count + 1):
                store = self._seed_store(index)
                hostname = self._seed_domain(store)
                self._seed_membership(store, admin_user)
                ShopSettings.provision_for(store)
                vendor = self._seed_vendor(store)
                categories = self._seed_categories(store)
                self._seed_products(store, vendor, categories, products_per_store)
                hosts.append(hostname)

        self.stdout.write(self.style.SUCCESS(f"Seeded {store_count} load-test store(s)."))
        self.stdout.write("")
        self.stdout.write("Suggested loadtest environment variables:")
        self.stdout.write(f"  LOADTEST_TENANT_HOSTS={','.join(hosts)}")
        self.stdout.write(f"  LOADTEST_ADMIN_HOSTS={','.join(hosts)}")
        self.stdout.write(f"  LOADTEST_ADMIN_USERNAME={ADMIN_USERNAME}")
        self.stdout.write(f"  LOADTEST_ADMIN_PASSWORD={options['admin_password']}")
        self.stdout.write("")
        self.stdout.write(
            "Remember LOADTEST_ALLOWED_HOSTS must also include every host above (and the --host "
            "you pass to locust) or the suite's safety guard will refuse to run — see loadtest/README.md."
        )

    # ------------------------------------------------------------------ guard

    def _guard_not_real_production(self, confirmed: bool) -> None:
        canonical = getattr(settings, "RASTISI_CANONICAL_DOMAIN_SUFFIX", "").lower().strip(".")
        admin_suffix = getattr(settings, "RASTISI_ADMIN_DOMAIN_SUFFIX", "").lower().strip(".")
        indistinguishable_from_production = (
            canonical == "rastisi.ir" and admin_suffix == "rastisi.ir" and not settings.DEBUG
        )
        if indistinguishable_from_production and not confirmed:
            raise CommandError(
                "Refusing to run: this environment's domain configuration "
                "(RASTISI_ADMIN_DOMAIN_SUFFIX=rastisi.ir, DEBUG=False) is "
                "indistinguishable from real RastiSi production. This command "
                "creates fake stores/products and a staff account with a known "
                "password — it must never run against a real production "
                "database. If this really is a disposable staging database that "
                "happens to mirror production's domain config, re-run with "
                "--confirm-not-production."
            )

    # ------------------------------------------------------------------ seeding

    def _seed_admin_user(self, password: str):
        user, created = User.objects.get_or_create(
            username=ADMIN_USERNAME, defaults={"is_staff": True},
        )
        user.is_staff = True
        user.set_password(password)
        user.save()
        self.stdout.write(f"  admin user: {'created' if created else 'updated'} ({ADMIN_USERNAME})")
        return user

    def _seed_store(self, index: int) -> Store:
        slug = f"{STORE_SLUG_PREFIX}-{index}"
        store, created = Store.objects.get_or_create(
            slug=slug,
            defaults={
                "name": f"فروشگاه تست بار {index}",
                "admin_subdomain": normalize_admin_subdomain(slug),
                "status": Store.Status.ACTIVE,
                "onboarding_stage": Store.OnboardingStage.DONE,
                "onboarding_completed_at": timezone.now(),
            },
        )
        if not created and store.status != Store.Status.ACTIVE:
            store.status = Store.Status.ACTIVE
            store.save(update_fields=["status", "updated_at"])
        return store

    def _seed_domain(self, store: Store) -> str:
        hostname = f"{store.admin_subdomain}.{settings.RASTISI_ADMIN_DOMAIN_SUFFIX}"
        domain, created = StoreDomain.objects.get_or_create(
            store=store, hostname=hostname,
            defaults={
                "is_primary": True,
                "domain_type": StoreDomain.DomainType.PLATFORM_SUBDOMAIN,
                "verification_status": StoreDomain.VerificationStatus.VERIFIED,
                "verified_at": timezone.now(),
            },
        )
        if not created and domain.verification_status != StoreDomain.VerificationStatus.VERIFIED:
            domain.verification_status = StoreDomain.VerificationStatus.VERIFIED
            domain.verified_at = timezone.now()
            domain.is_primary = True
            domain.save(update_fields=["verification_status", "verified_at", "is_primary", "updated_at"])
        return hostname

    def _seed_membership(self, store: Store, admin_user) -> None:
        membership, created = StoreMembership.objects.get_or_create(
            store=store, user=admin_user,
            defaults={
                "role": StoreMembership.Role.OWNER,
                "status": StoreMembership.MembershipStatus.ACTIVE,
                "accepted_at": timezone.now(),
            },
        )
        if not created and membership.status != StoreMembership.MembershipStatus.ACTIVE:
            membership.status = StoreMembership.MembershipStatus.ACTIVE
            membership.role = StoreMembership.Role.OWNER
            membership.accepted_at = membership.accepted_at or timezone.now()
            membership.save(update_fields=["status", "role", "accepted_at", "updated_at"])

    def _seed_vendor(self, store: Store) -> Vendor:
        vendor, _ = Vendor.objects.get_or_create(
            store=store, slug="loadtest-vendor", defaults={"name": "فروشندهٔ تست بار"},
        )
        return vendor

    def _seed_categories(self, store: Store) -> list[Category]:
        categories = []
        for i in range(1, 4):
            category, _ = Category.objects.get_or_create(
                store=store, slug=f"loadtest-category-{i}",
                defaults={"name": f"دستهٔ تست بار {i}", "is_active": True},
            )
            categories.append(category)
        return categories

    def _seed_products(self, store: Store, vendor: Vendor, categories: list[Category], count: int) -> None:
        for i in range(1, count + 1):
            # Every store always has a product at the fixed slug
            # "loadtest-product-1" — loadtest/locustfile.py hardcodes this
            # so every task can hit a real product-detail page without
            # first scraping a listing page for a real slug.
            slug = "loadtest-product-1" if i == 1 else f"loadtest-product-{i}"
            Product.objects.get_or_create(
                store=store, slug=slug,
                defaults={
                    "vendor": vendor,
                    "category": categories[i % len(categories)],
                    "name": f"کالای تست بار {i}",
                    "sku": f"LOADTEST-{store.slug}-{i}",
                    "price": Decimal("100000") + Decimal(i * 1000),
                    "stock": 100,
                    "status": Product.Status.ACTIVE,
                    "discount_percent": 10 if i % 5 == 0 else 0,
                },
            )
