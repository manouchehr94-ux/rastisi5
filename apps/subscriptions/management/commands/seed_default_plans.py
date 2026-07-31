"""بارگذاریِ ایدمپوتنتِ چهار پلنِ اولیه‌ی راستیسی (Section 7):
آزمایشی/پایه/حرفه‌ای/سازمانی.

هرگز یک Planِ از قبل موجود را بازنویسی نمی‌کند (``get_or_create`` — مقادیرِ
``defaults`` فقط در لحظه‌ی ساخت اعمال می‌شوند)، و هرگز برایِ Planای که از
قبل حداقل یک PlanVersion دارد نسخه‌ی تازه نمی‌سازد — تغییرِ قیمت/حق‌دسترسیِ
یک پلنِ موجود باید از مسیرِ صریحِ نسخه‌ی تازه (Platform Admin/`plan_
service.create_plan_version`) عبور کند، نه از اجرایِ دوباره‌ی این دستور
(ADR-63، تغییرناپذیریِ نسخه‌ی منتشرشده).

روزهایِ تریالِ پلنِ «آزمایشی» از ``PlatformConfiguration.default_trial_
days`` خوانده می‌شود (Section 2) — نه یک عددِ هاردکدشده."""

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.portal.services.platform_config_service import get_platform_configuration
from apps.subscriptions.entitlements import (
    CATALOG_PRODUCTS,
    CUSTOMERS_SEGMENTS,
    INVENTORY_WAREHOUSES,
    STAFF_MEMBERS,
    sync_entitlement_definitions,
)
from apps.subscriptions.models import Plan, PlanVersion
from apps.subscriptions.services.plan_service import (
    create_plan_version,
    publish_plan_version,
    set_plan_entitlement,
)

DOMAINS_CUSTOM = "domains.custom"
REPORTS_ADVANCED = "reports.advanced"
CATALOG_IMPORT = "catalog.import"
CATALOG_EXPORT = "catalog.export"

# (code, name, public_title, description, display_order, is_recommended)
PLAN_DEFINITIONS = [
    (
        "trial", "آزمایشی", "آزمایشی", "برای امتحان کردن راستیسی، پیش از هر تعهدی.",
        0, False,
    ),
    (
        "basic", "پایه", "پایه", "برای فروشگاه‌های تازه‌کار — یک فروشگاه با آدرسِ دائمیِ راستیسی.",
        1, False,
    ),
    (
        "professional", "حرفه‌ای", "حرفه‌ای", "برای کسب‌وکارهایی که رشد می‌کنند — دامنه‌ی اختصاصی و گزارش‌های پیشرفته.",
        2, True,
    ),
    (
        "enterprise", "سازمانی", "سازمانی", "برای کسب‌وکارهای بزرگ — محدودیت‌های قابل‌تنظیم و امکاناتِ ویژه.",
        3, False,
    ),
]

# code -> {entitlement_key: (is_unlimited, integer_limit) یا (is_enabled فقط برای boolean)}
PLAN_LIMITS = {
    "trial": {
        CATALOG_PRODUCTS: (False, 20), STAFF_MEMBERS: (False, 1),
        INVENTORY_WAREHOUSES: (False, 1), CUSTOMERS_SEGMENTS: (False, 1),
        DOMAINS_CUSTOM: False, REPORTS_ADVANCED: False,
        CATALOG_IMPORT: False, CATALOG_EXPORT: False,
    },
    "basic": {
        CATALOG_PRODUCTS: (False, 100), STAFF_MEMBERS: (False, 3),
        INVENTORY_WAREHOUSES: (False, 1), CUSTOMERS_SEGMENTS: (False, 3),
        DOMAINS_CUSTOM: False, REPORTS_ADVANCED: False,
        CATALOG_IMPORT: True, CATALOG_EXPORT: True,
    },
    "professional": {
        CATALOG_PRODUCTS: (False, 1000), STAFF_MEMBERS: (False, 10),
        INVENTORY_WAREHOUSES: (False, 5), CUSTOMERS_SEGMENTS: (False, 20),
        DOMAINS_CUSTOM: True, REPORTS_ADVANCED: True,
        CATALOG_IMPORT: True, CATALOG_EXPORT: True,
    },
    "enterprise": {
        CATALOG_PRODUCTS: (True, None), STAFF_MEMBERS: (True, None),
        INVENTORY_WAREHOUSES: (True, None), CUSTOMERS_SEGMENTS: (True, None),
        DOMAINS_CUSTOM: True, REPORTS_ADVANCED: True,
        CATALOG_IMPORT: True, CATALOG_EXPORT: True,
    },
}

# code -> (display_price, billing_interval)
PLAN_PRICING = {
    "trial": (0, PlanVersion.BillingInterval.NONE),
    "basic": (490000, PlanVersion.BillingInterval.MONTHLY),
    "professional": (1490000, PlanVersion.BillingInterval.MONTHLY),
    "enterprise": (4990000, PlanVersion.BillingInterval.MONTHLY),
}


class Command(BaseCommand):
    help = "چهار پلنِ اولیه‌ی راستیسی را idempotent می‌سازد (Section 7)."

    @transaction.atomic
    def handle(self, *args, **options):
        sync_entitlement_definitions()
        config = get_platform_configuration()

        created_plans = 0
        created_versions = 0

        for code, name, public_title, description, display_order, is_recommended in PLAN_DEFINITIONS:
            plan, plan_created = Plan.objects.get_or_create(
                code=code,
                defaults={
                    "name": name, "public_title": public_title, "description": description,
                    "is_active": True, "is_publicly_selectable": True,
                    "is_recommended": is_recommended, "display_order": display_order,
                },
            )
            created_plans += int(plan_created)

            if plan.versions.exists():
                continue  # نسخه‌ای از قبل هست — طبق ADR-63 دست‌نخورده می‌ماند.

            display_price, billing_interval = PLAN_PRICING[code]
            trial_days = config.default_trial_days if code == "trial" else 0
            version = create_plan_version(
                plan, display_price=display_price, billing_interval=billing_interval,
                trial_days=trial_days,
            )
            for entitlement_key, value in PLAN_LIMITS[code].items():
                if isinstance(value, tuple):
                    is_unlimited, integer_limit = value
                    set_plan_entitlement(
                        version, entitlement_key,
                        is_enabled=True, is_unlimited=is_unlimited, integer_limit=integer_limit,
                    )
                else:
                    set_plan_entitlement(version, entitlement_key, is_enabled=value)
            publish_plan_version(version)
            created_versions += 1

        self.stdout.write(self.style.SUCCESS(
            f"{created_plans} پلنِ تازه، {created_versions} نسخه‌ی تازه ساخته شد."
        ))
