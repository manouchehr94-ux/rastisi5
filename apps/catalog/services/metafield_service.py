"""خدماتِ ProductMetafield — ذخیره/بازیابی/حذفِ متادیتایِ محصول از رویِ
POST data فرمِ کالا. هرگز مستقیماً از request خام نمی‌خواند — view ابتدا
داده‌ها را extract می‌کند و اینجا می‌فرستد.

تمامِ عملیات‌ها Store-scoped هستند (از طریقِ product.store) —
ایزولاسیونِ چندمستأجری از طریقِ owner‌بودنِ Product تضمین می‌شود."""

from __future__ import annotations

from apps.catalog.models import ProductMetafield, METAFIELD_NS_SIZE_GUIDE, METAFIELD_NS_ARTISAN


def save_product_metafields_from_form(product, *, size_guide_content: str = "",
                                       maker: str = "", region: str = "") -> None:
    """متادیتاهایِ فرم‌محور را ذخیره/بروزرسانی/حذف می‌کند.

    هر فیلد: اگر خالی باشد، metafield حذف می‌شود (get_or_create نمی‌شود).
    اگر مقدار داشته باشد، upsert می‌شود."""
    _upsert_or_delete(product, METAFIELD_NS_SIZE_GUIDE, "chart_html", size_guide_content)
    _upsert_or_delete(product, METAFIELD_NS_ARTISAN, "maker", maker)
    _upsert_or_delete(product, METAFIELD_NS_ARTISAN, "region", region)


def get_product_metafield_values(product) -> dict:
    """مقادیرِ فعلیِ متادیتاهایِ فرم‌محور — برایِ pre-fill فرمِ ویرایش."""
    metafields = {
        (mf.namespace, mf.key): mf.value_text
        for mf in ProductMetafield.objects.filter(product=product)
    }
    return {
        "size_guide_content": metafields.get((METAFIELD_NS_SIZE_GUIDE, "chart_html"), ""),
        "maker": metafields.get((METAFIELD_NS_ARTISAN, "maker"), ""),
        "region": metafields.get((METAFIELD_NS_ARTISAN, "region"), ""),
    }


def _upsert_or_delete(product, namespace: str, key: str, value: str) -> None:
    """اگر value خالی باشد، حذف. اگر مقدار داشته باشد، upsert."""
    value = (value or "").strip()
    if not value:
        ProductMetafield.objects.filter(product=product, namespace=namespace, key=key).delete()
    else:
        ProductMetafield.objects.update_or_create(
            product=product, namespace=namespace, key=key,
            defaults={"value_text": value},
        )
