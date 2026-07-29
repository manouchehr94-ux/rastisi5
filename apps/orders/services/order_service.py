"""لایه‌ی سرویس سفارش‌ها — ساخت سفارش از سبد و مدیریت گردش وضعیت.

مطابق docs/spec/01-PROJECT-SPEC.md بخش ۶، قواعد ۷ تا ۹.
"""

import random

from django.db import IntegrityError, transaction

from apps.cart.services.pricing import cart_totals
from apps.catalog.models import Product, ProductVariant
from apps.catalog.services.inventory_service import (
    InsufficientStockError,
    decrement_stock_for_order_item,
    restock_order,
)
from apps.core.utils import format_toman
from apps.orders.models import Order, OrderItem, OrderStatusHistory
from apps.sms.events import SmsEvent
from apps.sms.services.sms_service import send_event_sms

ORDER_CODE_PREFIX = "DM"

# رویداد پیامکی متناظر با هر وضعیت مقصد سفارش (پردازش/ارسال/تحویل/لغو).
STATUS_SMS_EVENTS = {
    Order.Status.PROCESSING: SmsEvent.ORDER_PROCESSING,
    Order.Status.SHIPPED: SmsEvent.ORDER_SHIPPED,
    Order.Status.DELIVERED: SmsEvent.ORDER_DELIVERED,
    Order.Status.CANCELED: SmsEvent.ORDER_CANCELED,
}


def _order_sms_context(order: Order) -> dict:
    return {
        "customer_name": order.customer.full_name,
        "order_code": order.code,
        "amount": format_toman(order.grand_total, with_unit=False),
        "tracking_code": order.tracking_code,
    }

ALLOWED_TRANSITIONS = {
    Order.Status.PENDING: {Order.Status.PROCESSING, Order.Status.CANCELED},
    Order.Status.PROCESSING: {Order.Status.SHIPPED, Order.Status.CANCELED},
    Order.Status.SHIPPED: {Order.Status.DELIVERED, Order.Status.CANCELED},
    Order.Status.DELIVERED: set(),
    Order.Status.CANCELED: set(),
}

FINAL_STATUSES = {Order.Status.DELIVERED, Order.Status.CANCELED}


def _generate_order_code() -> str:
    while True:
        code = f"{ORDER_CODE_PREFIX}-{random.randint(10000, 99999)}"
        if not Order.objects.filter(code=code).exists():
            return code


def _snapshot_address(address) -> dict:
    return {
        "receiver_name": address.receiver_name,
        "phone": address.phone,
        "province": address.province,
        "city": address.city,
        "postal_code": address.postal_code,
        "full_address": address.full_address,
    }


def _variant_label(variant) -> str:
    if variant is None:
        return ""
    return f"{variant.attribute}: {variant.value}"


def _lock_and_revalidate_items(items, *, store):
    """قفل و بازاعتبارسنجی نهاییِ هر قلم سبد، درست پیش از ساخت سفارش (بخش ۷/۹).

    فقط بررسی cart_add (زمان افزودن به سبد) کافی نیست — بین افزودن به سبد و
    نهایی‌شدن سفارش ممکن است کالا/تنوع غیرفعال یا حذف شده باشد، یا موجودی
    توسط سفارش‌های هم‌زمان دیگر مصرف شده باشد. ``select_for_update()`` روی
    ردیف‌های Product/ProductVariant را به ترتیب پایدار (بر اساس pk) قفل
    می‌کند — هم برای جلوگیری از race شرط موجودی (بخش ۹) و هم برای این‌که دو
    تراکنش هم‌زمان با محصولات مشترک هرگز در ترتیب متفاوتی قفل نگیرند
    (کاهش ریسک deadlock). روی SQLite هم بدون خطا اجرا می‌شود (قفل واقعیِ
    سطح ردیف روی SQLite معنایی ندارد چون کل دیتابیس هنگام نوشتن قفل
    می‌شود، اما این تابع همان رفتار/تست را روی هر دو backend حفظ می‌کند —
    رفتار concurrency واقعی فقط روی PostgreSQL معتبر است، نه SQLite).
    """
    product_ids = sorted({item.product_id for item in items})
    locked_products = {
        p.pk: p
        for p in Product.objects.select_for_update().filter(pk__in=product_ids).order_by("pk")
    }

    variant_ids = sorted({item.variant_id for item in items if item.variant_id})
    locked_variants = {
        v.pk: v
        for v in ProductVariant.objects.select_for_update().filter(pk__in=variant_ids).order_by("pk")
    } if variant_ids else {}

    for item in items:
        product = locked_products.get(item.product_id)
        if product is None:
            raise ValueError("یکی از کالاهای سبد خرید دیگر موجود نیست")
        if product.store_id != store.pk:
            # هرگز نباید پیش بیاید — cart_add کالا را با همان Store scope
            # می‌کند — اما این‌جا هم به‌عنوان خط دفاعی آخر بررسی می‌شود تا
            # سفارشی هرگز از قلم‌های چندین Store مختلط ساخته نشود.
            raise ValueError(f"کالای «{product.name}» متعلق به این فروشگاه نیست")
        if product.status != Product.Status.ACTIVE:
            raise ValueError(f"کالای «{product.name}» دیگر برای فروش موجود نیست")

        variant = None
        if item.variant_id:
            variant = locked_variants.get(item.variant_id)
            if (
                variant is None
                or variant.product_id != product.pk
                or not variant.is_active
                or variant.store_id != store.pk
            ):
                raise ValueError(f"تنوع انتخاب‌شده برای «{product.name}» دیگر معتبر نیست")

        # موجودیِ مرجع برای اقلامِ دارای تنوع، موجودیِ خودِ تنوع است، نه
        # موجودیِ کالای والد — کالای دارای تنوع می‌تواند Product.stock صفر و
        # ProductVariant.stock مثبت داشته باشد (یا برعکس)؛ نگاه کنید به
        # ADR-31.
        available_stock = variant.stock if variant is not None else product.stock
        if item.quantity > available_stock:
            raise ValueError(f"موجودی «{product.name}» کافی نیست")

    return locked_products, locked_variants


