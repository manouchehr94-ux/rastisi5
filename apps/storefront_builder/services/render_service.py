"""رندر یک نسخه‌ی چیدمان (Draft یا منتشرشده) به فهرستی از بخش‌های آماده‌ی نمایش.

این ماژول تنها نقطه‌ی مشترک بین پیش‌نمایش ادیتور (Draft) و صفحه اصلی عمومی
(نسخه‌ی منتشرشده) است — دقیقاً همان چیزی که تصمیم کاربر می‌خواهد: «Public
storefront must never read the editable draft» یعنی هر دو مسیر از همین
رندرکننده استفاده می‌کنند اما همیشه با یک ``StorefrontLayoutVersion`` مشخص
که فراخوان (view) آن را انتخاب کرده — پیش‌نمایش version=draft، صفحه‌ی عمومی
version=published — نه خودِ این سرویس هرگز تصمیم نمی‌گیرد کدام نسخه.

هر بخش با استفاده از سرویس‌های *موجود* catalog/content داده می‌گیرد — نه
بازنویسیِ قوانینِ «قابل‌مشاهده بودن» — دقیقاً همان الگویی که
``apps.catalog.views.home`` از قبل استفاده می‌کند.
"""

from __future__ import annotations

from apps.catalog.models import Brand, Category
from apps.catalog.services.product_publish_service import storefront_listing_products
from apps.content.models import HeroSlide, PromotionalBanner
from apps.orders.services import best_seller_service

from ..section_registry import UnknownSectionTypeError, get_definition
from . import section_data_service

TILE_CLASSES = ["t1", "t2", "t3"]


def _hero_banner_context(store, section):
    slides = HeroSlide.objects.filter(store=store, is_active=True).select_related(
        "destination_category", "destination_product", "destination_brand",
    ).order_by("display_order", "id")
    return {"hero_slides": slides}


def _image_slider_context(store, section):
    return _hero_banner_context(store, section)


def _single_banner_context(store, section):
    banners = PromotionalBanner.objects.filter(store=store, is_active=True).select_related(
        "destination_category", "destination_product", "destination_brand",
    ).order_by("display_order", "id")[:1]
    return {"banners": banners}


def _multi_banner_context(store, section):
    banners = PromotionalBanner.objects.filter(store=store, is_active=True).select_related(
        "destination_category", "destination_product", "destination_brand",
    ).order_by("display_order", "id")
    return {"banners": banners}


def _category_grid_context(store, section):
    top_categories = list(
        Category.objects.filter(store=store, parent__isnull=True, is_active=True).order_by("order", "name")
    )
    return {
        "tiles": list(zip(top_categories[:3], TILE_CLASSES)),
        "cream_category": top_categories[3] if len(top_categories) > 3 else None,
        "top_categories": top_categories,
    }


def _newest_products_context(store, section):
    products = (
        storefront_listing_products(store).select_related("brand").prefetch_related("images")
        .order_by("-created_at")[:8]
    )
    return {"products": products}


def _best_sellers_context(store, section):
    """پرفروش‌ترین‌هایِ واقعی — از ``best_seller_service`` (محاسبه‌ی زنده
    از OrderItem)، **نه** ``Product.sold_count`` که هیچ writer‌ای ندارد
    (به مستندسازیِ ``best_seller_service`` مراجعه شود). ``pk__in`` ترتیبِ
    رتبه را حفظ نمی‌کند، پس فهرست دستی طبقِ همان ترتیبِ رتبه‌بندی بازسازی
    می‌شود (همان الگویِ ``collection_products_add``ی فازِ B)."""
    product_ids = best_seller_service.best_selling_product_ids(store, limit=8)
    if not product_ids:
        return {"products": []}
    products_by_id = {
        p.pk: p
        for p in storefront_listing_products(store).filter(pk__in=product_ids)
        .select_related("brand").prefetch_related("images")
    }
    products = [products_by_id[pid] for pid in product_ids if pid in products_by_id]
    return {"products": products}


def _discounted_products_context(store, section):
    products = (
        storefront_listing_products(store).select_related("brand").prefetch_related("images")
        .filter(discount_percent__gt=0).order_by("-discount_percent")[:6]
    )
    return {"products": products}


def _amazing_offers_context(store, section):
    from django.utils import timezone
    from datetime import timedelta

    product = (
        storefront_listing_products(store).filter(discount_percent__gt=0)
        .order_by("-discount_percent").first()
    )
    return {"product": product, "deadline": (timezone.now() + timedelta(hours=8)).isoformat()}


def _featured_products_context(store, section):
    # هیچ فیلد is_featured‌ای در Product وجود ندارد (شکاف تأییدشده در گزارش
    # ممیزی) — تا زمانی که آن قابلیت واقعاً ساخته شود، این بخش از جدیدترین‌ها
    # استفاده می‌کند تا هرگز داده‌ی جعلی/ثابت نشان ندهد.
    return _newest_products_context(store, section)


