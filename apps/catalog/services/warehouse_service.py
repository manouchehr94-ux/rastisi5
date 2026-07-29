"""مدیریتِ انبار — ایجاد، ویرایش، آرشیو، تعیینِ انبارِ پیش‌فرض.

نگاه کنید به ADR-37 در ``SAAS_DOMAIN_DECISIONS.md``. ``provision_default_warehouse``
دقیقاً همان الگوی ``ShopSettings.provision_for``/``FooterSettings.provision_for``
را دنبال می‌کند: یک قدمِ صریح و idempotent، نه اثرِ جانبیِ خاموشِ ساختن/
خواندنِ Store — این کدبیس هیچ‌جا از signal برای provisioning استفاده
نمی‌کند، پس اینجا هم نباید استثنا باشد.
"""

from django.core.exceptions import ValidationError
from django.db import transaction

from apps.catalog.models import Warehouse

DEFAULT_WAREHOUSE_CODE = "main"


class WarehouseError(Exception):
    """خطای قابل‌نمایش هنگام مدیریتِ انبار."""


@transaction.atomic
def provision_default_warehouse(store) -> Warehouse:
    """اگر این Store هنوز انبارِ پیش‌فرض ندارد، یکی می‌سازد؛ در غیر این صورت
    همان انبارِ پیش‌فرضِ موجود را بدونِ تغییر برمی‌گرداند (idempotent)."""
    existing = Warehouse.objects.filter(store=store, is_default=True).first()
    if existing is not None:
        return existing

    warehouse, _ = Warehouse.objects.get_or_create(
        store=store, code=DEFAULT_WAREHOUSE_CODE,
        defaults={"name": "انبار اصلی", "is_default": True, "is_active": True},
    )
    if not warehouse.is_default:
        warehouse.is_default = True
        warehouse.save(update_fields=["is_default", "updated_at"])
    return warehouse


def list_warehouses(store):
    return Warehouse.objects.filter(store=store).order_by("fulfillment_priority", "name")


@transaction.atomic
def create_warehouse(store, *, actor=None, **fields) -> Warehouse:
    # قیدِ دیتابیس "دقیقاً یک انبارِ پیش‌فرض" فوری بررسی می‌شود (نه در پایانِ
    # تراکنش)، پس انبارِ پیش‌فرضِ قبلی باید پیش از ذخیره‌ی انبارِ تازه پاک شود.
    if fields.get("is_default"):
        _clear_other_defaults(store, keep=None)
    warehouse = Warehouse(store=store, **fields)
    try:
        warehouse.full_clean()
    except ValidationError as exc:
        raise WarehouseError("؛ ".join(sum(exc.message_dict.values(), []))) from exc
    warehouse.save()
    from apps.core.services.audit_service import record_audit_event
    record_audit_event(
        store=store, actor=actor, action_code="warehouse.created",
        object_type="Warehouse", object_id=warehouse.pk, object_label=warehouse.name,
    )
    return warehouse


@transaction.atomic
def update_warehouse(warehouse: Warehouse, *, actor=None, **fields) -> Warehouse:
    if fields.get("is_default"):
        _clear_other_defaults(warehouse.store, keep=warehouse)
    for key, value in fields.items():
        setattr(warehouse, key, value)
    try:
        warehouse.full_clean()
    except ValidationError as exc:
        raise WarehouseError("؛ ".join(sum(exc.message_dict.values(), []))) from exc
    warehouse.save()
    from apps.core.services.audit_service import record_audit_event
    record_audit_event(
        store=warehouse.store, actor=actor, action_code="warehouse.updated",
        object_type="Warehouse", object_id=warehouse.pk, object_label=warehouse.name,
    )
    return warehouse


def _clear_other_defaults(store, *, keep: "Warehouse | None") -> None:
    queryset = Warehouse.objects.filter(store=store, is_default=True)
    if keep is not None:
        queryset = queryset.exclude(pk=keep.pk)
    queryset.update(is_default=False)


@transaction.atomic
def set_default_warehouse(warehouse: Warehouse, *, actor=None) -> Warehouse:
    if not warehouse.is_active:
        raise WarehouseError("انبارِ غیرفعال نمی‌تواند پیش‌فرض شود.")
    _clear_other_defaults(warehouse.store, keep=warehouse)
    warehouse.is_default = True
    warehouse.save(update_fields=["is_default", "updated_at"])
    from apps.core.services.audit_service import record_audit_event
    record_audit_event(
        store=warehouse.store, actor=actor, action_code="warehouse.default_changed",
        object_type="Warehouse", object_id=warehouse.pk, object_label=warehouse.name,
    )
    return warehouse


@transaction.atomic
def archive_warehouse(warehouse: Warehouse, *, actor=None) -> Warehouse:
    if warehouse.is_default:
        raise WarehouseError("انبارِ پیش‌فرض را نمی‌توان آرشیو کرد؛ ابتدا انبارِ دیگری را پیش‌فرض کنید.")
    warehouse.is_active = False
    warehouse.save(update_fields=["is_active", "updated_at"])
    from apps.core.services.audit_service import record_audit_event
    record_audit_event(
        store=warehouse.store, actor=actor, action_code="warehouse.archived",
        object_type="Warehouse", object_id=warehouse.pk, object_label=warehouse.name,
    )
    return warehouse
