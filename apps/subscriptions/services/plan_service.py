"""سرویسِ مدیریتِ پلن و نسخه‌ی پلن — انتشار/بازنشستگی و اجرایِ تغییرناپذیریِ
نسخه‌ی منتشرشده (ADR-63). این عملیات platform-level هستند و از Django Admin
یا تست فراخوانی می‌شوند؛ هیچ مسیرِ Merchant به این‌جا نمی‌رسد."""

from django.db import transaction
from django.utils import timezone

from apps.subscriptions.models import EntitlementDefinition, PlanEntitlement, PlanVersion

# ``actor`` روی امضایِ توابع نگه داشته شده تا وقتی یک Audit Logِ پلتفرمی
# اضافه شد بدونِ تغییرِ فراخوان‌ها وصل شود؛ عملیاتِ platform-level فعلاً از
# طریقِ Django Admin's own LogEntry ردیابی می‌شوند.


class PlanServiceError(Exception):
    """خطای قابل‌نمایشِ عملیاتِ پلن — انتشارِ نامعتبر، ویرایشِ نسخه‌ی منتشرشده و... ."""


@transaction.atomic
def create_plan_version(plan, **fields) -> PlanVersion:
    """نسخه‌ی پیش‌نویسِ تازه‌ای می‌سازد؛ ``version_number`` را خودکار (یکی
    بیشتر از بیشترین نسخه‌ی موجودِ همان پلن) تعیین می‌کند مگر صراحتاً داده
    شود."""
    if "version_number" not in fields:
        last = plan.versions.order_by("-version_number").values_list("version_number", flat=True).first()
        fields["version_number"] = (last or 0) + 1
    fields.setdefault("status", PlanVersion.Status.DRAFT)
    return PlanVersion.objects.create(plan=plan, **fields)


@transaction.atomic
def set_plan_entitlement(plan_version, entitlement_key, **values) -> PlanEntitlement:
    """یک ``PlanEntitlement`` را رویِ یک نسخه‌ی *پیش‌نویس* تنظیم/به‌روزرسانی
    می‌کند — نسخه‌ی منتشرشده تغییرناپذیر است (ADR-63). وضعیت همیشه تازه از
    دیتابیس خوانده می‌شود، نه از instanceِ احتمالاً کهنه‌ی حافظه."""
    current_status = PlanVersion.objects.filter(pk=plan_version.pk).values_list("status", flat=True).first()
    if current_status != PlanVersion.Status.DRAFT:
        raise PlanServiceError("فقط نسخه‌ی «پیش‌نویس» قابلِ ویرایشِ Entitlement است.")
    entitlement = EntitlementDefinition.objects.filter(key=entitlement_key).first()
    if entitlement is None:
        raise PlanServiceError(f"تعریفِ حق‌دسترسیِ «{entitlement_key}» وجود ندارد.")
    obj, _created = PlanEntitlement.objects.update_or_create(
        plan_version=plan_version, entitlement=entitlement, defaults=values,
    )
    obj.full_clean()
    obj.save()
    return obj


@transaction.atomic
def publish_plan_version(plan_version, *, actor=None) -> PlanVersion:
    """نسخه‌ی پیش‌نویس را منتشر می‌کند — پس از این، شرایطِ آن تغییرناپذیر
    می‌شود (ADR-63). idempotent: انتشارِ دوباره‌ی یک نسخه‌ی از پیش منتشرشده
    بی‌اثر است."""
    locked = PlanVersion.objects.select_for_update().get(pk=plan_version.pk)
    if locked.status == PlanVersion.Status.PUBLISHED:
        return locked
    if locked.status != PlanVersion.Status.DRAFT:
        raise PlanServiceError("فقط نسخه‌ی «پیش‌نویس» قابلِ انتشار است.")
    locked.status = PlanVersion.Status.PUBLISHED
    locked.published_at = timezone.now()
    if locked.effective_from is None:
        locked.effective_from = locked.published_at
    locked.save(update_fields=["status", "published_at", "effective_from", "updated_at"])
    return locked


@transaction.atomic
def retire_plan_version(plan_version, *, actor=None) -> PlanVersion:
    """نسخه‌ی منتشرشده را بازنشسته می‌کند — اشتراک‌هایِ موجود روی این نسخه
    دست‌نخورده می‌مانند (ADR-63)؛ فقط اشتراکِ *تازه* دیگر نمی‌گیرد."""
    locked = PlanVersion.objects.select_for_update().get(pk=plan_version.pk)
    if locked.status == PlanVersion.Status.RETIRED:
        return locked
    if locked.status != PlanVersion.Status.PUBLISHED:
        raise PlanServiceError("فقط نسخه‌ی «منتشرشده» قابلِ بازنشستگی است.")
    locked.status = PlanVersion.Status.RETIRED
    locked.retired_at = timezone.now()
    locked.save(update_fields=["status", "retired_at", "updated_at"])
    return locked
