"""ثبتِ نهاییِ نامِ دائمیِ فروشگاه (Section 11؛ نامیده‌شده «Section J» در
تعریفِ ``normalize_platform_subdomain_label``) — چهارمین/آخرین مفهومِ متمایز
از چهارگانه‌ی §3.6-3.7: نامِ نمایشی (``Store.name``) ≠ نامِ دائمی (این
ماژول، یک ``StoreDomain`` با ``domain_type=PLATFORM_SUBDOMAIN``) ≠ میزبانِ
راستیسی (همینجاست، ``{handle}.{RASTISI_ADMIN_DOMAIN_SUFFIX}``) ≠ دامنه‌ی
اختصاصیِ اختیاری (Section 12، جدا).

قوانین:
* فقط یک‌بار قابلِ ثبت توسطِ خودِ تاجر — پس از آن غیرقابلِ تغییر (این
  ماژول است که این قاعده را اجرا می‌کند، نه فقط توضیحِ آن در مستندات).
* فقط برایِ اشتراکِ *پولی و فعال* مجاز است (نه تریال، نه بدونِ اشتراک) —
  مطابق §3.5 «پس از تأییدِ پرداخت».
* هاست‌نیمِ آزمایشی هرگز حذف نمی‌شود، فقط بازنشسته (retired_at) —
  دقیقاً همان سیاستِ ADR-101/103: دیگر هرگز تغییرمسیر نمی‌دهد و هرگز به
  فروشگاهِ دیگری واگذار نمی‌شود.
* Race-safe: یکتاییِ ``hostname`` یک قیدِ واقعیِ دیتابیس است
  (``StoreDomain.hostname``)، پس دو تلاشِ هم‌زمان برایِ یک لیبلِ یکسان،
  یکی موفق و دیگری با خطایِ روشن مواجه می‌شود — نه یک race که هر دو را
  «موفق» نشان دهد.
* تغییرِ نامِ دائمی پس از ثبت، فقط از طریقِ مسیرِ جداگانه‌ی
  ``rename_platform_handle_as_superuser`` ممکن است (فقط سوپریوزر، همیشه با
  دلیل، همیشه حسابرسی‌شده) — تا Platform Admin UI (Section 13) ساخته شود،
  این از طریقِ دستورِ مدیریتیِ ``rename_store_handle`` اجرا می‌شود، نه یک
  ویوی وب."""

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.core.services.audit_service import record_audit_event
from apps.stores.hostnames import normalize_platform_subdomain_label
from apps.stores.models import Store, StoreDomain


class HandleError(Exception):
    """خطای قابل‌نمایشِ ثبت/تغییرِ نامِ دائمیِ فروشگاه."""


def _normalize_label_or_raise(label: str) -> str:
    try:
        return normalize_platform_subdomain_label(label)
    except ValidationError as exc:
        raise HandleError("؛ ".join(exc.messages)) from exc


def has_claimed_handle(store: Store) -> bool:
    return StoreDomain.objects.filter(store=store, domain_type=StoreDomain.DomainType.PLATFORM_SUBDOMAIN).exists()


def _require_paid_active_subscription(store: Store) -> None:
    from apps.subscriptions.models import StoreSubscription

    subscription = StoreSubscription.objects.filter(store=store, is_current=True).first()
    if subscription is None or subscription.status != StoreSubscription.Status.ACTIVE:
        raise HandleError(
            "ثبتِ نامِ دائمیِ فروشگاه فقط پس از تأییدِ پرداخت و فعال‌شدنِ اشتراک ممکن است."
        )