@transaction.atomic
def create_order_from_cart(
    cart, *, customer, vendor, address, shipping_method, payment_gateway,
    coupon=None, note="", store, idempotency_key="",
):
    """سفارش را از روی سبد خرید می‌سازد و همه‌ی مبالغ را اسنپ‌شات می‌کند.

    ``store`` الزامی است — همان Store که فراخوان (معمولاً
    ``checkout_service.finalize_order``) از ``request.store`` resolve کرده؛
    برای قیمت‌گذاری (``cart_totals``) و پیامک ثبت سفارش استفاده می‌شود.

    ``idempotency_key`` اختیاری است (خالی یعنی بدون کنترل idempotency — برای
    فراخوان‌های مستقیم/تست). وقتی مقدار دارد (معمولاً
    ``Cart.checkout_token`` — نگاه کنید به
    ``checkout_service.get_or_create_checkout_token``)، این تابع:

    * ابتدا بررسی می‌کند آیا سفارشی با همین کلید از قبل ساخته شده — اگر بله،
      همان سفارش موجود را برمی‌گرداند (بدون کاهش دوباره‌ی موجودی، بدون قلم
      تکراری) — این حالت «ارسال دوباره‌ی متوالی» (double-click بعد از این‌که
      درخواست اول کامل شده) را می‌پوشاند؛
    * سپس، هنگام درج خودِ Order، به یکتاییِ سطح دیتابیس
      (``uniq_order_idempotency_key_when_set``) تکیه می‌کند: اگر هم‌زمان دو
      درخواست با همین کلید هر دو از بررسی اول عبور کرده باشند (race واقعی)،
      فقط یکی می‌تواند درج را کامل کند؛ درخواستِ بازنده با ``IntegrityError``
      داخل یک savepoint (نه کل تراکنش) مواجه و بلافاصله همان سفارشِ برنده را
      واکشی و برمی‌گرداند — بدون تلاش دوباره برای ساخت قلم‌ها یا کاهش موجودی.
    """
    if idempotency_key:
        existing = Order.objects.filter(idempotency_key=idempotency_key).first()
        if existing is not None:
            return existing

    if vendor.store_id != store.pk:
        # حفظ عدم‌تطابق Order.store/Order.vendor.store در همان مسیر تولید
        # Production (بخش ۱ — این تنها مسیر ساخت Order در Production است).
        raise ValueError("این فروشنده متعلق به این فروشگاه نیست")

    items = list(cart.items.select_related("product", "variant"))
    if not items:
        raise ValueError("سبد خرید خالی است")

    locked_products, locked_variants = _lock_and_revalidate_items(items, store=store)

    totals = cart_totals(cart, store=store, coupon=coupon, shipping_method=shipping_method)

    try:
        with transaction.atomic():
            order = Order.objects.create(
                code=_generate_order_code(),
                store=store,
                customer=customer,
                vendor=vendor,
                idempotency_key=idempotency_key,
                address=_snapshot_address(address),
                shipping_method=shipping_method,
                payment_gateway=payment_gateway,
                coupon=coupon,
                items_total=totals["items_total"],
                product_discount=totals["product_discount"],
                coupon_discount=totals["coupon_discount"],
                shipping_cost=totals["shipping_cost"],
                tax=totals["tax"],
                grand_total=totals["grand_total"],
                note=note,
            )
    except IntegrityError:
        if idempotency_key:
            existing = Order.objects.filter(idempotency_key=idempotency_key).first()
            if existing is not None:
                return existing
        raise

    for item in items:
        product = locked_products[item.product_id]
        variant = locked_variants.get(item.variant_id) if item.variant_id else None
        unit_price = product.final_price
        OrderItem.objects.create(
            order=order,
            product=product,
            variant=variant,
            product_name=product.name,
            sku=product.sku,
            variant_label=_variant_label(variant),
            quantity=item.quantity,
            unit_price=unit_price,
            line_total=unit_price * item.quantity,
        )
        # با قفلِ قبلی (_lock_and_revalidate_items)، شکستِ این کاهش عملاً
        # نباید پیش بیاید — decrement_stock_for_order_item همچنان دوباره
        # (به‌صورت اتمیک، با stock__gte) بررسی می‌کند تا موجودی هرگز منفی
        # نشود، و برای هر قلم دقیقاً یک ``StockMovement`` ثبت می‌کند.
        try:
            decrement_stock_for_order_item(
                store=store, product=product, variant=variant, quantity=item.quantity, order=order,
            )
        except InsufficientStockError as exc:
            raise ValueError(str(exc)) from exc

    OrderStatusHistory.objects.create(
        order=order, from_status="", to_status=order.status, note="سفارش ثبت شد"
    )

    if coupon is not None and totals["coupon_applied"]:
        coupon.used_count += 1
        coupon.save(update_fields=["used_count"])

    transaction.on_commit(
        lambda: send_event_sms(
            SmsEvent.ORDER_PLACED, order.customer.phone, _order_sms_context(order), store=store
        )
    )

    return order


