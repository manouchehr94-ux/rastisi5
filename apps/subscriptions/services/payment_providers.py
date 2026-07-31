"""انتزاعِ درگاهِ پرداختِ پلتفرم (Section 8) — چندارائه‌دهنده، اما در این فاز
فقط یک ارائه‌دهنده‌ی dev/test واقعاً پیاده‌سازی شده. هیچ اعتبارِ واقعیِ
درگاهِ بانکی (زرین‌پال/زیبال و...) در این کدبیس نیست — افزودنِ آن یک تصمیمِ
جداگانه‌ی بعدی است (این محدودیت باید در گزارشِ نهایی صریحاً اعلام شود، نه
پنهان).

هر ارائه‌دهنده فقط یک وظیفه دارد: برایِ یک ``PlatformPaymentAttempt`` آدرسِ
هدایت (redirect) را برمی‌گرداند. تأییدِ نهاییِ پرداخت همیشه از طریقِ
``apps.subscriptions.services.billing_service.confirm_payment_attempt``
انجام می‌شود — نه اینجا؛ این ماژول هرگز مستقیماً وضعیتِ فاکتور/اشتراک را
تغییر نمی‌دهد."""

from django.urls import reverse


class PaymentProviderError(Exception):
    """درگاهِ پرداختِ درخواست‌شده در دسترس/معتبر نیست."""


class BasePaymentProvider:
    code = ""

    def start_url(self, attempt) -> str:
        raise NotImplementedError


class DevPaymentProvider(BasePaymentProvider):
    """درگاهِ آزمایشی — یک صفحه‌ی داخلیِ «بانکِ جعلی» که مالک را به انتخابِ
    آشکارِ «پرداختِ موفق» یا «پرداختِ ناموفق» می‌برد. هرگز پیامک/تراکنشِ واقعی
    ارسال نمی‌کند؛ فقط برایِ توسعه/تست/دمو است (مشابهِ الگویِ
    ``apps.sms.services.backends.ConsoleBackend``)."""

    code = "dev"

    def start_url(self, attempt) -> str:
        # این مسیر همیشه رویِ urlconf پرتالِ پلتفرم زندگی می‌کند (هرگز رویِ
        # میزبانِ پنلِ مدیریتِ یک Store)، پس صریحاً همان urlconf را می‌دهیم —
        # نه پیش‌فرضِ ``get_urlconf()``، که فقط داخلِ چرخه‌ی یک درخواستِ
        # واقعی (پس از میان‌افزارِ مسیریابیِ میزبان) مقداردهی می‌شود و در
        # فراخوانیِ مستقیمِ سرویس (مثلاً از تست) وجود ندارد.
        return reverse("portal:billing-dev-provider", args=[attempt.public_id], urlconf="shop_core.urls_platform")


_PROVIDERS = {
    DevPaymentProvider.code: DevPaymentProvider(),
}


def get_payment_provider(code: str) -> BasePaymentProvider:
    try:
        return _PROVIDERS[code]
    except KeyError:
        raise PaymentProviderError(f"درگاهِ پرداختِ «{code}» شناخته‌شده نیست.") from None


def available_provider_codes() -> list[str]:
    return list(_PROVIDERS.keys())
