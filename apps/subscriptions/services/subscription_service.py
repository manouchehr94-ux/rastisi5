"""ماشینِ حالتِ اشتراک — تنها مسیرِ مجازِ تغییرِ وضعیتِ ``StoreSubscription``.
نگاه کنید به ADR-66 (ماشینِ حالت)، ADR-67 (تریال/grace)، ADR-71 (رخدادها).

هر انتقال: ``transaction.atomic`` + ``select_for_update`` رویِ اشتراک، فقط
انتقالِ قانونی (جدولِ ``ALLOWED_TRANSITIONS``)، idempotent، ثبتِ actor،
ساختِ ``SubscriptionEvent`` و رخدادِ Audit Log. هیچ ویو‌ای نباید مستقیماً
``subscription.status = ...`` بنویسد."""

from django.db import transaction
from django.utils import timezone

from apps.core.services.audit_service import record_audit_event
from apps.subscriptions.models import PlanVersion, StoreSubscription, SubscriptionEvent

S = StoreSubscription.Status
ET = SubscriptionEvent.EventType


class SubscriptionError(Exception):
    """خطای قابل‌نمایشِ عملیاتِ اشتراک — انتقالِ غیرمجاز، نسخه‌ی نامعتبر و... ."""


class IllegalTransitionError(SubscriptionError):
    """انتقالِ درخواست‌شده از وضعیتِ فعلی مجاز نیست."""


#: جدولِ انتقال‌هایِ قانونی — از هر وضعیت به کدام وضعیت‌ها می‌توان رفت
#: (نگاه کنید به ADR-66). انتقال‌هایِ غیرِ فهرست‌شده رد می‌شوند. مثال‌هایِ
#: صریحاً غیرمجاز: expired→active (بدونِ اشتراکِ تازه)، cancelled→trialing،
#: suspended→trialing.
ALLOWED_TRANSITIONS = {
    S.PENDING: {S.TRIALING, S.ACTIVE, S.CANCELLED},
    S.TRIALING: {S.ACTIVE, S.GRACE_PERIOD, S.EXPIRED, S.CANCELLED},
    S.ACTIVE: {S.GRACE_PERIOD, S.PAST_DUE, S.SUSPENDED, S.CANCELLED, S.EXPIRED},
    S.GRACE_PERIOD: {S.ACTIVE, S.PAST_DUE, S.SUSPENDED, S.EXPIRED, S.CANCELLED},
    S.PAST_DUE: {S.ACTIVE, S.GRACE_PERIOD, S.SUSPENDED, S.EXPIRED, S.CANCELLED},
    S.SUSPENDED: {S.ACTIVE, S.EXPIRED, S.CANCELLED},
    S.CANCELLED: set(),
    S.EXPIRED: set(),
}


def _record_event(subscription, *, event_type, from_status, to_status, actor, reason,
                  from_plan_version=None, to_plan_version=None, idempotency_key="", metadata=None):
    SubscriptionEvent.objects.create(
        subscription=subscription, store=subscription.store, event_type=event_type,
        from_status=from_status or "", to_status=to_status or "",
        from_plan_version=from_plan_version, to_plan_version=to_plan_version,
        actor=actor, reason=reason or "", idempotency_key=idempotency_key or "",
        metadata=metadata or {},
    )
    record_audit_event(
        store=subscription.store, actor=actor, action_code=f"subscription.{event_type}",
        object_type="StoreSubscription", object_id=str(subscription.pk),
        object_label=f"{subscription.plan_version.plan.code} → {to_status or from_status}",
        before={"status": from_status} if from_status else None,
        after={"status": to_status} if to_status else None,
        metadata=metadata or {},
        request_id=idempotency_key or "",
    )


