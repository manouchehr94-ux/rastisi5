"""رزروِ موجودی — نگاه کنید به ADR-39 در ``SAAS_DOMAIN_DECISIONS.md``.

سیاستِ این ماژول دقیقاً همان چیزی است که ADR-39 مستند می‌کند: رزرو فقط
موجودیِ در دسترس (available) را کم می‌کند، هرگز موجودیِ فیزیکی (on_hand)
را — فقط *مصرفِ* (consume) رزرو است که واقعاً موجودی را کم می‌کند و یک
``StockMovement`` (از طریق ``inventory_service.decrement_stock_for_order_item``)
ثبت می‌کند. آزادسازی/انقضا هرگز موجودیِ فیزیکی را لمس نمی‌کنند چون رزرو
از ابتدا آن را کم نکرده بود.

زمان‌بندیِ رزرو (checkpoint 3، بخش ۷): در این نسخه، رزرو بلافاصله پیش از
ساختِ سفارش ایجاد و در همان تراکنشِ اتمیک بلافاصله مصرف می‌شود —
``order_service.create_order_from_cart`` هرگز رزروی را بینِ دو درخواستِ
HTTP جداگانه باز نگه نمی‌دارد (نگاه کنید به ADR-39 برای دلیلِ این
انتخاب و جایگزین‌های بررسی‌شده)."""

from datetime import timedelta

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from apps.catalog.models import InventoryReservation, Product, ProductVariant
from apps.catalog.services.inventory_service import InsufficientStockError, decrement_stock_for_order_item
from apps.core.services.audit_service import record_audit_event

DEFAULT_RESERVATION_TTL_MINUTES = 20


class ReservationError(Exception):
    """خطای قابل‌نمایش هنگام رزروِ موجودی."""


def _active_reserved_quantity(*, product, variant) -> int:
    return InventoryReservation.objects.filter(
        product=product, variant=variant, status=InventoryReservation.Status.ACTIVE,
    ).aggregate(total=Sum("quantity"))["total"] or 0


@transaction.atomic
def reserve_inventory(
    *, store, product, variant=None, quantity: int, cart=None, source: str = "checkout",
    idempotency_key: str = "", ttl_minutes: int | None = DEFAULT_RESERVATION_TTL_MINUTES, metadata: dict | None = None,
) -> InventoryReservation:
    """موجودیِ در دسترس را برای ``quantity`` واحد رزرو می‌کند.

    قفلِ ردیفِ Product/ProductVariant قبل از محاسبه‌ی موجودیِ در دسترس
    گرفته می‌شود تا دو رزروِ هم‌زمان برای آخرین واحد هرگز هر دو موفق
    نشوند — دقیقاً همان الگوی قفلِ پایدارِ
    ``order_service._lock_and_revalidate_items``.
    """
    if idempotency_key:
        existing = InventoryReservation.objects.filter(idempotency_key=idempotency_key).first()
        if existing is not None:
            return existing

    if quantity <= 0:
        raise ReservationError("تعداد رزرو باید مثبت باشد.")
    if product.store_id != store.pk:
        raise ReservationError("این کالا متعلق به فروشگاه دیگری است.")
    if variant is not None and (variant.product_id != product.pk or variant.store_id != store.pk):
        raise ReservationError("این تنوع متعلق به این کالا/فروشگاه نیست.")
    if product.status != Product.Status.ACTIVE:
        raise ReservationError(f"کالای «{product.name}» دیگر برای فروش موجود نیست.")
    if variant is not None and not variant.is_active:
        raise ReservationError(f"تنوعِ انتخاب‌شده برای «{product.name}» دیگر معتبر نیست.")

    if variant is not None:
        locked = ProductVariant.objects.select_for_update().get(pk=variant.pk)
        on_hand = locked.stock
    else:
        locked = Product.objects.select_for_update().get(pk=product.pk)
        on_hand = locked.stock

    already_reserved = _active_reserved_quantity(product=product, variant=variant)
    available = on_hand - already_reserved
    if quantity > available:
        raise InsufficientStockError(f"موجودی «{product.name}» کافی نیست")

    expires_at = timezone.now() + timedelta(minutes=ttl_minutes) if ttl_minutes else None
    reservation = InventoryReservation.objects.create(
        store=store, product=product, variant=variant, cart=cart, quantity=quantity,
        status=InventoryReservation.Status.ACTIVE, idempotency_key=idempotency_key, source=source,
        expires_at=expires_at, metadata=metadata or {},
    )
    return reservation


