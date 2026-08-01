"""لایه‌ی سرویسِ یکپارچه‌سازی‌های سطحِ Store — اتصال/قطعِ اتصال/تستِ فرمت،
با ثبتِ حسابرسی برایِ هر تغییر (نگاه کنید به ``apps.core.services.audit_service``،
بازاستفاده‌شده، نه یک دفترِ حسابرسیِ جداگانه)."""

from django.utils import timezone

from apps.core.services.audit_service import record_audit_event
from apps.stores.integrations.registry import all_providers, get_provider
from apps.stores.models import StoreIntegrationConnection


class IntegrationError(Exception):
    """خطای قابل‌نمایشِ اتصال/تست یکپارچه‌سازی."""


class UnknownProviderError(IntegrationError):
    pass


def _require_provider(provider_code: str):
    provider = get_provider(provider_code)
    if provider is None:
        raise UnknownProviderError(f"یکپارچه‌سازیِ ناشناخته: {provider_code!r}")
    return provider


def get_or_create_connection(*, store, provider_code: str) -> StoreIntegrationConnection:
    _require_provider(provider_code)
    connection, _created = StoreIntegrationConnection.objects.get_or_create(
        store=store, provider_code=provider_code,
    )
    return connection


def connect(*, store, provider_code: str, values: dict, actor) -> StoreIntegrationConnection:
    """اعتبارنامه‌ها را (پس از اعتبارسنجیِ فرمتِ واقعیِ Provider) ذخیره و
    یکپارچه‌سازی را فعال می‌کند."""
    provider = _require_provider(provider_code)
    error = provider.validate(values)
    if error:
        raise IntegrationError(error)

    connection = get_or_create_connection(store=store, provider_code=provider_code)
    was_connected = connection.is_active
    connection.set_credentials(values)
    connection.is_active = True
    connection.connected_at = connection.connected_at or timezone.now()
    connection.save(update_fields=["encrypted_credentials", "is_active", "connected_at", "updated_at"])

    record_audit_event(
        store=store, actor=actor,
        action_code="integration.connected" if not was_connected else "integration.credentials_updated",
        object_type="StoreIntegrationConnection", object_id=connection.pk, object_label=provider.display_name,
    )
    return connection


def disconnect(*, store, provider_code: str, actor) -> StoreIntegrationConnection:
    provider = _require_provider(provider_code)
    connection = get_or_create_connection(store=store, provider_code=provider_code)
    connection.is_active = False
    connection.save(update_fields=["is_active", "updated_at"])

    record_audit_event(
        store=store, actor=actor, action_code="integration.disconnected",
        object_type="StoreIntegrationConnection", object_id=connection.pk, object_label=provider.display_name,
    )
    return connection


def test_connection(*, store, provider_code: str, actor) -> StoreIntegrationConnection:
    """«تستِ اتصال» یعنی اعتبارسنجیِ واقعیِ فرمتِ اعتبارنامه‌ی ذخیره‌شده —
    نه یک فراخوانیِ شبکه به APIِ مستندنشده‌ی بیرونی (که بدونِ مدارکِ
    تأییدشده نمی‌توان صحتش را تضمین کرد؛ نگاه کنید به داکیومنتِ ماژولِ
    registry برایِ دلیلِ کامل)."""
    provider = _require_provider(provider_code)
    connection = get_or_create_connection(store=store, provider_code=provider_code)
    error = provider.validate(connection.get_credentials())

    connection.last_tested_at = timezone.now()
    connection.last_test_result = "failed" if error else "success"
    connection.last_test_message = error or "فرمتِ اعتبارنامه‌ی ذخیره‌شده معتبر است."
    connection.save(update_fields=["last_tested_at", "last_test_result", "last_test_message", "updated_at"])

    record_audit_event(
        store=store, actor=actor, action_code="integration.tested",
        object_type="StoreIntegrationConnection", object_id=connection.pk, object_label=provider.display_name,
        metadata={"result": connection.last_test_result},
    )
    return connection


def connections_context(*, store) -> list[dict]:
    """برایِ رندرِ صفحه‌ی تنظیماتِ یکپارچه‌سازی‌ها — یک ردیف به‌ازایِ هر
    Provider، صرف‌نظر از این‌که Store قبلاً به آن وصل شده یا نه."""
    existing = {c.provider_code: c for c in StoreIntegrationConnection.objects.filter(store=store)}
    rows = []
    for provider in all_providers():
        connection = existing.get(provider.code)
        rows.append({
            "provider": provider,
            "connection": connection,
            "is_connected": bool(connection and connection.is_active),
            "credentials": connection.get_credentials() if connection else {},
        })
    return rows
