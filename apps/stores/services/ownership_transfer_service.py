"""انتقالِ مالکیتِ فروشگاه (Section 15) — دوطرفه، OTP-گیت برایِ هر دو طرف،
همیشه با انقضا و حسابرسی. مالکِ فعلی هرگز صرفِ کلیک عضویتش را از دست
نمی‌دهد — فقط پس از پذیرشِ واقعیِ طرفِ مقابل (OTPِ خودِ او، نه مالکِ فعلی)
اجرا می‌شود."""

from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from apps.core.services.audit_service import record_audit_event
from apps.portal.services.owner_auth_service import get_or_create_owner_by_phone
from apps.stores.models import Store, StoreMembership, StoreOwnershipTransfer

TRANSFER_TTL_DAYS = 3


class OwnershipTransferError(Exception):
    """خطای قابل‌نمایشِ آغاز/پذیرش/لغوِ انتقالِ مالکیت."""


@transaction.atomic
def initiate_transfer(*, store: Store, initiated_by, target_phone: str) -> StoreOwnershipTransfer:
    if StoreOwnershipTransfer.objects.filter(store=store, status=StoreOwnershipTransfer.Status.PENDING).exists():
        raise OwnershipTransferError("این فروشگاه از قبل یک انتقالِ مالکیتِ در-انتظار دارد.")

    from_membership = StoreMembership.objects.filter(
        store=store, user=initiated_by, role=StoreMembership.Role.OWNER,
        status=StoreMembership.MembershipStatus.ACTIVE,
    ).first()
    if from_membership is None:
        raise OwnershipTransferError("فقط مالکِ فعالِ فروشگاه می‌تواند انتقالِ مالکیت را آغاز کند.")

    if not (target_phone or "").strip():
        raise OwnershipTransferError("شماره‌ی موبایلِ مالکِ جدید الزامی است.")

    transfer = StoreOwnershipTransfer.objects.create(
        store=store, initiated_by=initiated_by, target_phone=target_phone,
        expires_at=timezone.now() + timedelta(days=TRANSFER_TTL_DAYS),
    )
    record_audit_event(
        store=store, actor=initiated_by, action_code="store.ownership_transfer_initiated",
        object_type="StoreOwnershipTransfer", object_id=transfer.pk, object_label=target_phone,
    )
    return transfer


def get_pending_transfer_by_token(token: str) -> StoreOwnershipTransfer | None:
    return StoreOwnershipTransfer.objects.select_related("store").filter(
        token=token, status=StoreOwnershipTransfer.Status.PENDING,
    ).first()


@transaction.atomic
def cancel_transfer(*, transfer: StoreOwnershipTransfer, actor) -> StoreOwnershipTransfer:
    locked = StoreOwnershipTransfer.objects.select_for_update().get(pk=transfer.pk)
    if locked.status != StoreOwnershipTransfer.Status.PENDING:
        raise OwnershipTransferError("این انتقال دیگر در-انتظار نیست.")
    locked.status = StoreOwnershipTransfer.Status.CANCELLED
    locked.cancelled_at = timezone.now()
    locked.save(update_fields=["status", "cancelled_at", "updated_at"])
    record_audit_event(
        store=locked.store, actor=actor, action_code="store.ownership_transfer_cancelled",
        object_type="StoreOwnershipTransfer", object_id=locked.pk, object_label=locked.target_phone,
    )
    return locked