def _transition(subscription, *, to_status, event_type, actor, reason, idempotency_key="",
                extra_fields=None, metadata=None):
    """هسته‌ی مشترکِ همه‌ی انتقال‌ها — قفل، بررسیِ قانونی‌بودن، به‌روزرسانیِ
    فیلدها، ثبتِ رخداد. idempotent: اگر اشتراک از قبل در ``to_status`` باشد
    و همان ``idempotency_key`` قبلاً رخداد ساخته باشد، بی‌اثر برمی‌گردد."""
    locked = StoreSubscription.objects.select_for_update().get(pk=subscription.pk)
    from_status = locked.status

    if from_status == to_status:
        # idempotent no-op — اگر رخدادِ همین کلید قبلاً ثبت شده باشد.
        if idempotency_key and locked.events.filter(idempotency_key=idempotency_key).exists():
            return locked
        # وضعیت از قبل درست است؛ فیلدهایِ اضافی را (در صورتِ تفاوت) اعمال
        # نمی‌کنیم تا رفتار قابل‌پیش‌بینی بماند — فقط برمی‌گردیم.
        return locked

    if to_status not in ALLOWED_TRANSITIONS.get(from_status, set()):
        raise IllegalTransitionError(
            f"انتقال از «{from_status}» به «{to_status}» مجاز نیست."
        )

    locked.status = to_status
    if to_status in StoreSubscription.TERMINAL_STATUSES:
        locked.is_current = False
    for field, value in (extra_fields or {}).items():
        setattr(locked, field, value)
    locked.save()

    _record_event(
        locked, event_type=event_type, from_status=from_status, to_status=to_status,
        actor=actor, reason=reason, idempotency_key=idempotency_key, metadata=metadata,
    )
    return locked


# ================================================================== ساختِ اشتراک

@transaction.atomic
def create_subscription(store, plan_version, *, source=StoreSubscription.Source.ADMIN, actor=None) -> StoreSubscription:
    """یک اشتراکِ ``pending`` تازه می‌سازد. اگر Store از قبل اشتراکِ جاری
    داشته باشد خطا می‌دهد (قیدِ یک‌اشتراکِ‌جاری). نسخه باید منتشرشده باشد."""
    if StoreSubscription.objects.filter(store=store, is_current=True).exists():
        raise SubscriptionError("این فروشگاه از قبل یک اشتراکِ جاری دارد.")
    if plan_version.status != PlanVersion.Status.PUBLISHED:
        raise SubscriptionError("فقط نسخه‌ی «منتشرشده»ی پلن قابلِ اشتراک است.")
    subscription = StoreSubscription.objects.create(
        store=store, plan_version=plan_version, status=S.PENDING, is_current=True, source=source,
    )
    _record_event(subscription, event_type=ET.CREATED, from_status="", to_status=S.PENDING,
                  actor=actor, reason="", to_plan_version=plan_version)
    return subscription


# ================================================================== انتقال‌ها

@transaction.atomic
def start_trial(subscription, *, actor=None, idempotency_key="") -> StoreSubscription:
    """اشتراک را به ``trialing`` می‌برد و بازه‌ی تریال را از ``trial_days``ِ
    نسخه محاسبه می‌کند (ADR-67). تغییرِ پلن مدتِ تریال را ریست نمی‌کند."""
    now = timezone.now()
    days = subscription.plan_version.trial_days
    end = now + timezone.timedelta(days=days) if days else now
    return _transition(
        subscription, to_status=S.TRIALING, event_type=ET.TRIAL_STARTED, actor=actor,
        reason="", idempotency_key=idempotency_key,
        extra_fields={"trial_start_at": now, "trial_end_at": end, "start_at": subscription.start_at or now},
    )


@transaction.atomic
def activate_subscription(subscription, *, actor=None, period_end=None, idempotency_key="") -> StoreSubscription:
    """اشتراک را فعال می‌کند. دوره‌ی جاری را تنظیم می‌کند. در 5A پول واقعی
    دریافت نمی‌شود (ADR-72) — فعال‌سازی یک اقدامِ اداری/سرویسی است."""
    now = timezone.now()
    return _transition(
        subscription, to_status=S.ACTIVE, event_type=ET.ACTIVATED, actor=actor,
        reason="", idempotency_key=idempotency_key,
        extra_fields={
            "start_at": subscription.start_at or now,
            "current_period_start": subscription.current_period_start or now,
            "current_period_end": period_end,
        },
    )


@transaction.atomic
def enter_grace_period(subscription, *, actor=None, grace_end=None, idempotency_key="") -> StoreSubscription:
    now = timezone.now()
    if grace_end is None:
        days = subscription.plan_version.grace_period_days
        grace_end = now + timezone.timedelta(days=days) if days else now
    return _transition(
        subscription, to_status=S.GRACE_PERIOD, event_type=ET.GRACE_STARTED, actor=actor,
        reason="", idempotency_key=idempotency_key, extra_fields={"grace_period_end": grace_end},
    )


@transaction.atomic
def mark_past_due(subscription, *, actor=None, idempotency_key="") -> StoreSubscription:
    return _transition(
        subscription, to_status=S.PAST_DUE, event_type=ET.PAST_DUE, actor=actor,
        reason="", idempotency_key=idempotency_key,
    )