@transaction.atomic
def consume_inventory_reservation(reservation: InventoryReservation, *, order, actor=None) -> InventoryReservation:
    """رزرو را مصرف می‌کند: موجودیِ فیزیکی را واقعاً کم می‌کند (از طریق
    ``inventory_service.decrement_stock_for_order_item``، با ثبتِ
    ``StockMovement``) و رزرو را ``CONSUMED`` علامت می‌زند.

    اگر رزرو از قبل مصرف شده باشد (retry)، بدونِ کاهشِ دوباره‌ی موجودی
    همان رزرو را برمی‌گرداند — idempotent."""
    reservation = InventoryReservation.objects.select_for_update().get(pk=reservation.pk)
    if reservation.status == InventoryReservation.Status.CONSUMED:
        return reservation
    if reservation.status in InventoryReservation.FINAL_STATUSES:
        raise ReservationError(f"این رزرو در وضعیتِ «{reservation.get_status_display()}» است و دیگر قابلِ مصرف نیست.")

    decrement_stock_for_order_item(
        store=reservation.store, product=reservation.product, variant=reservation.variant,
        quantity=reservation.quantity, order=order, actor=actor,
    )
    reservation.status = InventoryReservation.Status.CONSUMED
    reservation.consumed_at = timezone.now()
    reservation.order = order
    reservation.save(update_fields=["status", "consumed_at", "order", "updated_at"])
    return reservation


@transaction.atomic
def release_inventory_reservation(reservation: InventoryReservation, *, actor=None) -> InventoryReservation:
    """رزرو را آزاد می‌کند (بدونِ اثر روی موجودیِ فیزیکی چون رزرو هرگز آن را
    کم نکرده بود)."""
    reservation = InventoryReservation.objects.select_for_update().get(pk=reservation.pk)
    if reservation.status == InventoryReservation.Status.CONSUMED:
        raise ReservationError("رزروِ مصرف‌شده را نمی‌توان آزاد کرد.")
    if reservation.status in InventoryReservation.FINAL_STATUSES:
        raise ReservationError(f"این رزرو در وضعیتِ «{reservation.get_status_display()}» است.")

    reservation.status = InventoryReservation.Status.RELEASED
    reservation.released_at = timezone.now()
    reservation.save(update_fields=["status", "released_at", "updated_at"])
    record_audit_event(
        store=reservation.store, actor=actor, action_code="reservation.released",
        object_type="InventoryReservation", object_id=reservation.pk,
        object_label=str(reservation.product.name if reservation.product_id else ""),
    )
    return reservation


def expire_inventory_reservations(*, batch_size: int = 500) -> int:
    """رزروهای فعالِ منقضی‌شده را دسته‌دسته به ``EXPIRED`` تغییر می‌دهد —
    هرگز کلِ نتیجه را یک‌جا در حافظه بارگذاری نمی‌کند (فقط شناسه‌ها، به
    اندازه‌ی هر دسته). Store-safe و idempotent — اجرای دوباره روی رزروهایی
    که قبلاً منقضی شده‌اند اثری ندارد چون فیلترِ ``status=ACTIVE`` دیگر
    آن‌ها را برنمی‌گرداند."""
    now = timezone.now()
    total_expired = 0

    while True:
        ids = list(
            InventoryReservation.objects.filter(
                status=InventoryReservation.Status.ACTIVE, expires_at__isnull=False, expires_at__lte=now,
            ).order_by("pk").values_list("pk", flat=True)[:batch_size]
        )
        if not ids:
            break
        with transaction.atomic():
            updated = InventoryReservation.objects.filter(
                pk__in=ids, status=InventoryReservation.Status.ACTIVE,
            ).update(status=InventoryReservation.Status.EXPIRED, released_at=now)
            total_expired += updated
        if len(ids) < batch_size:
            break

    return total_expired


def list_reservations(store, *, status: str = ""):
    queryset = InventoryReservation.objects.filter(store=store).select_related("product", "variant", "cart", "order")
    if status:
        queryset = queryset.filter(status=status)
    return queryset
