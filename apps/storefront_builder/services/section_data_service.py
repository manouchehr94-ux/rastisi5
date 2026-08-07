"""حلِ منبعِ داده‌یِ «بخشِ محصول» (فازِ C) — تنها نقطه‌ی ورودیِ مجاز برایِ
تبدیلِ تنظیماتِ اعتبارسنجی‌شده‌یِ یک section (خروجیِ
``section_registry._validate_product_section_settings``) به فهرستِ واقعیِ
Product برایِ رندر.

اعتبارسنجیِ مالکیتِ Store برایِ ارجاعات (``source_id``/``product_ids``) —
که در ``section_registry.py`` عمداً انجام نشده (به مستندسازیِ بالایِ آن
فایل مراجعه شود) — همینجا انجام می‌شود: هر ارجاعِ حذف‌شده/غیرفعال/متعلق
به فروشگاهِ دیگر بی‌صدا به «بدون کالا» تبدیل می‌شود (fail closed، بدون
کرش) — دقیقاً همان فلسفه‌ای که ``build_render_items`` برایِ section_key
ناشناخته دارد: صفحه هرگز نباید به‌خاطرِ یک ارجاعِ کهنه/نامعتبر خراب شود."""

from __future__ import annotations

from django.urls import reverse

from apps.catalog.services import collection_service


def _reorder_by_ids(products_by_id: dict, ordered_ids: list) -> list:
    return [products_by_id[pid] for pid in ordered_ids if pid in products_by_id]


def _resolve_collection(store, settings: dict):
    source_id = settings.get("source_id")
    if not source_id:
        return [], None
    try:
        collection = collection_service.get_scoped_collection(store, source_id)
    except collection_service.CollectionNotFoundError:
        return [], None
    if not collection.is_active:
        return [], None

    limit = settings["item_limit"]
    items = collection_service.collection_visible_items(collection, store)[:limit]
    products = [item.product for item in items]
    view_all_url = reverse("catalog:collection-detail", args=[collection.slug])
    return products, view_all_url


_RESOLVERS = {
    "collection": _resolve_collection,
}


def resolve_products(store, settings: dict) -> tuple[list, str | None]:
    """فهرستِ Product نهایی (به ترتیبِ صحیح، حداکثر ``item_limit`` عدد) و
    آدرسِ اختیاریِ «مشاهده همه» را برایِ ``data_source`` این section
    برمی‌گرداند. برایِ منبعِ نامعتبر/هنوز-پیاده‌سازی‌نشده، فهرستِ خالی
    (نه خطا) — همان قراردادِ fail-closedِ بالا."""
    resolver = _RESOLVERS.get(settings.get("data_source"))
    if resolver is None:
        return [], None
    return resolver(store, settings)
