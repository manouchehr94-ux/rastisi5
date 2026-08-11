"""سرویس حل مقصد — تبدیل مقصد ذخیره‌شده به URL قابل رندر.

این ماژول تنها نقطه‌ی مسئول تبدیل مقصد ذخیره‌شده به URL نهایی است.
هرگز '#' برنمی‌گرداند. اگر مقصدی معتبر نباشد، None برمی‌گرداند.
"""

from django.urls import reverse

from .models import DestinationType


def resolve_destination_url(instance) -> str | None:
    """URL مقصد را بر اساس نوع و مقادیر FK حل می‌کند.

    بازمی‌گرداند:
    - URL معتبر (رشته) اگر مقصد قابل حل باشد
    - None اگر مقصدی وجود نداشته باشد یا شیء مقصد حذف شده باشد

    هرگز بازنمی‌گرداند:
    - '#'
    - مسیر ساختگی
    - URL خطرناک
    """
    dtype = instance.destination_type

    if dtype == DestinationType.NONE:
        return None

    if dtype == DestinationType.CATEGORY:
        category = instance.destination_category
        if category is None:
            return None
        return reverse("catalog:product-list") + f"?category={category.slug}"

    if dtype == DestinationType.PRODUCT:
        product = instance.destination_product
        if product is None:
            return None
        return reverse("catalog:product-detail", args=[product.slug])

    if dtype == DestinationType.BRAND:
        brand = instance.destination_brand
        if brand is None:
            return None
        return reverse("catalog:product-list") + f"?brand={brand.slug}"

    if dtype == DestinationType.COLLECTION:
        collection = instance.destination_collection
        if collection is None:
            return None
        return reverse("catalog:collection-detail", args=[collection.slug])

    if dtype == DestinationType.EXTERNAL:
        url = (instance.destination_external_url or "").strip()
        return url if url else None

    return None


def resolve_destination_context(instance) -> dict:
    """اطلاعات کامل مقصد برای رندر در تمپلیت.

    بازمی‌گرداند دیکشنری شامل:
    - url: آدرس مقصد یا None
    - open_new_tab: بولین
    - rel: مقدار rel برای لینک‌های خارجی (noopener noreferrer)
    """
    url = resolve_destination_url(instance)
    is_external = instance.destination_type == DestinationType.EXTERNAL

    return {
        "url": url,
        "open_new_tab": instance.open_in_new_tab,
        "rel": "noopener noreferrer" if (is_external and instance.open_in_new_tab) else "",
    }


def resolve_destination_setting(store, destination: dict | None) -> dict:
    """معادل ``resolve_destination_context`` برای مقصدهای ذخیره‌شده در JSON
    (نه یک شیء مدل ``DestinationMixin``) — یعنی بلوک ``destination`` داخل
    ``StorefrontSection.settings`` (سازنده بصری).

    برخلاف ``section_registry.validate_destination_settings`` (که فقط شکل/
    enum را چک می‌کند و هرگز دیتابیس را لمس نمی‌کند)، این تابع همان لایه‌ای
    است که مالکیت Store را چک می‌کند — دقیقاً همان تفکیک مسئولیتی که
    ``section_data_service.resolve_products`` برای منابع داده محصول دارد.
    ارجاع حذف‌شده/غیرفعال/متعلق به فروشگاه دیگر بی‌صدا به «بدون مقصد»
    (``url=None``) تبدیل می‌شود — هرگز کرش نمی‌کند."""
    destination = destination or {}
    dtype = destination.get("destination_type", DestinationType.NONE)
    open_in_new_tab = bool(destination.get("open_in_new_tab", False))
    url = None

    if dtype == DestinationType.CATEGORY:
        from apps.catalog.models import Category

        url = _category_url(store, destination.get("destination_id"), Category)
    elif dtype == DestinationType.PRODUCT:
        from apps.catalog.models import Product

        url = _product_url(store, destination.get("destination_id"), Product)
    elif dtype == DestinationType.BRAND:
        from apps.catalog.models import Brand

        url = _brand_url(store, destination.get("destination_id"), Brand)
    elif dtype == DestinationType.COLLECTION:
        from apps.catalog.models import MerchantCollection

        url = _collection_url(store, destination.get("destination_id"), MerchantCollection)
    elif dtype == DestinationType.EXTERNAL:
        raw_url = (destination.get("destination_external_url") or "").strip()
        url = raw_url or None

    is_external = dtype == DestinationType.EXTERNAL
    return {
        "url": url,
        "open_new_tab": open_in_new_tab,
        "rel": "noopener noreferrer" if (is_external and open_in_new_tab) else "",
    }


