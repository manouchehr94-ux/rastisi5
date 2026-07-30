"""Providerِ «دستی/تستی» — پیاده‌سازیِ اولِ صادقانه (ADR-75).

این Provider هیچ پرداختِ واقعی را خودکار *نمی‌کند* و هرگز موفقیت را جعل
نمی‌کند: جلسه‌ی پرداخت کاربر را به یک صفحه‌ی راهنمایِ پرداختِ داخلی می‌برد، و
تأییدِ پرداخت فقط از راهِ یک Webhookِ امضاشده (HMAC-SHA256) یا اقدامِ صریحِ
مدیرِ پلتفرم انجام می‌شود. برایِ اتصالِ یک درگاهِ تولیدیِ واقعی، یک Provider
تازه پشتِ همین رابط اضافه می‌شود؛ این کلاس دست‌نخورده می‌ماند.

امضایِ Webhook: ``hex(hmac_sha256(secret, f"{timestamp}.{body}"))`` در هدرِ
``X-Billing-Signature``، همراهِ ``X-Billing-Timestamp`` (unix). تأیید:
تحملِ زمانی + مقایسه‌ی زمان-ثابت.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from decimal import Decimal, InvalidOperation

from apps.billing.providers.base import (
    BillingPaymentProvider,
    PaymentSessionResult,
    PaymentStatusResult,
    ProviderResponseError,
    RefundResult,
    WebhookEventData,
    WebhookVerificationError,
)

SIGNATURE_HEADER = "X-Billing-Signature"
TIMESTAMP_HEADER = "X-Billing-Timestamp"
DEFAULT_TOLERANCE_SECONDS = 300


class ManualProvider(BillingPaymentProvider):
    code = "manual"
    supports_automatic_capture = False

    def __init__(self, *, tolerance_seconds: int = DEFAULT_TOLERANCE_SECONDS):
        self.tolerance_seconds = tolerance_seconds

    def create_payment_session(self, *, attempt, invoice, return_url: str) -> PaymentSessionResult:
        # هیچ تماسِ خارجی؛ session_id یک شناسه‌ی داخلیِ پایدار است و redirect به
        # صفحه‌ی راهنمایِ پرداختِ داخلی می‌رود (نه یک موفقیتِ جعلی).
        session_id = f"manual-sess-{attempt.public_token}"
        return PaymentSessionResult(
            session_id=session_id,
            redirect_url=return_url,
            extra={"manual": True, "invoice_number": invoice.number},
        )

    @staticmethod
    def _expected_signature(secret: str, timestamp: str, body: bytes) -> str:
        message = timestamp.encode("utf-8") + b"." + body
        return hmac.new(secret.encode("utf-8"), message, hashlib.sha256).hexdigest()

    def verify_webhook(self, *, headers: dict, body: bytes, secret: str) -> bool:
        if not secret:
            raise WebhookVerificationError("رازِ Webhook پیکربندی نشده است.", code="no_secret")
        # هدرها case-insensitive خوانده می‌شوند.
        lowered = {str(k).lower(): v for k, v in headers.items()}
        signature = lowered.get(SIGNATURE_HEADER.lower())
        timestamp = lowered.get(TIMESTAMP_HEADER.lower())
        if not signature or not timestamp:
            raise WebhookVerificationError("امضا یا زمانِ Webhook موجود نیست.", code="missing")
        try:
            ts = int(timestamp)
        except (TypeError, ValueError) as exc:
            raise WebhookVerificationError("زمانِ Webhook نامعتبر است.", code="bad_timestamp") from exc
        if abs(time.time() - ts) > self.tolerance_seconds:
            raise WebhookVerificationError("زمانِ Webhook خارج از تحملِ مجاز است.", code="expired")
        expected = self._expected_signature(secret, timestamp, body)
        if not hmac.compare_digest(expected, str(signature)):
            raise WebhookVerificationError("امضایِ Webhook نامعتبر است.", code="bad_signature")
        return True

    def parse_webhook_event(self, *, body: bytes) -> WebhookEventData:
        try:
            payload = json.loads(body.decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as exc:
            raise ProviderResponseError("بدنه‌ی Webhook JSONِ معتبر نیست.", code="bad_json") from exc
        if not isinstance(payload, dict):
            raise ProviderResponseError("بدنه‌ی Webhook باید یک شیء JSON باشد.", code="bad_shape")
        amount = None
        if payload.get("amount") not in (None, ""):
            try:
                amount = Decimal(str(payload["amount"]))
            except (InvalidOperation, ValueError) as exc:
                raise ProviderResponseError("مبلغِ Webhook نامعتبر است.", code="bad_amount") from exc
        event_type = str(payload.get("event_type", ""))
        return WebhookEventData(
            event_id=str(payload.get("event_id", "")),
            event_type=event_type,
            provider_payment_id=str(payload.get("provider_payment_id", "")),
            amount=amount,
            currency=str(payload.get("currency", "")),
            succeeded=event_type == "payment.succeeded",
            raw_summary={"event_type": event_type},
        )

    def fetch_payment_status(self, *, provider_payment_id: str) -> PaymentStatusResult:
        # Providerِ دستی چیزی برایِ استعلامِ server-side ندارد — صادقانه
        # «تأییدنشده» برمی‌گرداند.
        return PaymentStatusResult(provider_payment_id=provider_payment_id, succeeded=False)

    def refund_payment(self, *, provider_payment_id: str, amount: Decimal, currency: str,
                       idempotency_key: str) -> RefundResult:
        # بازپرداختِ دستی خودکار نیست — به‌عنوانِ «ثبت‌شده، نیازمندِ پردازشِ
        # دستی» برمی‌گردد؛ تکمیلِ واقعی با اقدامِ صریحِ مدیر انجام می‌شود.
        return RefundResult(
            provider_refund_id=f"manual-refund-{idempotency_key}",
            succeeded=False,
            raw_summary={"manual": True},
        )
