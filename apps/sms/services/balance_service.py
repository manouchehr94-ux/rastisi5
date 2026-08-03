"""اعتبارِ پیامکِ Store و خریدِ بسته — لایه‌ی سرویسِ ``SmsBalance``/
``SmsPackage``/``SmsPackagePurchase`` (نگاه کنید به داکیومنتِ آن مدل‌ها
برای سیاستِ کاملِ کسر/تکمیل)."""

from django.db import transaction
from django.db.models import F
from django.utils import timezone

from ..models import SmsBalance, SmsCreditAdjustment, SmsPackage, SmsPackagePurchase


def get_or_create_balance(*, store) -> SmsBalance:
    balance, _created = SmsBalance.objects.get_or_create(store=store)
    return balance


def deduct_credit(*, store) -> None:
    """یک واحد از اعتبارِ Store کم می‌کند — صرفاً برایِ گزارش‌دهی/شفافیت.

    TODO: این تابع فعلاً ارسال را روی اعتبارِ صفر/منفی مسدود نمی‌کند —
    مسدودسازیِ واقعیِ ارسال روی نبودِ اعتبار یک تصمیمِ محصولی است که باید
    جداگانه گرفته شود (ریسکِ قفل‌شدنِ OTP ورودِ مشتریان اگر بدونِ برنامه‌ی
    شارژِ خودکار/هشدارِ زودهنگام فعال شود)."""
    get_or_create_balance(store=store)
    SmsBalance.objects.filter(store=store).update(credits=F("credits") - 1)


class InvalidAdjustmentError(Exception):
    """اصلاحِ درخواست‌شده معتبر نیست (مثلاً بدونِ دلیل یا تغییرِ صفر)."""


@transaction.atomic
def adjust_credit(*, store, delta: int, reason: str, note: str = "", actor=None) -> SmsCreditAdjustment:
    """اعتبارِ Store را به‌صورتِ دستی تغییر می‌دهد و یک ردیفِ دفترِ اصلاح
    (``SmsCreditAdjustment``) با مقدارِ قبل/تغییر/بعد ثبت می‌کند — تنها راهِ
    مجازِ Platform Admin برایِ تغییرِ اعتبار، هرگز نوشتنِ مستقیمِ فیلد."""
    if delta == 0:
        raise InvalidAdjustmentError("مقدارِ تغییر نمی‌تواند صفر باشد.")
    if not reason.strip():
        raise InvalidAdjustmentError("دلیلِ اصلاح الزامی است.")

    balance = SmsBalance.objects.select_for_update().filter(store=store).first()
    if balance is None:
        balance = get_or_create_balance(store=store)
        balance = SmsBalance.objects.select_for_update().get(pk=balance.pk)

    before = balance.credits
    after = before + delta
    balance.credits = after
    balance.save(update_fields=["credits", "updated_at"])

    return SmsCreditAdjustment.objects.create(
        store=store, actor=actor, delta=delta, balance_before=before, balance_after=after,
        reason=reason.strip(), note=note.strip(),
    )


def list_active_packages():
    return SmsPackage.objects.filter(is_active=True).order_by("display_order", "credit_amount")


def request_purchase(*, store, package: SmsPackage) -> SmsPackagePurchase:
    """درخواستِ خریدِ یک بسته را با وضعیتِ ``pending`` ثبت می‌کند — اعتباری
    فوراً افزوده نمی‌شود (نگاه کنید به ``SmsPackagePurchase`` docstring)."""
    return SmsPackagePurchase.objects.create(
        store=store, package=package,
        credit_amount=package.credit_amount, price=package.price,
    )


class PurchaseNotPendingError(Exception):
    """فقط خریدهای در وضعیتِ pending قابلِ تکمیل/لغو هستند."""


@transaction.atomic
def complete_purchase(*, purchase: SmsPackagePurchase) -> SmsPackagePurchase:
    """فقط از مسیرِ Platform Admin — پرداخت را تکمیل‌شده علامت می‌زند و
    اعتبارِ بسته را به Store اضافه می‌کند (یک‌بار، idempotent با قفلِ ردیف)."""
    locked = SmsPackagePurchase.objects.select_for_update().get(pk=purchase.pk)
    if locked.status != SmsPackagePurchase.Status.PENDING:
        raise PurchaseNotPendingError("این خرید در وضعیتِ در انتظار نیست")

    balance = get_or_create_balance(store=locked.store)
    SmsBalance.objects.filter(pk=balance.pk).update(credits=balance.credits + locked.credit_amount)

    locked.status = SmsPackagePurchase.Status.COMPLETED
    locked.completed_at = timezone.now()
    locked.save(update_fields=["status", "completed_at", "updated_at"])
    return locked


@transaction.atomic
def cancel_purchase(*, purchase: SmsPackagePurchase) -> SmsPackagePurchase:
    locked = SmsPackagePurchase.objects.select_for_update().get(pk=purchase.pk)
    if locked.status != SmsPackagePurchase.Status.PENDING:
        raise PurchaseNotPendingError("این خرید در وضعیتِ در انتظار نیست")
    locked.status = SmsPackagePurchase.Status.CANCELED
    locked.save(update_fields=["status", "updated_at"])
    return locked