@transaction.atomic
def suspend_subscription(subscription, *, actor=None, reason="", idempotency_key="") -> StoreSubscription:
    return _transition(
        subscription, to_status=S.SUSPENDED, event_type=ET.SUSPENDED, actor=actor,
        reason=reason, idempotency_key=idempotency_key,
        extra_fields={"suspended_at": timezone.now()},
    )


@transaction.atomic
def resume_subscription(subscription, *, actor=None, idempotency_key="") -> StoreSubscription:
    """اشتراکِ معلق/معوق/grace را دوباره فعال می‌کند (ADR-66) — هرگز به
    ``trialing`` برنمی‌گردد."""
    return _transition(
        subscription, to_status=S.ACTIVE, event_type=ET.RESUMED, actor=actor,
        reason="", idempotency_key=idempotency_key, extra_fields={"suspended_at": None},
    )


@transaction.atomic
def cancel_at_period_end(subscription, *, actor=None, idempotency_key="") -> StoreSubscription:
    """لغو را در پایانِ دوره زمان‌بندی می‌کند — اشتراک تا آن زمان فعال می‌ماند
    (وضعیت تغییر نمی‌کند، فقط پرچمِ ``cancel_at_period_end``). idempotent."""
    locked = StoreSubscription.objects.select_for_update().get(pk=subscription.pk)
    if locked.status in StoreSubscription.TERMINAL_STATUSES:
        raise IllegalTransitionError("اشتراکِ نهایی‌شده را نمی‌توان زمان‌بندیِ لغو کرد.")
    if locked.cancel_at_period_end:
        return locked
    locked.cancel_at_period_end = True
    locked.save(update_fields=["cancel_at_period_end", "updated_at"])
    _record_event(locked, event_type=ET.CANCEL_SCHEDULED, from_status=locked.status,
                  to_status=locked.status, actor=actor, reason="", idempotency_key=idempotency_key)
    return locked


@transaction.atomic
def cancel_immediately(subscription, *, actor=None, reason="", idempotency_key="") -> StoreSubscription:
    return _transition(
        subscription, to_status=S.CANCELLED, event_type=ET.CANCELLED, actor=actor,
        reason=reason, idempotency_key=idempotency_key,
        extra_fields={"cancelled_at": timezone.now(), "cancel_at_period_end": False},
    )


@transaction.atomic
def expire_subscription(subscription, *, actor=None, idempotency_key="") -> StoreSubscription:
    return _transition(
        subscription, to_status=S.EXPIRED, event_type=ET.EXPIRED, actor=actor,
        reason="", idempotency_key=idempotency_key, extra_fields={"expired_at": timezone.now()},
    )


@transaction.atomic
def change_plan_version(subscription, target_version, *, actor=None, reason="", idempotency_key="") -> StoreSubscription:
    """نسخه‌ی پلنِ اشتراک را عوض می‌کند (ارتقا/تنزل) — وضعیت را تغییر نمی‌دهد،
    فقط ``plan_version`` و رخدادِ ``plan_changed`` (ADR-70). مدتِ تریال ریست
    نمی‌شود (ADR-67). نسخه‌ی هدف باید منتشرشده باشد.

    در 5A فقط Entitlement‌ها را تغییر می‌دهد؛ هیچ پول واقعی/پروریشنی رخ
    نمی‌دهد (ADR-72)."""
    locked = StoreSubscription.objects.select_for_update().get(pk=subscription.pk)
    if locked.status in StoreSubscription.TERMINAL_STATUSES:
        raise IllegalTransitionError("اشتراکِ نهایی‌شده را نمی‌توان تغییرِ پلن داد.")
    if target_version.status != PlanVersion.Status.PUBLISHED:
        raise SubscriptionError("فقط نسخه‌ی «منتشرشده» قابلِ انتخاب است.")
    if idempotency_key and locked.events.filter(idempotency_key=idempotency_key).exists():
        return locked
    from_version = locked.plan_version
    if from_version.pk == target_version.pk:
        return locked
    locked.plan_version = target_version
    locked.save(update_fields=["plan_version", "updated_at"])
    _record_event(
        locked, event_type=ET.PLAN_CHANGED, from_status=locked.status, to_status=locked.status,
        actor=actor, reason=reason, from_plan_version=from_version, to_plan_version=target_version,
        idempotency_key=idempotency_key,
        metadata={"from_version": from_version.pk, "to_version": target_version.pk},
    )
    return locked
