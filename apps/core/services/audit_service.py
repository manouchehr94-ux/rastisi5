"""دفتر حسابرسیِ Store-owned — ثبتِ رخدادهای حساسِ پنل مدیریت.

نگاه کنید به ADR-36 در ``SAAS_DOMAIN_DECISIONS.md``. لایه‌های سرویسِ
کسب‌وکار (نه ویو، نه تمپلیت) باید ``record_audit_event`` را فراخوانی کنند —
هیچ رخداد حسابرسی‌ای نباید مستقیماً از ویو ثبت شود.
"""

import json

from apps.core.models import AuditLogEntry

#: کلیدهای متادیتا که هرگز نباید در دفتر حسابرسی ذخیره شوند، حتی اگر
#: فراخواننده به‌اشتباه آن‌ها را در ``metadata``/``before``/``after``
#: بگذارد — خط دفاعی آخر، نه جایگزین احتیاطِ خودِ فراخواننده.
_FORBIDDEN_KEYS = frozenset({
    "password", "password1", "password2", "new_password", "old_password",
    "token", "access_token", "refresh_token", "auth_token", "csrf_token",
    "secret", "api_key", "api_secret", "gateway_secret", "merchant_secret",
    "card_number", "cvv", "cvv2", "card_cvv",
})

_REDACTED = "***REDACTED***"


def _redact(value):
    if isinstance(value, dict):
        return {
            key: (_REDACTED if key.lower() in _FORBIDDEN_KEYS else _redact(val))
            for key, val in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_redact(item) for item in value]
    return value


def _summarize(value) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    try:
        return json.dumps(_redact(value), ensure_ascii=False, default=str, sort_keys=True)
    except TypeError:
        return str(value)


def record_audit_event(
    *, store, action_code: str, actor=None, object_type: str = "", object_id="",
    object_label: str = "", before=None, after=None, metadata: dict | None = None,
    request_id: str = "", result: str = AuditLogEntry.ResultStatus.SUCCESS,
) -> AuditLogEntry:
    """یک رخداد حسابرسی ثبت می‌کند؛ در صورت تکرارِ همان ``request_id`` برای
    همان (فروشگاه، کد عملیات)، رخداد تازه‌ای ساخته نمی‌شود (idempotent در
    برابر retry) و ردیفِ موجود برگردانده می‌شود.
    """
    if request_id:
        existing = AuditLogEntry.objects.filter(
            store=store, action_code=action_code, request_id=request_id,
        ).first()
        if existing is not None:
            return existing

    return AuditLogEntry.objects.create(
        store=store,
        actor=actor,
        action_code=action_code,
        object_type=object_type,
        object_id=str(object_id) if object_id not in (None, "") else "",
        object_label=object_label,
        before_summary=_summarize(before),
        after_summary=_summarize(after),
        metadata=_redact(metadata or {}),
        request_id=request_id,
        result=result,
    )


def list_audit_events(
    store, *, action_code: str = "", actor_id=None, object_type: str = "", q: str = "",
):
    queryset = AuditLogEntry.objects.filter(store=store).select_related("actor")
    if action_code:
        queryset = queryset.filter(action_code=action_code)
    if actor_id:
        queryset = queryset.filter(actor_id=actor_id)
    if object_type:
        queryset = queryset.filter(object_type=object_type)
    if q:
        from django.db.models import Q
        queryset = queryset.filter(
            Q(object_label__icontains=q) | Q(action_code__icontains=q) | Q(object_id__icontains=q)
        )
    return queryset
