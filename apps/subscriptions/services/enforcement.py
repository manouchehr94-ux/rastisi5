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
