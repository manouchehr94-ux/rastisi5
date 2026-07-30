"""رجیستریِ Providerهایِ پرداختِ اشتراک (ADR-75).

Providerِ فعال از ``settings.RASTISI_BILLING_PROVIDER`` تعیین می‌شود (پیش‌فرض
«manual»). رازِ Webhook فقط از تنظیمات/محیط خوانده می‌شود، هرگز از پایگاه‌داده
یا کد."""

from django.conf import settings

from apps.billing.providers.base import BillingProviderError
from apps.billing.providers.manual import ManualProvider

_PROVIDERS = {
    ManualProvider.code: ManualProvider(),
}


def get_provider(code: str | None = None):
    """نمونه‌ی Providerِ خواسته‌شده (یا Providerِ فعالِ پیش‌فرض)."""
    code = code or active_provider_code()
    provider = _PROVIDERS.get(code)
    if provider is None:
        raise BillingProviderError(f"Providerِ «{code}» ثبت نشده است.", code="unknown_provider")
    return provider


def active_provider_code() -> str:
    return getattr(settings, "RASTISI_BILLING_PROVIDER", "manual") or "manual"


def webhook_secret() -> str:
    """رازِ تأییدِ Webhookِ Providerِ فعال — فقط از تنظیمات/محیط."""
    return getattr(settings, "RASTISI_BILLING_WEBHOOK_SECRET", "") or ""
