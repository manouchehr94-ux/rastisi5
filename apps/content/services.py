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
