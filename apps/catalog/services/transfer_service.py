"""انتقالِ موجودی بین انبارها — نگاه کنید به ADR-40 در ``SAAS_DOMAIN_DECISIONS.md``.

بر خلافِ سایرِ رویدادهای ``StockMovement`` (که ``stock_before``/``stock_after``
را روی موجودیِ کلِ ``Product``/``ProductVariant`` می‌سنجند)، انتقال بین دو
انبارِ همان Store هرگز موجودیِ کلِ کالا (aggregate) را تغییر نمی‌دهد — فقط
محلِ آن جابه‌جا می‌شود. به همین دلیل ``stock_before``/``stock_after`` برای
رویدادهای ``WAREHOUSE_TRANSFER_OUT``/``WAREHOUSE_TRANSFER_IN`` روی موجودیِ
همان انبار (``WarehouseInventory.on_hand``) سنجیده می‌شود، نه روی
``Product.stock`` — این با ADR-38 سازگار است: ``Product``/``Variant.stock``
همچنان تنها منبعِ حقیقتِ موجودیِ قابلِ‌فروش است و انتقالِ داخلی آن را
تغییر نمی‌دهد.

قفلِ ردیف‌های ``WarehouseInventory`` همیشه به ترتیبِ ``(product_id,
variant_id)`` گرفته می‌شود — دقیقاً همان الگوی جلوگیری از بن‌بست که در
``order_service._lock_and_revalidate_items`` استفاده شده."""

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import F
from django.utils import timezone

from apps.catalog.models import StockMovement, WarehouseInventory, WarehouseTransfer, WarehouseTransferItem
from apps.core.services.audit_service import record_audit_event


class TransferError(Exception):
    """خطای قابل‌نمایش هنگام مدیریتِ انتقالِ انبار."""


def _next_transfer_number(store) -> str:
    count = WarehouseTransfer.objects.filter(store=store).count()
    return f"TRF-{count + 1:06d}"


def list_transfers(store):
    return WarehouseTransfer.objects.filter(store=store).select_related("source_warehouse", "destination_warehouse")


def _validate_transition(transfer: WarehouseTransfer, target_status: str) -> None:
    allowed = WarehouseTransfer.ALLOWED_TRANSITIONS.get(transfer.status, set())
    if target_status not in allowed:
        target_label = dict(WarehouseTransfer.Status.choices)[target_status]
        raise TransferError(
            f"انتقال از وضعیتِ «{transfer.get_status_display()}» نمی‌تواند به «{target_label}» برود."
        )


@transaction.atomic
def create_transfer(store, *, source_warehouse, destination_warehouse, items, note="", actor=None) -> WarehouseTransfer:
    """``items``: لیستی از dict با کلیدهای ``product``، ``variant`` (اختیاری) و ``quantity``."""
    if not items:
        raise TransferError("انتقال باید حداقل یک قلم داشته باشد.")

    transfer = WarehouseTransfer(
        store=store, transfer_number=_next_transfer_number(store),
        source_warehouse=source_warehouse, destination_warehouse=destination_warehouse,
        note=note, actor=actor,
    )
    try:
        transfer.full_clean(exclude=["transfer_number"])
    except ValidationError as exc:
        raise TransferError("؛ ".join(sum(exc.message_dict.values(), []))) from exc
    transfer.save()

    for entry in items:
        quantity = entry["quantity"]
        if quantity <= 0:
            raise TransferError("تعدادِ درخواستی باید مثبت باشد.")
        variant = entry.get("variant")
        product = entry["product"]
        if product.store_id != store.pk or (variant is not None and variant.store_id != store.pk):
            raise TransferError("این کالا/تنوع متعلق به این فروشگاه نیست.")
        WarehouseTransferItem.objects.create(
            transfer=transfer, product=product, variant=variant, quantity_requested=quantity,
        )

    record_audit_event(
        store=store, actor=actor, action_code="transfer.created",
        object_type="WarehouseTransfer", object_id=transfer.pk, object_label=transfer.transfer_number,
    )
    return transfer


@transaction.atomic
def request_transfer(transfer: WarehouseTransfer, *, actor=None) -> WarehouseTransfer:
    transfer = WarehouseTransfer.objects.select_for_update().get(pk=transfer.pk)
    _validate_transition(transfer, WarehouseTransfer.Status.REQUESTED)
    transfer.status = WarehouseTransfer.Status.REQUESTED
    transfer.save(update_fields=["status", "updated_at"])
    record_audit_event(
        store=transfer.store, actor=actor, action_code="transfer.requested",
        object_type="WarehouseTransfer", object_id=transfer.pk, object_label=transfer.transfer_number,
    )
    return transfer


