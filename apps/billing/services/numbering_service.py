"""شماره‌گذاریِ قطعیِ race-safe برایِ اسنادِ صورتحساب (ADR-74).

یکتایی از یک شمارنده‌ی ماندگار (``BillingSequence``) می‌آید که تحتِ
``select_for_update`` افزایش می‌یابد — هرگز از ``COUNT(*)`` جدول، که تحتِ
هم‌زمانی/retry شماره‌ی تکراری می‌سازد. شماره‌ها خواناست و تاریخی‌شان
تغییرناپذیر است (فیلدِ ``number`` پس از ساخت عوض نمی‌شود).

قالب‌ها:
- فاکتور:      ``INV-{YYYY}-{n:06d}``
- Credit Note: ``CN-{YYYY}-{n:06d}``
"""

from django.db import transaction
from django.utils import timezone

from apps.billing.models import BillingSequence

INVOICE_SEQUENCE_KEY = "subscription_invoice"
CREDIT_NOTE_SEQUENCE_KEY = "subscription_credit_note"


@transaction.atomic
def _next_value(key: str) -> int:
    """مقدارِ بعدیِ شمارنده‌ی ``key`` را race-safe برمی‌گرداند."""
    seq = BillingSequence.objects.select_for_update().filter(key=key).first()
    if seq is None:
        # ساختِ اولیه idempotent است (کلید یکتاست)؛ سپس قفل می‌گیریم.
        BillingSequence.objects.get_or_create(key=key)
        seq = BillingSequence.objects.select_for_update().get(key=key)
    seq.last_value = seq.last_value + 1
    seq.save(update_fields=["last_value", "updated_at"])
    return seq.last_value


def next_invoice_number(*, now=None) -> str:
    now = now or timezone.now()
    n = _next_value(INVOICE_SEQUENCE_KEY)
    return f"INV-{now:%Y}-{n:06d}"


def next_credit_note_number(*, now=None) -> str:
    now = now or timezone.now()
    n = _next_value(CREDIT_NOTE_SEQUENCE_KEY)
    return f"CN-{now:%Y}-{n:06d}"
