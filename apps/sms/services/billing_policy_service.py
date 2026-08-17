"""محاسبه قطعه/هزینه، رزرو اعتبار و ثبت لاگ‌های سطح پلتفرم."""

from dataclasses import dataclass
from math import ceil

from django.db import transaction
from django.utils import timezone

from ..models import SmsBalance, SmsBillingPolicy, SmsLog


@dataclass(frozen=True)
class SmsQuote:
    character_count: int
    billable_units: int
    unit_price_toman: int
    cost_toman: int


class InsufficientSmsCreditError(Exception):
    def __init__(self, *, balance: int, required: int, minimum_after: int):
        self.balance = balance
        self.required = required
        self.minimum_after = minimum_after
        super().__init__("اعتبار پیامک کافی نیست")


def quote_message(message: str, *, policy=None) -> SmsQuote:
    policy = policy or SmsBillingPolicy.load()
    chars = len(message or "")
    units = ceil(chars / policy.chars_per_credit) if chars else 0
    return SmsQuote(
        character_count=chars,
        billable_units=units,
        unit_price_toman=policy.price_per_credit_toman,
        cost_toman=units * policy.price_per_credit_toman,
    )


@transaction.atomic
def reserve_credits(*, store, units: int, is_otp: bool):
    """قبل از تماس شبکه اعتبار را اتمیک رزرو می‌کند؛ در شکست provider باید refund شود."""
    balance, _ = SmsBalance.objects.get_or_create(store=store)
    balance = SmsBalance.objects.select_for_update().get(pk=balance.pk)
    policy = SmsBillingPolicy.load()
    minimum_after = -policy.otp_overdraft_limit if is_otp else 0
    before = balance.credits
    after = before - units
    if after < minimum_after:
        raise InsufficientSmsCreditError(
            balance=before, required=units, minimum_after=minimum_after,
        )
    balance.credits = after
    balance.save(update_fields=["credits", "updated_at"])
    return before, after


@transaction.atomic
def refund_credits(*, store, units: int):
    if units <= 0:
        balance, _ = SmsBalance.objects.get_or_create(store=store)
        return balance.credits
    balance, _ = SmsBalance.objects.get_or_create(store=store)
    balance = SmsBalance.objects.select_for_update().get(pk=balance.pk)
    balance.credits += units
    balance.save(update_fields=["credits", "updated_at"])
    return balance.credits


def record_platform_attempt(*, event_key: str, recipient: str, message: str, result, protect_body: bool = False):
    quote = quote_message(message)
    success = bool(result.success)
    return SmsLog.objects.create(
        store=None, event_key=event_key, recipient=recipient,
        message="" if protect_body else message,
        status=SmsLog.Status.SENT if success else SmsLog.Status.FAILED,
        error_message="" if success else (result.error_message or ""),
        provider_ref_id=result.provider_ref_id or "",
        provider=getattr(result, "provider", "") or "",
        character_count=quote.character_count,
        billable_units=quote.billable_units,
        unit_price_toman=quote.unit_price_toman,
        cost_toman=quote.cost_toman if success else 0,
        attempt_count=1,
        sent_at=timezone.now() if success else None,
    )
