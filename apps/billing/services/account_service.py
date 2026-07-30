"""مدیریتِ ``StoreBillingAccount`` — یک حساب به‌ازایِ هر فروشگاه، idempotent،
Store-scoped. تغییرِ این حساب هرگز فاکتورِ گذشته را عوض نمی‌کند (فاکتورها
اسنپ‌شات می‌گیرند؛ ADR-73)."""

from django.core.exceptions import ValidationError
from django.db import transaction

from apps.billing.models import StoreBillingAccount
from apps.core.services.audit_service import record_audit_event

#: فیلدهایی که مرچنت مجاز به ویرایشِ آن‌هاست.
EDITABLE_FIELDS = (
    "legal_name", "billing_email", "billing_phone",
    "country", "region", "city", "postal_code", "address_line",
    "tax_identifier", "locale",
)


class BillingAccountError(Exception):
    """خطای قابل‌نمایش هنگام مدیریتِ حسابِ صورتحساب."""


def get_billing_account(store):
    """حسابِ صورتحسابِ این فروشگاه یا ``None``."""
    return StoreBillingAccount.objects.filter(store=store).first()


@transaction.atomic
def get_or_create_billing_account(store, *, currency=None):
    """حسابِ صورتحسابِ فروشگاه را برمی‌گرداند و اگر نبود یک حسابِ خالی می‌سازد
    (lazy provisioning) — ارز از پارامتر یا پیش‌فرضِ مدل تعیین می‌شود.
    idempotent."""
    account = StoreBillingAccount.objects.filter(store=store).select_for_update().first()
    if account is not None:
        return account
    defaults = {}
    if currency:
        defaults["currency"] = currency
    return StoreBillingAccount.objects.create(store=store, **defaults)


@transaction.atomic
def update_billing_account(store, *, actor=None, **fields):
    """فیلدهایِ مجازِ حسابِ صورتحساب را به‌روزرسانی می‌کند. ارز از این مسیر
    قابلِ تغییر نیست (ارزِ فاکتورهایِ جاری را نباید بی‌سروصدا عوض کرد)."""
    account = get_or_create_billing_account(store)
    before = account.snapshot()
    changed = {}
    for key, value in fields.items():
        if key not in EDITABLE_FIELDS:
            continue
        setattr(account, key, value if value is not None else "")
        changed[key] = getattr(account, key)
    try:
        account.full_clean()
    except ValidationError as exc:
        raise BillingAccountError("؛ ".join(sum(exc.message_dict.values(), []))) from exc
    account.save()
    record_audit_event(
        store=store, actor=actor, action_code="billing.account_updated",
        object_type="StoreBillingAccount", object_id=account.pk, object_label=account.legal_name or store.slug,
        before=before, after=account.snapshot(),
    )
    return account
