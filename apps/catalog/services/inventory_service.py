"""دفتر موجودی (Inventory Ledger) — کاهش/بازگشتِ اتمیکِ موجودی به‌همراه ثبتِ حسابرسی.

هیچ‌جای این ماژول موجودی را مستقیماً بدون ثبت یک ``StockMovement`` تغییر
نمی‌دهد (ADR-31 در ``SAAS_DOMAIN_DECISIONS.md``). این سرویس، لایه‌ی واحدِ
اعمالِ تغییرِ موجودی برای سفارش‌ها (ثبت/لغو) است — پیش از این PR،
``order_service.create_order_from_cart`` مستقیماً و بدون ثبت، ``Product.stock``
را کم می‌کرد و برای اقلامِ دارای تنوع، موجودیِ *اشتباه* (Product به‌جای
ProductVariant) را کم می‌کرد و لغو سفارش هرگز موجودی را بازنمی‌گرداند — این
دو باگ اینجا با معرفیِ دفتر موجودی اصلاح شده‌اند.
"""

from django.db.models import F

from apps.catalog.models import Product, ProductVariant, StockMovement
from apps.core.services.audit_service import record_audit_event


class InsufficientStockError(Exception):
    """موجودیِ هدف (کالا یا تنوع) برای این تعداد کافی نیست."""


def decrement_stock_for_order_item(*, store, product, variant, quantity, order, actor=None):
    """موجودیِ صحیح (تنوع در صورت وجود، وگرنه خودِ کالا) را برای یک قلمِ سفارشِ
    تازه کاهش می‌دهد و یک ``StockMovement`` ثبت می‌کند.

    باید داخل همان تراکنشی فراخوانی شود که قفلِ ردیف (``select_for_update``)
    را از قبل گرفته — نگاه کنید به
    ``order_service._lock_and_revalidate_items`` — چون مقدارِ
    ``stock_before`` مستقیماً از رویِ نمونه‌ی پاس‌داده‌شده خوانده می‌شود، نه
    با یک کوئریِ تازه.
    """
    if variant is not None:
        stock_before = variant.stock
        updated = ProductVariant.objects.filter(pk=variant.pk, stock__gte=quantity).update(
            stock=F("stock") - quantity
        )
    else:
        stock_before = product.stock
        updated = Product.objects.filter(pk=product.pk, stock__gte=quantity).update(
            stock=F("stock") - quantity
        )

    if updated == 0:
        raise InsufficientStockError(f"موجودی «{product.name}» کافی نیست")

    StockMovement.objects.create(
        store=store, product=product, variant=variant,
        reason=StockMovement.Reason.ORDER_PLACED, delta=-quantity,
        stock_before=stock_before, stock_after=stock_before - quantity,
        order=order, actor=actor,
    )


def restock_order(*, store, order, actor=None) -> None:
    """موجودیِ تمامِ اقلامِ این سفارش را بازمی‌گرداند (لغو سفارش) و برای هرکدام
    یک ``StockMovement`` با علتِ ``ORDER_CANCELED`` ثبت می‌کند.

    اقلامی که ``product``شان دیگر وجود ندارد (حذف‌شده، ``SET_NULL``) بی‌صدا
    رد می‌شوند — چیزی برای بازگرداندنِ موجودی به آن باقی نمانده.
    """
    for item in order.items.select_for_update().select_related("product", "variant"):
        if item.product_id is None:
            continue

        if item.variant_id is not None:
            variant = ProductVariant.objects.select_for_update().filter(pk=item.variant_id).first()
            if variant is None:
                continue
            stock_before = variant.stock
            ProductVariant.objects.filter(pk=variant.pk).update(stock=F("stock") + item.quantity)
            product, target_variant = item.product, variant
        else:
            product = Product.objects.select_for_update().filter(pk=item.product_id).first()
            if product is None:
                continue
            stock_before = product.stock
            Product.objects.filter(pk=product.pk).update(stock=F("stock") + item.quantity)
            target_variant = None

        StockMovement.objects.create(
            store=store, product=product, variant=target_variant,
            reason=StockMovement.Reason.ORDER_CANCELED, delta=item.quantity,
            stock_before=stock_before, stock_after=stock_before + item.quantity,
            order=order, actor=actor,
        )


class ReturnItemAlreadyRestockedError(Exception):
    """این قلمِ مرجوعی قبلاً یک‌بار به موجودی بازگشته — نگاه کنید به ADR-35."""


