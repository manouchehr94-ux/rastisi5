"""ناسازگاری‌هایِ دامنه/زیردامنه را فقط *می‌خواند* و گزارش می‌دهد (هرگز چیزی
نمی‌نویسد) — برای ``verify_domain_consistency`` (Section U/V). هر مورد: dict
با ``severity`` (error/warning) و ``message``، دقیقاً مطابق الگویِ
``apps.subscriptions.services.subscription_service.check_subscription_
consistency`` و خواهرانش (billing/inventory)."""

from django.conf import settings
from django.db.models import Count

from apps.stores.hostnames import RESERVED_PLATFORM_SUBDOMAINS
from apps.stores.models import Store, StoreDomain


def check_domain_consistency() -> list:
    issues = []

    # ۱) نام میزبانِ نرمال‌شده‌ی تکراری — قیدِ unique=True باید جلویش را
    # بگیرد؛ این فقط دفاعِ لایه‌ی دوم است (مثلاً پس از migration دستی).
    dupes = (
        StoreDomain.objects.values("hostname").annotate(n=Count("id")).filter(n__gt=1)
    )
    for row in dupes:
        issues.append({
            "severity": "error",
            "message": f"نام میزبانِ «{row['hostname']}» بیش از یک بار ثبت شده ({row['n']} ردیف).",
        })

    # ۲) Storeای بدونِ شناسه‌ی پایدارِ پلتفرم (platform_code خالی) — قیدِ
    # DB باید NULL را رد کند؛ این‌جا فقط رشته‌ی خالی را می‌گیرد.
    for store in Store.objects.filter(platform_code=""):
        issues.append({
            "severity": "error",
            "message": f"فروشگاه {store.pk} ({store.name}) شناسه‌ی پایدارِ پلتفرم ندارد.",
        })

    # ۳) بیش از یک دامنه‌ی اصلی برایِ یک Store — قیدِ
    # uniq_primary_domain_per_store باید جلویش را بگیرد؛ دفاعِ لایه‌ی دوم.
    dupe_primary = (
        StoreDomain.objects.filter(is_primary=True)
        .values("store_id").annotate(n=Count("id")).filter(n__gt=1)
    )
    for row in dupe_primary:
        issues.append({
            "severity": "error",
            "message": f"فروشگاه {row['store_id']} بیش از یک دامنه‌ی اصلی دارد ({row['n']}).",
        })

    # ۴) Storeای که همه‌ی دامنه‌هایش بازنشسته‌اند (هیچ دامنه‌ی فعالِ اصلی‌ای
    # ندارد) اما هنوز ACTIVE است — یعنی هیچ آدرسِ زنده‌ای برایِ آن باقی
    # نمانده (باید هرگز رخ ندهد؛ سرویسِ ادعایِ زیردامنه/تعیینِ دستهِ دائمی
    # همیشه باید دامنه‌ی اصلیِ تازه را قبل از بازنشسته‌کردنِ قدیمی بسازد).
    stores_with_primary = set(
        StoreDomain.objects.filter(is_primary=True).values_list("store_id", flat=True)
    )
    active_store_ids_with_any_domain = set(
        StoreDomain.objects.filter(store__status=Store.Status.ACTIVE).values_list("store_id", flat=True)
    )
    for store_id in active_store_ids_with_any_domain - stores_with_primary:
        issues.append({
            "severity": "error",
            "message": f"فروشگاه {store_id} فعال است اما هیچ دامنه‌ی اصلیِ زنده‌ای ندارد "
                       f"(همه‌ی دامنه‌هایش بازنشسته/نامعتبرند).",
        })

    # ۴ب) دامنه‌ی بازنشسته‌ای که هنوز is_primary=True مانده — تناقض؛ باید
    # هرگز رخ ندهد (قیدِ retired_domain_is_never_primary باید جلویش را
    # بگیرد؛ دفاعِ لایه‌ی دوم برایِ داده‌ای که از مسیرِ دیگری وارد شده).
    for domain in StoreDomain.objects.filter(retired_at__isnull=False, is_primary=True):
        issues.append({
            "severity": "error",
            "message": f"دامنه‌ی بازنشسته‌ی «{domain.hostname}» هنوز is_primary=True است.",
        })

    # ۵) برخوردِ نامِ رزروشده — برچسبِ چپِ نام میزبان با فهرستِ رزروِ
    # زیردامنه‌ی پلتفرم برخورد دارد (باید توسطِ اعتبارسنجیِ ادعای زیردامنه
    # جلوگیری شود؛ اینجا برایِ داده‌ای که از مسیرِ دیگری وارد شده بررسی
    # می‌شود، مثلاً seed/import دستی).
    suffix = f".{settings.RASTISI_ADMIN_DOMAIN_SUFFIX}"
    for domain in StoreDomain.objects.filter(hostname__endswith=suffix):
        label = domain.hostname[: -len(suffix)]
        if "." not in label and label in RESERVED_PLATFORM_SUBDOMAINS:
            issues.append({
                "severity": "error",
                "message": f"نام میزبانِ «{domain.hostname}» از برچسبِ رزروشده‌ی «{label}» استفاده می‌کند.",
            })

    # ۶) برخوردِ دامنه‌ی عمومی با میزبانِ پنل مدیریتِ یک فروشگاه (باید هرگز
    # رخ ندهد — قیدِ unique=True روی هر دو ستون به‌تنهایی این را ممکن
    # نمی‌کند مگر با ورودِ دستی).
    admin_hosts = {
        f"{s.admin_subdomain}.{settings.RASTISI_ADMIN_DOMAIN_SUFFIX}": s.pk
        for s in Store.objects.only("id", "admin_subdomain")
    }
    for domain in StoreDomain.objects.all():
        colliding_store_id = admin_hosts.get(domain.hostname)
        if colliding_store_id is not None and colliding_store_id != domain.store_id:
            issues.append({
                "severity": "error",
                "message": f"دامنه‌ی «{domain.hostname}» (فروشگاه {domain.store_id}) با میزبانِ "
                           f"پنل مدیریتِ فروشگاه {colliding_store_id} برخورد دارد.",
            })

    # ۷) Storeی فعال بدونِ هیچ دامنه‌ی generated_trial ای — پیش از پرتال
    # ساخته شده‌اند (مثلاً Akhlaghi)، پس فقط هشدار است نه خطا.
    stores_with_trial = set(
        StoreDomain.objects.filter(domain_type=StoreDomain.DomainType.GENERATED_TRIAL)
        .values_list("store_id", flat=True)
    )
    for store in Store.objects.filter(status=Store.Status.ACTIVE).exclude(pk__in=stores_with_trial):
        issues.append({
            "severity": "warning",
            "message": f"فروشگاه {store.pk} ({store.name}) هیچ دامنه‌ی آزمایشیِ generated_trial ندارد.",
        })

    return issues
