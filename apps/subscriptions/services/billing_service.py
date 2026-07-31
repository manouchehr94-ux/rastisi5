"""خریدِ اشتراکِ پلتفرم (Section 8/9) — فاکتور → تلاشِ پرداخت → درگاه →
فعال‌سازیِ اشتراک، فقط پس از تأییدِ *واقعیِ* پرداخت.

قاعده‌ی مطلق: پرداختِ ناموفق هرگز اشتراکی فعال نمی‌کند، هرگز داده‌ای حذف/
افشا نمی‌کند — فاکتور فقط ``PENDING`` می‌ماند (قابلِ تلاشِ دوباره). فقط
``confirm_payment_attempt`` با ``success=True`` مجاز است اشتراک را از طریقِ
ماشینِ حالتِ ``subscription_service`` تغییر دهد؛ هیچ‌جایِ دیگری مستقیماً
``StoreSubscription.status`` را نمی‌نویسد (نگاه کنید به ADR-66).

Step-up OTP رویِ این مسیر هنوز اعمال نشده — این وظیفه‌ی Section 10 است
(``PlatformConfiguration.step_up_actions`` از قبل شاملِ کلیدِ
``subscription_purchase`` است، اما نقطه‌ی enforcement هنوز به این ویو/سرویس
وصل نشده؛ این محدودیت باید در گزارشِ نهایی صریحاً اعلام شود)."""

from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from apps.stores.models import Store
from apps.subscriptions.models import PlanVersion, PlatformInvoice, PlatformPaymentAttempt, StoreSubscription
from apps.subscriptions.services import subscription_service
from apps.subscriptions.services.payment_providers import PaymentProviderError, get_payment_provider

_PERIOD_LENGTH_BY_INTERVAL = {
    PlanVersion.BillingInterval.MONTHLY: timedelta(days=30),
    PlanVersion.BillingInterval.YEARLY: timedelta(days=365),
}


class BillingError(Exception):
    """خطای قابل‌نمایشِ فرآیندِ فاکتور/پرداختِ پلتفرم."""


def _current_subscription_for_update(store: Store) -> StoreSubscription | None:
    return StoreSubscription.objects.select_for_update().filter(store=store, is_current=True).first()


@transaction.atomic
def create_invoice(*, store: Store, plan_version: PlanVersion, actor=None) -> PlatformInvoice:
    """فاکتورِ خریدِ یک نسخه‌ی پلنِ منتشرشده و پولی می‌سازد. پلنِ رایگان/بدونِ
    دوره (مثلِ پلنِ آزمایشی) قابلِ خریدِ مستقیم نیست — آن از طریقِ
    ``provision_trial_store`` گرفته می‌شود، نه این مسیر."""
    if plan_version.status != PlanVersion.Status.PUBLISHED:
        raise BillingError("فقط نسخه‌ی «منتشرشده»ی پلن قابلِ خرید است.")
    if plan_version.billing_interval == PlanVersion.BillingInterval.NONE or plan_version.display_price <= 0:
        raise BillingError("این پلن رایگان/بدونِ دوره است و از این مسیر قابلِ خرید نیست.")

    current = _current_subscription_for_update(store)
    if current is None:
        reason = PlatformInvoice.Reason.NEW_SUBSCRIPTION
    elif current.plan_version_id == plan_version.pk:
        reason = PlatformInvoice.Reason.RENEWAL
    else:
        reason = PlatformInvoice.Reason.UPGRADE

    return PlatformInvoice.objects.create(
        store=store, plan_version=plan_version, reason=reason,
        amount=plan_version.display_price, currency=plan_version.currency, created_by=actor,
    )