def accept_transfer(*, transfer: StoreOwnershipTransfer) -> tuple[StoreOwnershipTransfer, "User"]:  # noqa: F821
    """طرفِ مقابل (که خودش با OTPِ شماره‌ی ``transfer.target_phone`` تأیید
    شده — این تابع فرض می‌کند تأییدِ OTP از قبل با موفقیت انجام شده) را
    مالکِ جدید می‌کند. مالکِ قبلی حذف نمی‌شود — نقشش به ``ADMINISTRATOR``
    تنزل می‌یابد تا همچنان عضوِ تیم بماند.

    ``expired`` عمداً *بیرونِ* بلوکِ atomicِ اصلی بررسی/raise می‌شود: اگر
    داخلِ همان تراکنش raise می‌کردیم، ثبتِ ``status=EXPIRED`` هم rollback
    می‌شد و انتقال برایِ همیشه در حالتِ نادرستِ «pending» می‌ماند."""
    new_owner = None
    old_owner_membership = None
    store = None

    with transaction.atomic():
        locked = StoreOwnershipTransfer.objects.select_for_update().get(pk=transfer.pk)
        if locked.status != StoreOwnershipTransfer.Status.PENDING:
            raise OwnershipTransferError("این انتقال دیگر در-انتظار نیست.")

        if locked.is_expired:
            locked.status = StoreOwnershipTransfer.Status.EXPIRED
            locked.save(update_fields=["status", "updated_at"])
        else:
            store = locked.store
            new_owner, _created = get_or_create_owner_by_phone(phone=locked.target_phone)

            old_owner_membership = StoreMembership.objects.select_for_update().filter(
                store=store, role=StoreMembership.Role.OWNER, status=StoreMembership.MembershipStatus.ACTIVE,
            ).first()
            if old_owner_membership is not None and old_owner_membership.user_id != new_owner.pk:
                old_owner_membership.role = StoreMembership.Role.ADMINISTRATOR
                old_owner_membership.save(update_fields=["role", "updated_at"])

            new_membership, created = StoreMembership.objects.get_or_create(
                store=store, user=new_owner,
                defaults={
                    "role": StoreMembership.Role.OWNER, "status": StoreMembership.MembershipStatus.ACTIVE,
                    "invited_by": locked.initiated_by, "accepted_at": timezone.now(),
                },
            )
            if not created:
                new_membership.role = StoreMembership.Role.OWNER
                new_membership.status = StoreMembership.MembershipStatus.ACTIVE
                if new_membership.accepted_at is None:
                    new_membership.accepted_at = timezone.now()
                new_membership.save(update_fields=["role", "status", "accepted_at", "updated_at"])

            locked.status = StoreOwnershipTransfer.Status.COMPLETED
            locked.completed_at = timezone.now()
            locked.save(update_fields=["status", "completed_at", "updated_at"])

    if locked.status == StoreOwnershipTransfer.Status.EXPIRED:
        raise OwnershipTransferError("این انتقال منقضی شده است.")

    record_audit_event(
        store=store, actor=new_owner, action_code="store.ownership_transfer_completed",
        object_type="StoreOwnershipTransfer", object_id=locked.pk, object_label=locked.target_phone,
        before={"previous_owner": old_owner_membership.user.username if old_owner_membership else None},
        after={"new_owner": new_owner.username},
    )
    _notify_transfer_completed(store=store, previous_owner_membership=old_owner_membership, new_owner=new_owner)
    return locked, new_owner


def _notify_transfer_completed(*, store: Store, previous_owner_membership, new_owner) -> None:
    from apps.notifications.services.notification_service import notify_security_event

    notify_security_event(
        subject="مالکیتِ فروشگاه منتقل شد",
        body=f"مالکیتِ فروشگاهِ «{store.name}» به مالکِ جدید منتقل شد.",
        user=new_owner, phone=new_owner.username, store=store,
    )
    if previous_owner_membership is not None:
        previous_owner = previous_owner_membership.user
        phone = getattr(getattr(previous_owner, "owner_profile", None), "phone", "")
        notify_security_event(
            subject="مالکیتِ فروشگاهِ شما منتقل شد",
            body=f"مالکیتِ فروشگاهِ «{store.name}» به مالکِ جدید منتقل شد؛ شما اکنون عضوِ تیم با نقشِ مدیر هستید.",
            user=previous_owner, phone=phone, store=store,
        )
