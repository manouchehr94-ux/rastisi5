"""سرویسِ CRM مشتریِ Store-scoped — پروفایل، یادداشت، برچسب (checkpoint 4 §14-16).

هیچ تابعی در این ماژول هرگز یک ``CustomerProfile``/``CustomerTag`` را بدونِ
فیلترِ صریحِ ``store=store`` جست‌وجو نمی‌کند — دقیقاً همان قاعده‌ی
``catalog_admin_service`` برای اکشن‌های فله‌ای. آمارِ کش‌شده‌ی پروفایل
(``order_count``/``total_spent``/...) تنها با فراخوانیِ صریحِ
``refresh_customer_profile_stats`` به‌روز می‌شود، هرگز با signal — نگاه کنید
به ADR-50 و مستندسازیِ ``CustomerProfile`` در ``apps/customers/models.py``.
"""

from django.db.models import Max, Min, Q, Sum
from django.utils import timezone

from apps.core.services.audit_service import record_audit_event
from apps.customers.models import Customer, CustomerNote, CustomerProfile, CustomerTag
from apps.orders.models import Order


class CustomerCrmError(Exception):
    """خطای قابل‌نمایشِ مستقیم به کاربر — برچسب/پروفایلِ نامعتبر یا متعلق به Store دیگر."""


def get_or_create_profile(store, customer: Customer) -> CustomerProfile:
    profile, _ = CustomerProfile.objects.get_or_create(store=store, customer=customer)
    return profile


def refresh_customer_profile_stats(profile: CustomerProfile) -> CustomerProfile:
    """آمارِ کش‌شده‌ی پروفایل را از رویِ Orderهای واقعیِ همین Store (نه فیلدهای
    سراسریِ ``Customer``) دوباره محاسبه می‌کند — نگاه کنید به ADR-50."""
    aggregates = Order.objects.filter(store=profile.store, customer=profile.customer).aggregate(
        paid_total=Sum("grand_total", filter=Q(payment_status=Order.PaymentStatus.PAID)),
        first_at=Min("created_at"),
        last_at=Max("created_at"),
    )
    order_count = Order.objects.filter(store=profile.store, customer=profile.customer).count()
    profile.order_count = order_count
    profile.total_spent = aggregates["paid_total"] or 0
    profile.first_order_at = aggregates["first_at"]
    profile.last_order_at = aggregates["last_at"]
    profile.stats_refreshed_at = timezone.now()
    profile.save(update_fields=[
        "order_count", "total_spent", "first_order_at", "last_order_at", "stats_refreshed_at",
    ])
    return profile


# ---------------------------------------------------------------- یادداشت‌ها

def add_note(profile: CustomerProfile, *, author, body: str, is_pinned: bool = False) -> CustomerNote:
    note = CustomerNote.objects.create(profile=profile, author=author, body=body, is_pinned=is_pinned)
    record_audit_event(
        store=profile.store, actor=author, action_code="customer_note.created",
        object_type="CustomerNote", object_id=str(note.pk),
        object_label=f"یادداشت برای {profile.customer.full_name}",
    )
    return note


def update_note(note: CustomerNote, *, actor, body: str | None = None, is_pinned: bool | None = None) -> CustomerNote:
    changed_fields = []
    if body is not None:
        note.body = body
        changed_fields.append("body")
    if is_pinned is not None:
        note.is_pinned = is_pinned
        changed_fields.append("is_pinned")
    if changed_fields:
        note.save(update_fields=changed_fields)
    record_audit_event(
        store=note.profile.store, actor=actor, action_code="customer_note.updated",
        object_type="CustomerNote", object_id=str(note.pk),
        object_label=f"یادداشت برای {note.profile.customer.full_name}",
    )
    return note


def delete_note(note: CustomerNote, *, actor) -> None:
    store = note.profile.store
    label = f"یادداشت برای {note.profile.customer.full_name}"
    note_id = note.pk
    note.delete()
    record_audit_event(
        store=store, actor=actor, action_code="customer_note.deleted",
        object_type="CustomerNote", object_id=str(note_id), object_label=label,
    )


# ---------------------------------------------------------------- برچسب‌ها

