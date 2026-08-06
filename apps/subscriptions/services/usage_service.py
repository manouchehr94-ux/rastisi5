"""سرویسِ سنجشِ مصرف (Usage) — نگاه کنید به ADR-68/69.

دو دسته متریک:
1. متریک‌هایِ *شمارشی* (کالا/تنوع/کارمند/انبار/سگمنت): زنده از
   ``QuerySet.count()`` خوانده می‌شوند — هیچ شمارنده‌ی ذخیره‌شده‌ای نگه داشته
   نمی‌شود تا خطرِ ناهماهنگی نباشد (ADR-68). حذفِ رکورد به‌طورِ طبیعی مصرف
   را کم می‌کند.
2. متریک‌هایِ *دوره‌ای* (ردیف‌هایِ واردات/تعدادِ صادرات در ماه): در
   ``UsageRecord`` به‌ازایِ هر دوره‌ی تقویمیِ ماهانه ذخیره و اتمیک افزوده
   می‌شوند؛ در دوره‌ی بعد صفر می‌شوند.

سقفِ عددی از ``entitlement_service.get_entitlement_limit`` می‌آید (پلن)، نه
از این‌جا — این ماژول فقط «چقدر مصرف شده» را می‌داند."""

from django.db import transaction
from django.db.models import F
from django.utils import timezone

from apps.subscriptions import entitlements as ekeys
from apps.subscriptions.models import UsageRecord


class UsageError(Exception):
    """خطای سنجش/مصرف — متریکِ ناشناخته یا مقدارِ نامعتبر."""


# ================================================================== متریک‌هایِ شمارشی (زنده)

def _count_products(store):
    from apps.catalog.models import Product
    # پیش‌نویسِ داخلیِ در حالِ ساخت (``is_draft_placeholder``) هنوز یک کالایِ
    # واقعی نیست — نباید تا زمانِ ذخیره‌ی نهاییِ معتبر جزوِ سقفِ اشتراک محسوب شود.
    return Product.objects.filter(store=store, is_draft_placeholder=False).count()


def _count_variants(store):
    from apps.catalog.models import ProductVariant
    # تنوع‌هایِ فعالِ غیرمنسوخ — همان تعریفی که سقفِ تولیدِ تنوع رویِ آن اعمال
    # می‌شود (نگاه کنید به §17/§28).
    return ProductVariant.objects.filter(store=store, is_active=True, is_obsolete=False).count()


def _count_staff(store):
    from apps.stores.models import StoreMembership
    # فقط صندلیِ مصرف‌کننده: فعال + دعوت‌شده‌ی پذیرفته (ADR §27). لغوشده‌ها
    # شمرده نمی‌شوند.
    return StoreMembership.objects.filter(
        store=store,
        status__in=[StoreMembership.MembershipStatus.ACTIVE, StoreMembership.MembershipStatus.INVITED],
    ).count()


def _count_warehouses(store):
    from apps.catalog.models import Warehouse
    return Warehouse.objects.filter(store=store, is_active=True).count()


def _count_segments(store):
    from apps.customers.models import CustomerSegment
    return CustomerSegment.objects.filter(store=store).count()


_COUNT_METRICS = {
    ekeys.CATALOG_PRODUCTS: _count_products,
    ekeys.CATALOG_VARIANTS: _count_variants,
    ekeys.STAFF_MEMBERS: _count_staff,
    ekeys.INVENTORY_WAREHOUSES: _count_warehouses,
    ekeys.CUSTOMERS_SEGMENTS: _count_segments,
}


def get_count_usage(store, key) -> int:
    counter = _COUNT_METRICS.get(key)
    if counter is None:
        raise UsageError(f"متریکِ شمارشیِ «{key}» تعریف نشده است.")
    return counter(store)


# ================================================================== متریک‌هایِ دوره‌ای