@transaction.atomic
def change_order_status(
    order: Order, to_status: str, *, by=None, note: str = "", tracking_code: str = "", store
) -> Order:
    """وضعیت سفارش را تغییر می‌دهد و حتماً یک رکورد OrderStatusHistory می‌سازد.

    tracking_code فقط برای گذار به «ارسال شده» معنا دارد و روی سفارش ذخیره
    می‌شود تا در پیامک اطلاع‌رسانی درج شود. ``store`` الزامی است — همان
    Store که برای پیامکِ تغییر وضعیت استفاده می‌شود؛ این تابع خودش هرگز
    Store را دوباره از Host یا حالت سازگاری حدس نمی‌زند.
    """
    from_status = order.status

    if from_status in FINAL_STATUSES:
        raise ValueError(f"سفارش در وضعیت نهایی «{order.get_status_display()}» است و قابل تغییر نیست")

    if to_status == from_status:
        raise ValueError("وضعیت جدید با وضعیت فعلی یکسان است")

    if to_status not in ALLOWED_TRANSITIONS.get(from_status, set()):
        raise ValueError(f"گذار از «{from_status}» به «{to_status}» مجاز نیست")

    update_fields = ["status", "updated_at"]
    order.status = to_status
    if to_status == Order.Status.SHIPPED and tracking_code:
        order.tracking_code = tracking_code
        update_fields.append("tracking_code")
    order.save(update_fields=update_fields)

    if to_status == Order.Status.CANCELED:
        # لغو یک سفارشِ PENDING/PROCESSING/SHIPPED باید موجودیِ کاهش‌یافته
        # هنگام ثبت را بازگرداند — پیش از این PR، لغو سفارش هرگز موجودی را
        # بازنمی‌گرداند (نگاه کنید به ADR-31). ``CANCELED`` یک وضعیتِ نهاییِ
        # بدونِ گذارِ خروجی است، پس این مسیر برای هر سفارش حداکثر یک‌بار اجرا
        # می‌شود.
        restock_order(store=store, order=order, actor=by)

    OrderStatusHistory.objects.create(
        order=order, from_status=from_status, to_status=to_status, changed_by=by, note=note
    )

    sms_event = STATUS_SMS_EVENTS.get(to_status)
    if sms_event:
        transaction.on_commit(
            lambda: send_event_sms(
                sms_event, order.customer.phone, _order_sms_context(order), store=store
            )
        )

    return order