@transaction.atomic
def claim_platform_handle(*, store: Store, label: str, actor) -> StoreDomain:
    """اولین و تنها فرصتِ تاجر برایِ ثبتِ نامِ دائمیِ فروشگاه."""
    if has_claimed_handle(store):
        raise HandleError("این فروشگاه از قبل یک نامِ دائمی ثبت کرده؛ نامِ دائمی پس از ثبت غیرقابلِ تغییر است.")

    _require_paid_active_subscription(store)
    normalized_label = _normalize_label_or_raise(label)

    from django.conf import settings

    hostname = f"{normalized_label}.{settings.RASTISI_ADMIN_DOMAIN_SUFFIX}"

    locked_store = Store.objects.select_for_update().get(pk=store.pk)
    old_primary = StoreDomain.objects.select_for_update().filter(store=locked_store, is_primary=True).first()
    if old_primary is not None:
        old_primary.is_primary = False
        old_primary.retired_at = timezone.now()
        old_primary.save(update_fields=["is_primary", "retired_at", "updated_at"])

    try:
        new_domain = StoreDomain.objects.create(
            store=locked_store, hostname=hostname, is_primary=True,
            domain_type=StoreDomain.DomainType.PLATFORM_SUBDOMAIN,
            verification_status=StoreDomain.VerificationStatus.VERIFIED, verified_at=timezone.now(),
        )
    except IntegrityError as exc:
        raise HandleError(f"نامِ «{normalized_label}» قبلاً توسطِ فروشگاهِ دیگری ثبت شده است.") from exc

    record_audit_event(
        store=locked_store, actor=actor, action_code="store.handle_claimed",
        object_type="StoreDomain", object_id=new_domain.pk, object_label=hostname,
        before={"old_hostname": old_primary.hostname if old_primary else None},
        after={"hostname": hostname},
    )
    _notify_handle_claimed(store=locked_store, actor=actor, hostname=hostname)
    return new_domain


def _notify_handle_claimed(*, store: Store, actor, hostname: str) -> None:
    from apps.notifications.services.notification_service import notify_security_event

    phone = getattr(getattr(actor, "owner_profile", None), "phone", "")
    notify_security_event(
        subject="نامِ دائمیِ فروشگاه ثبت شد",
        body=f"نامِ دائمیِ فروشگاهِ «{store.name}» روی {hostname} ثبت شد. این نام غیرقابلِ تغییر است.",
        user=actor, phone=phone, store=store,
    )


@transaction.atomic
def rename_platform_handle_as_superuser(*, store: Store, new_label: str, actor, reason: str) -> StoreDomain:
    """تغییرِ نامِ دائمی — فقط ابزارِ مدیرِ پلتفرم (نگاه کنید به ``rename_
    store_handle`` command)؛ برخلافِ ``claim_platform_handle``، محدودیتِ
    «فقط یک‌بار» یا الزامِ اشتراکِ فعال را اعمال نمی‌کند — تصمیمِ اداری است."""
    if not (reason or "").strip():
        raise HandleError("تغییرِ نامِ دائمی همیشه باید همراه با دلیل ثبت شود.")

    normalized_label = _normalize_label_or_raise(new_label)
    from django.conf import settings

    hostname = f"{normalized_label}.{settings.RASTISI_ADMIN_DOMAIN_SUFFIX}"

    locked_store = Store.objects.select_for_update().get(pk=store.pk)
    old_primary = StoreDomain.objects.select_for_update().filter(
        store=locked_store, domain_type=StoreDomain.DomainType.PLATFORM_SUBDOMAIN, is_primary=True,
    ).first()
    if old_primary is None:
        raise HandleError("این فروشگاه هنوز نامِ دائمی ثبت نکرده؛ برای ثبتِ اول از مسیرِ تاجر استفاده کنید.")

    old_primary.is_primary = False
    old_primary.retired_at = timezone.now()
    old_primary.save(update_fields=["is_primary", "retired_at", "updated_at"])

    try:
        new_domain = StoreDomain.objects.create(
            store=locked_store, hostname=hostname, is_primary=True,
            domain_type=StoreDomain.DomainType.PLATFORM_SUBDOMAIN,
            verification_status=StoreDomain.VerificationStatus.VERIFIED, verified_at=timezone.now(),
        )
    except IntegrityError as exc:
        raise HandleError(f"نامِ «{normalized_label}» قبلاً توسطِ فروشگاهِ دیگری ثبت شده است.") from exc

    record_audit_event(
        store=locked_store, actor=actor, action_code="store.handle_renamed_by_superuser",
        object_type="StoreDomain", object_id=new_domain.pk, object_label=hostname,
        before={"old_hostname": old_primary.hostname}, after={"hostname": hostname},
        metadata={"reason": reason},
    )
    return new_domain
