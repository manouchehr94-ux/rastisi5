"""پیش‌نمایش و اجرایِ تغییرِ پلن برایِ Merchant Admin (ADR-70/71/72).

تغییرِ پلن یک عملِ دومرحله‌ای است: (۱) پیش‌نمایش که تفاوتِ قابلیت‌ها و
هشدارهایِ تنزل (متریک‌هایی که مصرفِ فعلی از سقفِ پلنِ هدف بیشتر است) را نشان
می‌دهد و یک «توکنِ پیش‌نمایش» تولید می‌کند؛ (۲) اجرا که فقط اگر توکن با
وضعیتِ فعلیِ اشتراک هم‌خوان باشد انجام می‌شود — در غیر این صورت پیش‌نمایش
کهنه شده (اشتراک بینِ پیش‌نمایش و اجرا تغییر کرده) و اجرا رد می‌شود تا کاربر
تصمیمی بر اساسِ داده‌ی قدیمی نگیرد.

در Checkpoint 5A هیچ پولی جابه‌جا نمی‌شود (ADR-72) — تغییرِ پلن فقط
Entitlementها را عوض می‌کند. جمع‌آوریِ پرداختِ آنلاین کارِ Checkpoint 5B است.
"""

import hashlib

from apps.subscriptions import entitlements as ekeys
from apps.subscriptions.models import EntitlementDefinition, PlanVersion
from apps.subscriptions.services import entitlement_service as ent
from apps.subscriptions.services import subscription_service as svc
from apps.subscriptions.services import usage_service as usage


class PlanChangeError(Exception):
    """خطای قابل‌نمایش هنگام پیش‌نمایش/اجرایِ تغییرِ پلن."""


class StalePreviewError(PlanChangeError):
    """پیش‌نمایش کهنه شده — اشتراک از زمانِ تولیدِ پیش‌نمایش تغییر کرده است."""


def _preview_token(subscription, target_version) -> str:
    """توکنی که وضعیتِ اشتراک (نسخه‌ی پلن + زمانِ آخرین تغییر) و نسخه‌ی هدف را
    اثرانگشت می‌کند؛ اگر هرکدام عوض شود توکن دیگر هم‌خوان نیست."""
    raw = (
        f"{subscription.pk}:{subscription.plan_version_id}:"
        f"{subscription.updated_at.isoformat()}:{target_version.pk}"
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:40]


def _entitlement_value(store, key, entitlement_type, *, plan_version):
    """مقدارِ قابل‌مقایسه‌ی یک Entitlement رویِ یک نسخه‌ی پلن. برایِ boolean یک
    bool، برایِ سقف‌ها ``None`` (نامحدود)/``0`` (خاموش)/عدد."""
    if entitlement_type == EntitlementDefinition.EntitlementType.BOOLEAN:
        return ent.has_entitlement(store, key, plan_version=plan_version)
    return ent.get_entitlement_limit(store, key, plan_version=plan_version)


def preview_plan_change(store, target_version) -> dict:
    """تفاوتِ قابلیت‌ها و هشدارهایِ تنزل را بینِ پلنِ فعلی و ``target_version``
    محاسبه می‌کند و یک توکنِ پیش‌نمایش برمی‌گرداند.

    اگر Store اشتراکِ جاری نداشته باشد یا نسخه‌ی هدف منتشرشده نباشد
    ``PlanChangeError`` می‌اندازد."""
    subscription = ent.get_current_subscription(store)
    if subscription is None:
        raise PlanChangeError("این فروشگاه اشتراکِ جاری ندارد؛ تغییرِ پلن ممکن نیست.")
    if target_version.status != PlanVersion.Status.PUBLISHED:
        raise PlanChangeError("فقط نسخه‌ی «منتشرشده» را می‌توان انتخاب کرد.")

    current_version = subscription.plan_version
    is_same = current_version.pk == target_version.pk

    # تفاوتِ Entitlementها
    entitlement_changes = []
    definitions = {d.key: d for d in EntitlementDefinition.objects.filter(is_active=True)}
    for key, definition in definitions.items():
        current_value = _entitlement_value(store, key, definition.entitlement_type, plan_version=current_version)
        target_value = _entitlement_value(store, key, definition.entitlement_type, plan_version=target_version)
        if current_value != target_value:
            entitlement_changes.append({
                "key": key,
                "name": definition.name,
                "type": definition.entitlement_type,
                "current": current_value,
                "target": target_value,
            })

    # هشدارهایِ تنزل: متریک‌هایی که مصرفِ فعلی از سقفِ پلنِ هدف بیشتر است.
    over_limit_warnings = []
    for key, label in {**ekeys.COUNT_METRIC_KEYS, **ekeys.PERIOD_METRIC_KEYS}.items():
        target_limit = ent.get_entitlement_limit(store, key, plan_version=target_version)
        if target_limit is None:
            continue  # نامحدود در پلنِ هدف — هشداری نیست
        if key in ekeys.COUNT_METRIC_KEYS:
            current_usage = usage.get_count_usage(store, key)
        else:
            current_usage = usage.get_period_usage(store, key)
        if current_usage > target_limit:
            over_limit_warnings.append({
                "key": key,
                "label": label,
                "current": current_usage,
                "target_limit": target_limit,
            })

    return {
        "subscription": subscription,
        "current_version": current_version,
        "current_plan": current_version.plan,
        "target_version": target_version,
        "target_plan": target_version.plan,
        "is_same": is_same,
        "entitlement_changes": entitlement_changes,
        "over_limit_warnings": over_limit_warnings,
        "has_downgrade_risk": bool(over_limit_warnings),
        "token": _preview_token(subscription, target_version),
    }


def execute_plan_change(store, target_version, *, preview_token, actor=None, reason="", idempotency_key=""):
    """تغییرِ پلن را اجرا می‌کند — فقط اگر ``preview_token`` با وضعیتِ فعلیِ
    اشتراک هم‌خوان باشد. اگر اشتراک از زمانِ پیش‌نمایش تغییر کرده باشد
    ``StalePreviewError`` می‌اندازد (محافظت در برابرِ پیش‌نمایشِ کهنه).

    هیچ پولی جابه‌جا نمی‌شود (ADR-72)."""
    subscription = ent.get_current_subscription(store)
    if subscription is None:
        raise PlanChangeError("این فروشگاه اشتراکِ جاری ندارد؛ تغییرِ پلن ممکن نیست.")
    if target_version.status != PlanVersion.Status.PUBLISHED:
        raise PlanChangeError("فقط نسخه‌ی «منتشرشده» را می‌توان انتخاب کرد.")
    expected = _preview_token(subscription, target_version)
    if not preview_token or preview_token != expected:
        raise StalePreviewError(
            "این پیش‌نمایش دیگر معتبر نیست (اشتراکِ شما تغییر کرده)؛ لطفاً دوباره پیش‌نمایش بگیرید."
        )
    updated = svc.change_plan_version(
        subscription, target_version, actor=actor, reason=reason, idempotency_key=idempotency_key,
    )
    ent.clear_entitlement_cache()
    return updated