@transaction.atomic
def ship_transfer(transfer: WarehouseTransfer, *, actor=None) -> WarehouseTransfer:
    """موجودیِ انبارِ مبدأ را برای هر قلم کم می‌کند و به ``IN_TRANSIT`` می‌برد.

    فقط از ``REQUESTED`` مجاز است، پس یک retry پس از موفقیت (وضعیت دیگر
    ``REQUESTED`` نیست) با ``TransferError`` رد می‌شود — کاهشِ دوباره‌ی
    موجودی هرگز رخ نمی‌دهد."""
    transfer = WarehouseTransfer.objects.select_for_update().get(pk=transfer.pk)
    _validate_transition(transfer, WarehouseTransfer.Status.IN_TRANSIT)

    items = list(
        transfer.items.select_related("product", "variant").order_by("product_id", "variant_id")
    )
    for item in items:
        balance = WarehouseInventory.objects.select_for_update().filter(
            store=transfer.store, warehouse=transfer.source_warehouse,
            product=item.product, variant=item.variant,
        ).first()
        available = balance.on_hand if balance is not None else 0
        if item.quantity_requested > available:
            raise TransferError(f"موجودیِ «{item.product.name}» در انبارِ مبدأ کافی نیست.")

        before = available
        WarehouseInventory.objects.filter(pk=balance.pk).update(on_hand=F("on_hand") - item.quantity_requested)
        item.quantity_shipped = item.quantity_requested
        item.save(update_fields=["quantity_shipped", "updated_at"])
        StockMovement.objects.create(
            store=transfer.store, product=item.product, variant=item.variant, warehouse=transfer.source_warehouse,
            actor=actor, reason=StockMovement.Reason.WAREHOUSE_TRANSFER_OUT,
            delta=-item.quantity_requested, stock_before=before, stock_after=before - item.quantity_requested,
            note=f"انتقال {transfer.transfer_number} به {transfer.destination_warehouse.name}",
        )

    transfer.status = WarehouseTransfer.Status.IN_TRANSIT
    transfer.shipped_at = timezone.now()
    transfer.save(update_fields=["status", "shipped_at", "updated_at"])
    record_audit_event(
        store=transfer.store, actor=actor, action_code="transfer.shipped",
        object_type="WarehouseTransfer", object_id=transfer.pk, object_label=transfer.transfer_number,
    )
    return transfer


@transaction.atomic
def receive_transfer(transfer: WarehouseTransfer, *, actor=None) -> WarehouseTransfer:
    """موجودیِ انبارِ مقصد را به‌اندازه‌ی ``quantity_shipped`` هر قلم زیاد
    می‌کند و به ``RECEIVED`` می‌برد — فقط از ``IN_TRANSIT`` مجاز است، پس
    retry پس از موفقیت idempotent رد می‌شود (افزایشِ دوباره هرگز رخ
    نمی‌دهد)."""
    transfer = WarehouseTransfer.objects.select_for_update().get(pk=transfer.pk)
    _validate_transition(transfer, WarehouseTransfer.Status.RECEIVED)

    items = list(
        transfer.items.select_related("product", "variant").order_by("product_id", "variant_id")
    )
    for item in items:
        quantity = item.quantity_shipped or 0
        balance, _created = WarehouseInventory.objects.select_for_update().get_or_create(
            store=transfer.store, warehouse=transfer.destination_warehouse,
            product=item.product, variant=item.variant, defaults={"on_hand": 0},
        )
        before = balance.on_hand
        WarehouseInventory.objects.filter(pk=balance.pk).update(on_hand=F("on_hand") + quantity)
        item.quantity_received = quantity
        item.save(update_fields=["quantity_received", "updated_at"])
        StockMovement.objects.create(
            store=transfer.store, product=item.product, variant=item.variant, warehouse=transfer.destination_warehouse,
            actor=actor, reason=StockMovement.Reason.WAREHOUSE_TRANSFER_IN,
            delta=quantity, stock_before=before, stock_after=before + quantity,
            note=f"انتقال {transfer.transfer_number} از {transfer.source_warehouse.name}",
        )

    transfer.status = WarehouseTransfer.Status.RECEIVED
    transfer.received_at = timezone.now()
    transfer.save(update_fields=["status", "received_at", "updated_at"])
    record_audit_event(
        store=transfer.store, actor=actor, action_code="transfer.received",
        object_type="WarehouseTransfer", object_id=transfer.pk, object_label=transfer.transfer_number,
    )
    return transfer


@transaction.atomic
def cancel_transfer(transfer: WarehouseTransfer, *, actor=None) -> WarehouseTransfer:
    """انتقال را لغو می‌کند. اگر از پیش ``IN_TRANSIT`` بوده (یعنی موجودیِ
    مبدأ قبلاً کم شده)، همان مقدارِ ارسال‌شده به انبارِ مبدأ بازگردانده
    می‌شود — چون هرگز به مقصد نرسیده."""
    transfer = WarehouseTransfer.objects.select_for_update().get(pk=transfer.pk)
    was_in_transit = transfer.status == WarehouseTransfer.Status.IN_TRANSIT
    _validate_transition(transfer, WarehouseTransfer.Status.CANCELLED)

    if was_in_transit:
        items = list(
            transfer.items.select_related("product", "variant").order_by("product_id", "variant_id")
        )
        for item in items:
            quantity = item.quantity_shipped or 0
            if quantity <= 0:
                continue
            balance = WarehouseInventory.objects.select_for_update().get(
                store=transfer.store, warehouse=transfer.source_warehouse,
                product=item.product, variant=item.variant,
            )
            before = balance.on_hand
            WarehouseInventory.objects.filter(pk=balance.pk).update(on_hand=F("on_hand") + quantity)
            StockMovement.objects.create(
                store=transfer.store, product=item.product, variant=item.variant, warehouse=transfer.source_warehouse,
                actor=actor, reason=StockMovement.Reason.WAREHOUSE_TRANSFER_IN,
                delta=quantity, stock_before=before, stock_after=before + quantity,
                note=f"لغوِ انتقال {transfer.transfer_number} — بازگشت به {transfer.source_warehouse.name}",
            )

    transfer.status = WarehouseTransfer.Status.CANCELLED
    transfer.cancelled_at = timezone.now()
    transfer.save(update_fields=["status", "cancelled_at", "updated_at"])
    record_audit_event(
        store=transfer.store, actor=actor, action_code="transfer.cancelled",
        object_type="WarehouseTransfer", object_id=transfer.pk, object_label=transfer.transfer_number,
    )
    return transfer