@transaction.atomic
def start_payment_attempt(*, invoice: PlatformInvoice, provider_code: str) -> tuple[PlatformPaymentAttempt, str]:
    """یک تلاشِ پرداختِ تازه می‌سازد و آدرسِ هدایت به درگاه را برمی‌گرداند.
    فاکتورِ غیرِ ``PENDING`` (قبلاً پرداخت‌شده/باطل‌شده) دیگر قابلِ تلاش
    نیست."""
    locked_invoice = PlatformInvoice.objects.select_for_update().get(pk=invoice.pk)
    if locked_invoice.status != PlatformInvoice.Status.PENDING:
        raise BillingError("این فاکتور دیگر در انتظارِ پرداخت نیست.")

    try:
        provider = get_payment_provider(provider_code)
    except PaymentProviderError as exc:
        raise BillingError(str(exc)) from exc
    attempt = PlatformPaymentAttempt.objects.create(
        invoice=locked_invoice, provider_code=provider_code, status=PlatformPaymentAttempt.Status.PENDING,
    )
    return attempt, provider.start_url(attempt)


@transaction.atomic
def confirm_payment_attempt(
    *, attempt: PlatformPaymentAttempt, success: bool, actor=None, provider_ref: str = "",
) -> PlatformPaymentAttempt:
    """نتیجه‌ی نهاییِ یک تلاشِ پرداخت را ثبت می‌کند. Idempotent/بازپخش-امن:
    تلاشی که از قبل به وضعیتِ نهایی رسیده، بدونِ هیچ اثری برگردانده می‌شود —
    یک callback تکراری یا دستکاری‌شده نمی‌تواند نتیجه‌ای را که قبلاً ثبت شده
    معکوس کند."""
    locked_attempt = (
        PlatformPaymentAttempt.objects.select_for_update().select_related("invoice", "invoice__store")
        .get(pk=attempt.pk)
    )
    if locked_attempt.is_final:
        return locked_attempt

    if not success:
        locked_attempt.status = PlatformPaymentAttempt.Status.FAILED
        locked_attempt.provider_ref = provider_ref
        locked_attempt.save(update_fields=["status", "provider_ref", "updated_at"])
        return locked_attempt

    locked_invoice = PlatformInvoice.objects.select_for_update().get(pk=locked_attempt.invoice_id)
    if locked_invoice.status == PlatformInvoice.Status.PAID:
        # فاکتور از طریقِ یک تلاشِ دیگر قبلاً پرداخت شده — این تلاش را
        # ناموفق/زائد علامت نمی‌زنیم (تلاشِ خودش هنوز معتبر بود)، فقط از
        # فعال‌سازیِ دوباره‌ی اشتراک صرف‌نظر می‌کنیم.
        locked_attempt.status = PlatformPaymentAttempt.Status.SUCCEEDED
        locked_attempt.provider_ref = provider_ref
        locked_attempt.save(update_fields=["status", "provider_ref", "updated_at"])
        return locked_attempt

    store = locked_invoice.store
    plan_version = locked_invoice.plan_version
    now = timezone.now()
    period_length = _PERIOD_LENGTH_BY_INTERVAL.get(plan_version.billing_interval, timedelta(days=30))
    period_end = now + period_length

    subscription = _current_subscription_for_update(store)
    if subscription is None:
        subscription = subscription_service.create_subscription(
            store, plan_version, source=StoreSubscription.Source.SELF_SERVICE, actor=actor,
        )
        subscription_service.activate_subscription(subscription, actor=actor, period_end=period_end)
    else:
        if subscription.plan_version_id != plan_version.pk:
            subscription = subscription_service.change_plan_version(
                subscription, plan_version, actor=actor, reason="paid_purchase",
            )
        if subscription.status in (StoreSubscription.Status.PENDING, StoreSubscription.Status.TRIALING):
            subscription = subscription_service.activate_subscription(subscription, actor=actor, period_end=period_end)
        else:
            subscription = subscription_service.renew_subscription(
                subscription, period_start=now, period_end=period_end, actor=actor,
            )

    locked_attempt.status = PlatformPaymentAttempt.Status.SUCCEEDED
    locked_attempt.provider_ref = provider_ref
    locked_attempt.save(update_fields=["status", "provider_ref", "updated_at"])

    locked_invoice.status = PlatformInvoice.Status.PAID
    locked_invoice.paid_at = now
    locked_invoice.save(update_fields=["status", "paid_at", "updated_at"])

    subscription.external_reference = locked_attempt.public_id
    subscription.save(update_fields=["external_reference", "updated_at"])

    return locked_attempt