def current_period_bounds(now=None):
    """مرزهایِ دوره‌ی جاری (ماهِ تقویمی) — (شروع، پایان)."""
    now = now or timezone.now()
    start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if start.month == 12:
        end = start.replace(year=start.year + 1, month=1)
    else:
        end = start.replace(month=start.month + 1)
    return start, end


def get_period_usage(store, key, *, now=None) -> int:
    start, _end = current_period_bounds(now)
    record = UsageRecord.objects.filter(store=store, metric_key=key, period_start=start).first()
    return record.used_quantity if record else 0


@transaction.atomic
def consume_period_usage(store, key, amount, *, subscription=None, now=None) -> UsageRecord:
    """مصرفِ دوره‌ای را اتمیک افزایش می‌دهد و رکوردِ دوره را برمی‌گرداند.

    idempotencyِ عملیات مسئولیتِ فراخوان است (مثلاً اجرایِ واردات فقط یک‌بار
    اجرا می‌شود چون Jobِ نهایی‌شده دوباره اجرا نمی‌شود؛ ADR-61/68) — این تابع
    صرفاً افزایشِ race-safe را تضمین می‌کند (``F()`` + ``get_or_create`` +
    قفلِ ردیف)."""
    if amount < 0:
        raise UsageError("مقدارِ مصرف نمی‌تواند منفی باشد.")
    start, end = current_period_bounds(now)
    record, _created = UsageRecord.objects.select_for_update().get_or_create(
        store=store, metric_key=key, period_start=start,
        defaults={"period_end": end, "subscription": subscription, "used_quantity": 0},
    )
    if amount:
        UsageRecord.objects.filter(pk=record.pk).update(used_quantity=F("used_quantity") + amount)
        record.refresh_from_db(fields=["used_quantity"])
    return record


# ================================================================== خلاصه‌ی مصرف برایِ UI

def get_metric_usage(store, key, *, now=None):
    """یک ردیفِ ساخت‌یافته‌ی مصرف برایِ یک متریک: (current, limit, remaining,
    unlimited)."""
    from apps.subscriptions.services.entitlement_service import get_entitlement_limit

    if key in _COUNT_METRICS:
        current = get_count_usage(store, key)
    else:
        current = get_period_usage(store, key, now=now)
    limit = get_entitlement_limit(store, key)
    unlimited = limit is None
    remaining = None if unlimited else max(limit - current, 0)
    return {
        "key": key,
        "current": current,
        "limit": limit,
        "unlimited": unlimited,
        "remaining": remaining,
        "over_limit": (not unlimited) and current > limit,
    }


def get_usage_summary(store, *, now=None) -> list:
    """فهرستِ همه‌ی متریک‌هایِ قابلِ‌نمایش برایِ صفحه‌ی Usage."""
    rows = []
    for key, label in ekeys.COUNT_METRIC_KEYS.items():
        row = get_metric_usage(store, key, now=now)
        row["label"] = label
        row["period"] = False
        rows.append(row)
    for key, label in ekeys.PERIOD_METRIC_KEYS.items():
        row = get_metric_usage(store, key, now=now)
        row["label"] = label
        row["period"] = True
        rows.append(row)
    return rows


# ================================================================== گیتِ سقف

def check_usage_limit(store, key, *, requested_increment=1, now=None) -> None:
    """اگر ``current + requested_increment`` از سقفِ پلن عبور کند،
    ``UsageLimitExceeded`` می‌اندازد. سقفِ ``None`` (نامحدود) هرگز رد نمی‌کند.
    این فقط سقفِ عددی را می‌سنجد؛ گیتِ قابلیت/وضعیت جداست."""
    from apps.subscriptions.services.entitlement_service import UsageLimitExceeded, get_entitlement_limit

    limit = get_entitlement_limit(store, key)
    if limit is None:
        return
    if key in _COUNT_METRICS:
        current = get_count_usage(store, key)
    else:
        current = get_period_usage(store, key, now=now)
    if current + requested_increment > limit:
        raise UsageLimitExceeded(key, limit=limit, current=current)