def create_tag(store, *, name: str, code: str, description: str = "", color: str = "", actor=None) -> CustomerTag:
    if CustomerTag.objects.filter(store=store, code=code).exists():
        raise CustomerCrmError(f"برچسبی با کدِ «{code}» از قبل وجود دارد.")
    tag = CustomerTag.objects.create(store=store, name=name, code=code, description=description, color=color)
    record_audit_event(
        store=store, actor=actor, action_code="customer_tag.created",
        object_type="CustomerTag", object_id=str(tag.pk), object_label=tag.name,
    )
    return tag


def archive_tag(store, tag_id, *, actor=None) -> CustomerTag:
    """برچسب را غیرفعال می‌کند — هرگز حذفِ فیزیکی، چون ممکن است به پروفایل‌هایی
    متصل باشد (نگاه کنید به مستندسازیِ ``CustomerTag`` در models.py)."""
    tag = CustomerTag.objects.filter(store=store, pk=tag_id).first()
    if tag is None:
        raise CustomerCrmError("برچسبِ انتخاب‌شده معتبر نیست.")
    tag.is_active = False
    tag.save(update_fields=["is_active"])
    record_audit_event(
        store=store, actor=actor, action_code="customer_tag.archived",
        object_type="CustomerTag", object_id=str(tag.pk), object_label=tag.name,
    )
    return tag


def bulk_add_tag(store, customer_ids, tag_id, *, actor=None) -> int:
    """برچسبِ ``tag_id`` (متعلق به همین Store) را به پروفایلِ Store-scopedِ
    هر مشتری در ``customer_ids`` اضافه می‌کند — شناسه‌های مشتریِ فروشگاهِ
    دیگر بی‌صدا نادیده گرفته می‌شوند (هرگز پروفایلی در Store دیگر ساخته
    نمی‌شود)."""
    tag = CustomerTag.objects.filter(store=store, pk=tag_id, is_active=True).first()
    if tag is None:
        raise CustomerCrmError("برچسبِ انتخاب‌شده معتبر نیست.")

    customers = Customer.objects.filter(pk__in=customer_ids, orders__store=store).distinct()
    count = 0
    for customer in customers:
        profile = get_or_create_profile(store, customer)
        profile.tags.add(tag)
        count += 1
    if count:
        record_audit_event(
            store=store, actor=actor, action_code="customer.bulk_tag_added",
            object_type="CustomerProfile", object_id="bulk",
            object_label=f"{count} مشتری — برچسبِ «{tag.name}»",
            metadata={"customer_ids": list(customers.values_list("pk", flat=True))[:200], "tag_id": tag.pk},
        )
    return count


def bulk_remove_tag(store, customer_ids, tag_id, *, actor=None) -> int:
    tag = CustomerTag.objects.filter(store=store, pk=tag_id).first()
    if tag is None:
        raise CustomerCrmError("برچسبِ انتخاب‌شده معتبر نیست.")

    profiles = CustomerProfile.objects.filter(store=store, customer_id__in=customer_ids, tags=tag)
    count = profiles.count()
    for profile in profiles:
        profile.tags.remove(tag)
    if count:
        record_audit_event(
            store=store, actor=actor, action_code="customer.bulk_tag_removed",
            object_type="CustomerProfile", object_id="bulk",
            object_label=f"{count} مشتری — حذفِ برچسبِ «{tag.name}»",
            metadata={"customer_ids": list(profiles.values_list("customer_id", flat=True))[:200], "tag_id": tag.pk},
        )
    return count


def set_internal_status(store, customer_ids, status: str, *, actor=None) -> int:
    if status not in CustomerProfile.InternalStatus.values:
        raise CustomerCrmError(f"وضعیتِ داخلیِ «{status}» نامعتبر است.")
    customers = Customer.objects.filter(pk__in=customer_ids, orders__store=store).distinct()
    count = 0
    for customer in customers:
        profile = get_or_create_profile(store, customer)
        profile.internal_status = status
        profile.save(update_fields=["internal_status"])
        count += 1
    if count:
        record_audit_event(
            store=store, actor=actor, action_code="customer.bulk_status_changed",
            object_type="CustomerProfile", object_id="bulk",
            object_label=f"{count} مشتری — وضعیتِ «{status}»",
            metadata={"customer_ids": list(customers.values_list("pk", flat=True))[:200], "status": status},
        )
    return count