def _category_url(store, pk, Category):
    if not pk:
        return None
    try:
        category = Category.objects.get(pk=pk, store=store, is_active=True)
    except Category.DoesNotExist:
        return None
    return reverse("catalog:product-list") + f"?category={category.slug}"


def _product_url(store, pk, Product):
    if not pk:
        return None
    try:
        product = Product.objects.get(pk=pk, store=store)
    except Product.DoesNotExist:
        return None
    return reverse("catalog:product-detail", args=[product.slug])


def _brand_url(store, pk, Brand):
    if not pk:
        return None
    try:
        brand = Brand.objects.get(pk=pk, store=store, is_active=True)
    except Brand.DoesNotExist:
        return None
    return reverse("catalog:product-list") + f"?brand={brand.slug}"


def _collection_url(store, pk, MerchantCollection):
    if not pk:
        return None
    try:
        collection = MerchantCollection.objects.get(pk=pk, store=store, is_active=True)
    except MerchantCollection.DoesNotExist:
        return None
    return reverse("catalog:collection-detail", args=[collection.slug])


# ---------------------------------------------------------------- Media Asset cleanup (Phase 0.5)
#
# Explicit service function, deliberately NOT a Django signal (post_delete/
# pre_delete) — per the Phase 0.5 brief: "avoid fragile Django signals that
# delete files blindly on row deletion; prefer an explicit asset cleanup
# service." A signal fired on every Placement delete would have no easy way
# to express "only delete the physical file if truly nothing else still
# needs it" without duplicating this exact same reference check anyway —
# an explicit, callable function keeps that decision visible at every call
# site instead of hidden in signal-dispatch order.


def delete_media_asset_if_unreferenced(asset) -> bool:
    """اگر ``asset`` دیگر توسط هیچ Placementی (در هیچ نسخه‌ای — Published،
    Draft یا بایگانی‌شده) ارجاع نمی‌شود، خودِ ردیف را (و فایلِ فیزیکی‌اش را،
    فقط پس از commitِ موفقِ تراکنش) حذف می‌کند و ``True`` برمی‌گرداند.

    اگر هنوز حداقل یک Placement به آن ارجاع می‌دهد، **هیچ کاری نمی‌کند** و
    ``False`` برمی‌گرداند — قانونِ حیاتیِ Phase 0.5: هرگز فایلِ فیزیکیِ
    زیرِ یک asset را حذف نکن اگر Placementِ دیگری (مثلاً نسخه‌ی Published)
    هنوز به همان ردیف اشاره می‌کند.

    ``asset`` می‌تواند ``None`` باشد (مثلاً وقتی Placementِ حذف‌شده هنوز از
    قبل از Phase 0.5 است و هیچ FKِ assetای نداشت) — در این حالت بی‌صدا
    ``False`` برمی‌گرداند؛ فراخوان مسئولِ رفتارِ fallback (حذفِ مستقیمِ
    فایلِ قدیمی از طریقِ نامِ فایل) است، نه این تابع."""
    if asset is None:
        return False
    if asset.is_referenced():
        return False

    from django.db import transaction

    file_name = asset.image.name if asset.image else None
    storage = asset.image.storage if asset.image else None
    asset.delete()

    if file_name and storage:
        def _cleanup():
            if storage.exists(file_name):
                storage.delete(file_name)

        transaction.on_commit(_cleanup)
    return True
