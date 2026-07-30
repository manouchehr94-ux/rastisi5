"""Viewهایِ عمومیِ صورتحساب — فقط endpointِ Webhook (ADR-76).

این تنها مسیرِ صورتحساب است که CSRF ندارد (Webhookهایِ Provider نمی‌توانند
توکنِ CSRF بفرستند)؛ در عوض با امضایِ Provider تأیید می‌شوند. هیچ مسیرِ دیگری
از این معافیت استفاده نمی‌کند. Viewهایِ Merchant Billing در
``apps.dashboard`` هستند (commit 10)."""

import logging

from django.http import HttpResponse, HttpResponseBadRequest
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from apps.billing.providers.base import BillingProviderError, WebhookVerificationError
from apps.billing.services import payment_flow_service, webhook_service

logger = logging.getLogger("billing")


@csrf_exempt
@require_POST
def billing_webhook(request, provider_code):
    """Webhookِ خام را می‌پذیرد، امضا را تأیید و رخداد را در صندوقِ ورودی ذخیره
    می‌کند. هرگز از پارامترهایِ query یا احرازِ نشست استفاده نمی‌کند."""
    content_type = (request.content_type or "").lower()
    if "json" not in content_type:
        return HttpResponseBadRequest("Content-Type نامعتبر است.")

    body = request.body  # bytes خام برایِ بررسیِ امضا
    try:
        event = webhook_service.ingest_webhook(
            provider_code=provider_code, headers=dict(request.headers), body=body,
        )
    except webhook_service.WebhookTooLarge:
        return HttpResponse("payload بیش از حد بزرگ است.", status=413)
    except WebhookVerificationError:
        # امضا/زمانِ نامعتبر — هیچ تغییری در دامنه؛ ۴۰۰ بدونِ افشایِ جزئیات.
        return HttpResponseBadRequest("تأییدِ Webhook ناموفق بود.")
    except BillingProviderError:
        return HttpResponseBadRequest("رخدادِ Webhook نامعتبر است.")

    # پردازشِ تأییدِ پرداخت به‌صورتِ جدا و امن انجام می‌شود؛ خطایِ کسب‌وکاری رویِ
    # خودِ رخداد ثبت و برایِ Retryِ مدیر در دسترس می‌ماند — پس همیشه ۲۰۰
    # برمی‌گردانیم تا Provider بی‌مورد Retry نکند.
    try:
        payment_flow_service.process_webhook_event(event)
    except Exception:  # noqa: BLE001 — خطا رویِ رخداد ثبت می‌شود، پاسخ ۲۰۰ می‌ماند
        logger.exception("webhook processing failed for event %s", event.pk)
    return HttpResponse("ok", status=200)