def _brand_carousel_context(store, section):
    brands = Brand.objects.filter(store=store, is_active=True).order_by("sort_order", "name")
    return {"brands": brands}


def _category_context_for_promo_cards(store, section):
    categories = Category.objects.filter(store=store, is_active=True).order_by("order", "name")[:4]
    return {"categories": categories}


def _static_context(store, section):
    return {}


def _product_section_context(store, section):
    """برخلافِ همه‌ی builderهایِ دیگرِ این فایل، این یکی به تنظیماتِ
    خاصِ همین section (``data_source``/``source_id``/``product_ids``)
    وابسته است — پس در ``PER_INSTANCE_SECTION_KEYS`` زیر ثبت شده تا
    ``build_render_items`` آن را برایِ هر نمونه جداگانه محاسبه کند، نه
    یک‌بار برایِ کلِ section_key (بازنویسی‌شدن با کش، دقیقاً همان باگی
    که این پرچم برایِ جلوگیری از آن اضافه شده)."""
    products, view_all_url = section_data_service.resolve_products(store, section.settings or {})
    return {"products": products, "view_all_url": view_all_url}


#: کلیدهایی که context builder‌شان به تنظیماتِ خودِ همان نمونه‌ی section
#: وابسته است (نه فقط به store) — برایِ این‌ها، کشِ سطح-تابعِ
#: ``build_render_items`` باید per-instance باشد، وگرنه دو نمونه‌ی
#: تکرارشده (duplicable) با تنظیماتِ متفاوت (مثلاً دو کالکشنِ متفاوت)
#: محتوایِ یکسان (نمونه‌ی اول) نشان می‌دهند.
PER_INSTANCE_SECTION_KEYS = {"product_section"}


_CONTEXT_BUILDERS = {
    "announcement_bar": _static_context,
    "hero_banner": _hero_banner_context,
    "image_slider": _image_slider_context,
    "single_banner": _single_banner_context,
    "multi_banner": _multi_banner_context,
    "category_grid": _category_grid_context,
    "featured_products": _featured_products_context,
    "newest_products": _newest_products_context,
    "best_sellers": _best_sellers_context,
    "discounted_products": _discounted_products_context,
    "amazing_offers": _amazing_offers_context,
    "brand_carousel": _brand_carousel_context,
    "promo_cards": _category_context_for_promo_cards,
    "rich_text": _static_context,
    "image_text": _static_context,
    "product_section": _product_section_context,
    "trust_features": _static_context,
}


def build_render_items(version, store) -> list[dict]:
    """فهرست بخش‌های فعالِ یک نسخه، هرکدام با template_name + context آماده.

    بخش‌هایی با section_key ناشناخته (مثلاً از یک نسخه‌ی قدیمی‌تر که آن نوع
    را دیگر پشتیبانی نمی‌کند) بی‌صدا حذف می‌شوند — پیش‌نمایش/صفحه هرگز crash
    نمی‌کند.

    بهینه‌سازی کوئری: اکثرِ توابعِ ``_CONTEXT_BUILDERS`` به تنظیماتِ
    نمونه‌ی خاصِ یک section وابسته نیستند (فقط به ``store``) — پس اگر
    تاجر یک نوع section را چند بار تکرار کند (قابلیت پشتیبانی‌شده،
    ``duplicable=True``)، نتیجه‌ی کوئری برای همان section_key در یک بار
    رندر همیشه یکسان است و کش سطح-تابع زیر این کوئری‌های تکراری را در یک
    درخواست حذف می‌کند. استثنا: کلیدهایِ ``PER_INSTANCE_SECTION_KEYS``
    (فعلاً فقط ``product_section``) که تنظیماتِ per-instance دارند
    (مثلاً کالکشنِ متفاوت در هر نمونه) — برایِ این‌ها کش با
    ``(section_key, section.pk)`` کلیددهی می‌شود، نه فقط section_key، تا
    نمونه‌ی دوم محتوایِ نمونه‌ی اول را «قرض» نگیرد. این یک لایه‌ی کش
    خارجی/persistent نیست (که برای این ویو، همیشه باید Draft زنده را
    نشان دهد، خطر بازگشت داده‌ی کهنه دارد) — فقط حذفِ کوئریِ تکراری در
    یک درخواست."""
    items = []
    context_cache: dict = {}
    for section in version.sections.filter(is_active=True).order_by("order", "id"):
        try:
            definition = get_definition(section.section_key)
        except UnknownSectionTypeError:
            continue
        cache_key = (
            (section.section_key, section.pk)
            if section.section_key in PER_INSTANCE_SECTION_KEYS
            else section.section_key
        )
        if cache_key not in context_cache:
            builder = _CONTEXT_BUILDERS.get(section.section_key, _static_context)
            context_cache[cache_key] = builder(store, section)
        context = dict(context_cache[cache_key])
        context["section"] = section
        context["settings"] = section.settings or {}
        items.append({
            "section": section,
            "template_name": definition.template_name,
            "label_fa": definition.label_fa,
            "context": context,
        })
    return items