def restock_return_item(*, store, return_item, actor=None) -> "StockMovement | None":
    """موجودیِ یک قلمِ مرجوعیِ قابل‌بازگشت را افزایش می‌دهد و یک
    ``StockMovement`` با علتِ ``RETURN_RESTOCK`` ثبت می‌کند.

    محافظت در برابر بازگشتِ دوباره از دو راه: (۱) قیدِ دیتابیسِ
    ``uniq_stockmv_per_return_item`` که هرگز اجازه نمی‌دهد بیش از یک
    ``StockMovement`` به یک ``ReturnItem`` ارجاع دهد، و (۲) این تابع پیش از
    درج، وجودِ ردیفِ قبلی را صریحاً بررسی می‌کند تا خطای واضح
    ``ReturnItemAlreadyRestockedError`` بدهد به‌جای ``IntegrityError`` خام.
    فراخواننده (``return_service.complete_return``) باید ``return_item`` را
    از قبل قفل کرده باشد.
    """
    if StockMovement.objects.filter(return_item=return_item).exists():
        raise ReturnItemAlreadyRestockedError("موجودیِ این قلمِ مرجوعی قبلاً بازگشت داده شده است.")

    quantity = return_item.quantity_received or 0
    if quantity <= 0:
        return None

    order_item = return_item.order_item
    product = order_item.product
    variant = order_item.variant
    if product is None:
        return None  # کالای اصلی حذف شده — چیزی برای بازگرداندنِ موجودی به آن نمانده

    if variant is not None:
        variant = ProductVariant.objects.select_for_update().filter(pk=variant.pk).first()
        if variant is None:
            return None
        stock_before = variant.stock
        ProductVariant.objects.filter(pk=variant.pk).update(stock=F("stock") + quantity)
    else:
        product = Product.objects.select_for_update().filter(pk=product.pk).first()
        if product is None:
            return None
        stock_before = product.stock
        Product.objects.filter(pk=product.pk).update(stock=F("stock") + quantity)

    return StockMovement.objects.create(
        store=store, product=product, variant=variant,
        reason=StockMovement.Reason.RETURN_RESTOCK, delta=quantity,
        stock_before=stock_before, stock_after=stock_before + quantity,
        order=order_item.order, return_item=return_item, actor=actor,
    )


def restock_refund_item(*, store, refund_item, actor=None) -> "StockMovement | None":
    """موجودی را برای یک قلمِ استردادِ *بدونِ* درخواستِ مرجوعیِ رسمی بازمی‌گرداند
    (مثلاً استردادِ سریعِ حضوری) — فقط وقتی مدیر صراحتاً «بازگرداندنِ موجودی»
    را در لحظه‌ی ثبتِ استرداد انتخاب کرده باشد
    (``refund_service.execute_order_refund(..., restock=True)``)."""
    if StockMovement.objects.filter(refund_item=refund_item).exists():
        raise ReturnItemAlreadyRestockedError("موجودیِ این قلمِ استرداد قبلاً بازگشت داده شده است.")

    order_item = refund_item.order_item
    quantity = refund_item.quantity
    product = order_item.product
    variant = order_item.variant
    if product is None or quantity <= 0:
        return None

    if variant is not None:
        variant = ProductVariant.objects.select_for_update().filter(pk=variant.pk).first()
        if variant is None:
            return None
        stock_before = variant.stock
        ProductVariant.objects.filter(pk=variant.pk).update(stock=F("stock") + quantity)
    else:
        product = Product.objects.select_for_update().filter(pk=product.pk).first()
        if product is None:
            return None
        stock_before = product.stock
        Product.objects.filter(pk=product.pk).update(stock=F("stock") + quantity)

    return StockMovement.objects.create(
        store=store, product=product, variant=variant,
        reason=StockMovement.Reason.REFUND_RESTOCK, delta=quantity,
        stock_before=stock_before, stock_after=stock_before + quantity,
        order=order_item.order, refund_item=refund_item, actor=actor,
    )


def adjust_stock_manually(*, store, product, variant=None, new_stock: int, actor, note: str = ""):
    """موجودیِ کالا یا تنوع را به مقدارِ مطلقِ ``new_stock`` تنظیم می‌کند
    (مثلاً پس از شمارشِ انبار) و تفاوت را در دفترِ موجودی ثبت می‌کند."""
    if new_stock < 0:
        raise ValueError("موجودی نمی‌تواند منفی باشد.")

    target = variant if variant is not None else product
    stock_before = target.stock
    delta = new_stock - stock_before
    if delta == 0:
        return None

    target.stock = new_stock
    target.save(update_fields=["stock", "updated_at"])

    movement = StockMovement.objects.create(
        store=store, product=product, variant=variant,
        reason=StockMovement.Reason.MANUAL_ADJUSTMENT, delta=delta,
        stock_before=stock_before, stock_after=new_stock,
        actor=actor, note=note,
    )
    record_audit_event(
        store=store, actor=actor, action_code="inventory.manual_adjustment",
        object_type="Product" if variant is None else "ProductVariant",
        object_id=target.pk, object_label=product.name,
        before={"stock": stock_before}, after={"stock": new_stock}, metadata={"note": note},
    )
    return movement


def list_stock_movements(store, *, product=None, variant=None):
    queryset = StockMovement.objects.filter(store=store).select_related("product", "variant", "order", "actor")
    if variant is not None:
        queryset = queryset.filter(variant=variant)
    elif product is not None:
        queryset = queryset.filter(product=product)
    return queryset
