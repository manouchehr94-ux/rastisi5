"""گیت‌هایِ مصرف/قابلیت برایِ نقاطِ ساختِ رکورد — لایه‌ی نازکی رویِ
``entitlement_service`` و ``usage_service`` که در *لایه‌ی سرویس* (نه فقط UI)
فراخوانی می‌شوند تا واردات/اکشنِ فله‌ای/POSTِ مستقیم هم نتوانند دور بزنند
(نگاه کنید به ADR-69، §16).

هر گیت سه لایه دارد: (۱) وضعیتِ اشتراک اجازه‌ی رشد بدهد
(``require_growth_allowed``)، (۲) قابلیت فعال باشد، (۳) سقفِ عددی نقض نشود.
به‌روزرسانیِ رکوردِ موجود هرگز از این گیت‌ها عبور نمی‌کند — فقط *ساخت*."""

from apps.subscriptions import entitlements as ekeys
from apps.subscriptions.services import entitlement_service as ent
from apps.subscriptions.services import usage_service as usage

# استثناهایِ دامنه از entitlement_service دوباره صادر می‌شوند تا فراخوان‌ها
# فقط از یک‌جا import کنند.
FeatureNotAvailable = ent.FeatureNotAvailable
UsageLimitExceeded = ent.UsageLimitExceeded
SubscriptionRestricted = ent.SubscriptionRestricted


def enforce_feature(store, key) -> None:
    """فقط گیتِ قابلیت (بدونِ سقف/وضعیت) — برایِ قابلیت‌هایِ boolean مثلِ
    واردات/صادرات که جدا از سقفِ عددی‌اند."""
    ent.check_entitlement(store, key)


def _enforce_create(store, limit_key, *, feature_key=None, count=1, check_state=True):
    if check_state:
        ent.require_growth_allowed(store)
    if feature_key is not None:
        ent.check_entitlement(store, feature_key)
    usage.check_usage_limit(store, limit_key, requested_increment=count)


def enforce_can_create_product(store, *, count=1) -> None:
    _enforce_create(store, ekeys.CATALOG_PRODUCTS, count=count)


def enforce_can_create_variants(store, *, count=1) -> None:
    _enforce_create(store, ekeys.CATALOG_VARIANTS, count=count)


def enforce_can_add_staff(store, *, count=1) -> None:
    _enforce_create(store, ekeys.STAFF_MEMBERS, count=count)


def enforce_can_create_warehouse(store, *, count=1) -> None:
    _enforce_create(store, ekeys.INVENTORY_WAREHOUSES, count=count)


def enforce_can_create_segment(store, *, count=1) -> None:
    _enforce_create(store, ekeys.CUSTOMERS_SEGMENTS, feature_key=ekeys.CUSTOMERS_SEGMENTS, count=count)


# ================================================================== واردات/صادرات
#
# واردات/صادرات دو گیت دارند که از سقفِ ساختِ رکورد جدا هستند: (۱) گیتِ
# قابلیتِ boolean (پلن اصلاً واردات/صادرات دارد؟) و (۲) سقفِ دوره‌ای
# (ردیف‌هایِ واردات در ماه / تعدادِ صادرات در ماه). خودِ رکوردهایی که واردات
# می‌سازد (کالا/تنوع) جداگانه از مسیرِ بودجه‌ی ساخت مشمولِ سقفِ عددی می‌شوند
# تا واردات نتواند سقفِ کالا/تنوع را دور بزند (§16/§28).

def enforce_import_allowed(store) -> None:
    """گیتِ قابلیتِ واردات — اگر پلنِ فعلی واردات ندارد ``FeatureNotAvailable``.
    سقفِ ردیف و بودجه‌ی ساختِ کالا جداگانه بررسی می‌شوند."""
    ent.check_entitlement(store, ekeys.CATALOG_IMPORT)


def enforce_export_allowed(store) -> None:
    """گیتِ قابلیتِ صادرات — صادرات یک عملیاتِ *خواندنی* است، پس به وضعیتِ
    محدودشده (معلق) بند نیست؛ فقط قابلیت و سقفِ دوره‌ای مهم‌اند."""
    ent.check_entitlement(store, ekeys.CATALOG_EXPORT)


def check_import_row_budget(store, row_count) -> None:
    """اگر ``مصرفِ ردیفِ این دوره + row_count`` از سقفِ ماهانه عبور کند،
    ``UsageLimitExceeded`` می‌اندازد (کلِ واردات رد می‌شود، بدونِ کوتاه‌سازیِ
    خاموش)."""
    usage.check_usage_limit(store, ekeys.CATALOG_IMPORT_ROWS_MONTHLY, requested_increment=row_count)


def consume_import_rows(store, row_count, *, subscription=None) -> None:
    """مصرفِ ردیفِ وارداتِ این دوره را افزایش می‌دهد — فقط پس از اجرایِ واقعی
    (نه پیش‌نمایش) و یک‌بار به‌ازایِ هر Job (تکرارِ اجرا مسدود است، پس
    دوباره‌شماری رخ نمی‌دهد)."""
    if row_count:
        usage.consume_period_usage(store, ekeys.CATALOG_IMPORT_ROWS_MONTHLY, row_count, subscription=subscription)


def check_export_budget(store) -> None:
    """اگر تعدادِ صادراتِ این دوره به سقفِ ماهانه رسیده باشد،
    ``UsageLimitExceeded`` می‌اندازد."""
    usage.check_usage_limit(store, ekeys.CATALOG_EXPORTS_MONTHLY, requested_increment=1)


def consume_export(store, *, subscription=None) -> None:
    """یک واحد به مصرفِ صادراتِ این دوره اضافه می‌کند — فقط پس از تکمیلِ موفقِ
    یک ``ExportJob`` (شکست مصرف نمی‌کند)."""
    usage.consume_period_usage(store, ekeys.CATALOG_EXPORTS_MONTHLY, 1, subscription=subscription)


def product_creation_budget(store):
    """بودجه‌ی ساختِ کالا برایِ یک اجرایِ واردات: ``None`` یعنی نامحدود؛ عددِ
    صحیح یعنی چند کالایِ *تازه* دیگر می‌توان ساخت. اگر وضعیتِ اشتراک اجازه‌ی
    رشد ندهد ``0`` برمی‌گرداند (ردیف‌هایِ به‌روزرسانی همچنان اجرا می‌شوند، فقط
    ساختِ رکوردِ تازه بسته است — §16/§28)."""
    access = ent.get_subscription_access_state(store)
    if not access.allows_growth:
        return 0
    limit = ent.get_entitlement_limit(store, ekeys.CATALOG_PRODUCTS)
    if limit is None:
        return None
    current = usage.get_count_usage(store, ekeys.CATALOG_PRODUCTS)
    return max(limit - current, 0)
