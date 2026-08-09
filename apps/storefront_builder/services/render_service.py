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

from ..section_registry import (
    UnknownSectionTypeError,
    default_brand_carousel_settings,
    default_category_grid_settings,
    default_quick_links_settings,
    get_definition,
)
from . import section_data_service

TILE_CLASSES = ["t1", "t2", "t3"]


_DESTINATION_SELECT_RELATED = (
    "destination_category", "destination_product", "destination_brand", "destination_collection",
)


def _scoped_hero_slides(store, section):
    """اسلایدهای *مخصوصِ همین نمونه* section (اگر مرچنت از داخل سازنده
    بصری برایِ آن اسلاید اضافه کرده) — اگر این section هیچ اسلایدِ
    اختصاصی نداشت، به اسلایدهای سراسریِ فروشگاه (section=None، رفتارِ
    قدیمیِ پیش از این چکپوینت) برمی‌گردد. این دقیقاً همان مکانیزمی است که
    اجازه می‌دهد دو نمونه‌ی اسلایدر مستقل (با اسلایدهای متفاوت) وجود
    داشته باشند، بدون این‌که فروشگاه‌های قدیمی که هرگز این ویژگی را لمس
    نکرده‌اند رفتارشان تغییر کند."""
    scoped = HeroSlide.objects.filter(section=section, is_active=True).select_related(
        *_DESTINATION_SELECT_RELATED,
    ).order_by("display_order", "id")
    if scoped.exists():
        return scoped
    return HeroSlide.objects.filter(store=store, section__isnull=True, is_active=True).select_related(
        *_DESTINATION_SELECT_RELATED,
    ).order_by("display_order", "id")


def _hero_banner_context(store, section):
    from ..section_registry import default_slider_settings

    slider_settings = {**default_slider_settings(), **(section.settings or {})}
    return {
        "hero_slides": _scoped_hero_slides(store, section),
        "slider_settings": slider_settings,
        # فقط مصرف‌شونده توسط Familyهایی که زیرِ Hero یک ردیفِ بنرِ کوچک
        # می‌خواهند (مثلِ modern_fashion — نگاه کنید به گزارشِ
        # 11_REFERENCE_FIDELITY_GAP_ANALYSIS.md)؛ برای بقیه بی‌اثر است.
        "banners": _scoped_banners(store, section),
    }


def _image_slider_context(store, section):
    return _hero_banner_context(store, section)


def _scoped_banners(store, section):
    scoped = PromotionalBanner.objects.filter(section=section, is_active=True).select_related(
        *_DESTINATION_SELECT_RELATED,
    ).order_by("display_order", "id")
    if scoped.exists():
        return scoped
    return PromotionalBanner.objects.filter(store=store, section__isnull=True, is_active=True).select_related(
        *_DESTINATION_SELECT_RELATED,
    ).order_by("display_order", "id")


def _single_banner_context(store, section):
    return {"banners": _scoped_banners(store, section)[:1]}


def _multi_banner_context(store, section):
    return {"banners": _scoped_banners(store, section)}


def _category_grid_context(store, section):
    """چکپوینتِ ۱۱: اگر مرچنت صراحتاً دسته‌بندی انتخاب کرده باشد
    (``category_ids``)، دقیقاً همان‌ها به همان ترتیب نمایش داده می‌شوند —
    وگرنه (فروشگاهی که هنوز این تنظیمات را لمس نکرده) دقیقاً همان
    رفتارِ auto-pick قبل از این چکپوینت (۳+۱ دسته‌ی اولِ فعالِ سطحِ اول)
    بازتولید می‌شود. ``pk__in`` ترتیب را حفظ نمی‌کند، پس فهرستِ
    انتخاب‌شده دستی طبقِ همان ترتیبِ ذخیره‌شده بازسازی می‌شود (همان الگویِ
    ``_best_sellers_context``)."""
    category_ids = (section.settings or {}).get("category_ids") or []
    if category_ids:
        by_id = {
            c.pk: c for c in Category.objects.filter(store=store, pk__in=category_ids, is_active=True)
        }
        categories = [by_id[cid] for cid in category_ids if cid in by_id]
    else:
        categories = list(
            Category.objects.filter(store=store, parent__isnull=True, is_active=True).order_by("order", "name")
        )
    return {
        "tiles": list(zip(categories[:3], TILE_CLASSES)),
        "cream_category": categories[3] if len(categories) > 3 else None,
        "top_categories": categories,
        "category_grid_settings": {**default_category_grid_settings(), **(section.settings or {})},
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
    """چکپوینتِ ۱۱: همان الگویِ ``_category_grid_context`` — ``brand_ids``
    خالی یعنی رفتارِ auto (همه‌ی برندهایِ فعال) دست‌نخورده می‌ماند."""
    settings = {**default_brand_carousel_settings(), **(section.settings or {})}
    brand_ids = settings["brand_ids"]
    if brand_ids:
        by_id = {b.pk: b for b in Brand.objects.filter(store=store, pk__in=brand_ids, is_active=True)}
        brands = [by_id[bid] for bid in brand_ids if bid in by_id]
    else:
        brands = list(Brand.objects.filter(store=store, is_active=True).order_by("sort_order", "name"))

    view_all_url = None
    if settings["show_view_all"]:
        destination = (section.settings or {}).get("destination") or {}
        if destination.get("destination_type", "none") != "none":
            from apps.content.services import resolve_destination_setting

            resolved = resolve_destination_setting(store, destination)
            view_all_url = resolved["url"]

    return {"brands": brands, "brand_carousel_settings": settings, "view_all_url": view_all_url}


def _collection_tiles_context(store, section):
    """چکپوینتِ ۱۲: بخشِ جدید — خودِ MerchantCollectionها را نشان می‌دهد
    (نه کالاهایِ داخلشان). ``collection_ids`` خالی = همه‌ی کالکشن‌های
    فعال (ترتیبِ ایجاد، جدیدترین اول)."""
    from apps.catalog.models import MerchantCollection

    collection_ids = (section.settings or {}).get("collection_ids") or []
    if collection_ids:
        by_id = {
            c.pk: c for c in MerchantCollection.objects.filter(store=store, pk__in=collection_ids, is_active=True)
        }
        collections = [by_id[cid] for cid in collection_ids if cid in by_id]
    else:
        collections = list(
            MerchantCollection.objects.filter(store=store, is_active=True).order_by("-created_at")
        )
    # شمارشِ کالا با یک کوئریِ جمعی (annotate)، نه N+1 در تمپلیت
    from django.db.models import Count

    counts_qs = MerchantCollection.objects.filter(pk__in=[c.pk for c in collections]).annotate(item_count=Count("items"))
    counts_by_id = {row.pk: row.item_count for row in counts_qs}
    tiles = [{"collection": c, "item_count": counts_by_id.get(c.pk, 0)} for c in collections]
    return {"collection_tiles": tiles}


def _quick_links_context(store, section):
    """چکپوینتِ ۱۲: «دسترسی سریع» — یک Menuِ موجود (همان زیرساختِ
    Menu/MenuItem/Destinationِ ناوبریِ هدر/فوتر) را به‌شکلِ کارت‌هایِ
    بصری نشان می‌دهد؛ هیچ مدلِ لینکِ جدیدی ساخته نشده.

    ``Prefetch`` با یک queryset از پیش‌فیلترشده (نه ``prefetch_related``یِ
    ساده + یک ``.filter()`` دیگر رویِ ``menu.items`` بعداً) — وگرنه آن
    فیلترِ دوم یک کوئریِ کاملاً جدا اجرا می‌کرد و کشِ prefetch را بی‌اثر
    می‌گذاشت (همان الگویِ ``apps.content.context_processors.navigation_menus``)."""
    from django.db.models import Prefetch

    from apps.content.models import Menu, MenuItem
    from apps.content.services import resolve_destination_url

    settings = {**default_quick_links_settings(), **(section.settings or {})}
    menu_id = settings["menu_id"]
    items = []
    menu = None
    if menu_id:
        items_qs = MenuItem.objects.filter(is_active=True, parent__isnull=True).select_related(
            "destination_category", "destination_product", "destination_brand",
        ).order_by("display_order", "id")
        menu = Menu.objects.filter(store=store, pk=menu_id, is_active=True).prefetch_related(
            Prefetch("items", queryset=items_qs),
        ).first()
    if menu is not None:
        for menu_item in menu.items.all():
            url = resolve_destination_url(menu_item)
            if url:
                items.append({"title": menu_item.title, "url": url, "open_in_new_tab": menu_item.open_in_new_tab})
    return {"quick_link_items": items}


def _video_section_context(store, section):
    """چکپوینتِ ۱۲: از همان تشخیصِ ارائه‌دهنده/محاسبه‌ی embed_url که برایِ
    ویدیویِ کالا استفاده می‌شود عبور می‌کند (نه بازنویسیِ دوباره) — یک
    نمونه‌ی موقتِ (ذخیره‌نشده‌یِ) ``ProductVideo`` فقط برایِ عبور از همان
    منطق ساخته می‌شود."""
    video_url = (section.settings or {}).get("video_url") or ""
    if not video_url:
        return {"video_embed_url": None, "video_is_instagram": False, "video_permalink": None}

    from apps.catalog.models import ProductVideo
    from apps.catalog.services import product_video_service

    try:
        provider, _external_id = product_video_service.detect_provider_and_id(video_url)
    except product_video_service.ProductVideoError:
        return {"video_embed_url": None, "video_is_instagram": False, "video_permalink": None}

    temp_video = ProductVideo(provider=provider, url=video_url)
    if provider == ProductVideo.Provider.INSTAGRAM:
        return {"video_embed_url": None, "video_is_instagram": True,
                "video_permalink": product_video_service.instagram_permalink(temp_video)}
    return {"video_embed_url": product_video_service.embed_url(temp_video), "video_is_instagram": False, "video_permalink": None}


def _category_context_for_promo_cards(store, section):
    categories = Category.objects.filter(store=store, is_active=True).order_by("order", "name")[:4]
    return {"categories": categories}


def _static_context(store, section):
    return {}


def _resolved_destination_context(store, section):
    """بلوکِ ``destination`` این section (اگر داشته باشد) را به URL/تب‌جدید
    واقعی حل می‌کند — برایِ انواعی که در ``DESTINATION_AWARE_SECTION_KEYS``
    عضوند و لینکشان واقعاً «سطحِ خودِ section» است (نه per-slide/per-banner
    مثلِ hero/banner که مقصدشان داخلِ خودِ مدلِ ``HeroSlide``/
    ``PromotionalBanner`` است)."""
    destination = (section.settings or {}).get("destination") or {}
    if destination.get("destination_type", "none") == "none":
        return {"destination": {"url": None, "open_new_tab": False, "rel": ""}}

    from apps.content.services import resolve_destination_setting

    return {"destination": resolve_destination_setting(store, destination)}


def _product_section_context(store, section):
    """برخلافِ همه‌ی builderهایِ دیگرِ این فایل، این یکی به تنظیماتِ
    خاصِ همین section (``data_source``/``source_id``/``product_ids``)
    وابسته است — پس در ``PER_INSTANCE_SECTION_KEYS`` زیر ثبت شده تا
    ``build_render_items`` آن را برایِ هر نمونه جداگانه محاسبه کند، نه
    یک‌بار برایِ کلِ section_key (بازنویسی‌شدن با کش، دقیقاً همان باگی
    که این پرچم برایِ جلوگیری از آن اضافه شده)."""
    products, view_all_url = section_data_service.resolve_products(store, section.settings or {})
    destination = (section.settings or {}).get("destination") or {}
    if destination.get("destination_type", "none") != "none":
        from apps.content.services import resolve_destination_setting

        resolved = resolve_destination_setting(store, destination)
        if resolved["url"]:
            view_all_url = resolved["url"]
    return {"products": products, "view_all_url": view_all_url}


#: کلیدهایی که context builder‌شان به تنظیماتِ خودِ همان نمونه‌ی section
#: وابسته است (نه فقط به store) — برایِ این‌ها، کشِ سطح-تابعِ
#: ``build_render_items`` باید per-instance باشد، وگرنه دو نمونه‌ی
#: تکرارشده (duplicable) با تنظیماتِ متفاوت (مثلاً دو کالکشنِ متفاوت)
#: محتوایِ یکسان (نمونه‌ی اول) نشان می‌دهند.
PER_INSTANCE_SECTION_KEYS = {
    "product_section", "image_text", "hero_banner", "image_slider", "single_banner", "multi_banner",
    "category_grid", "brand_carousel", "collection_tiles", "quick_links", "video_section",
}


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
    "image_text": _resolved_destination_context,
    "product_section": _product_section_context,
    "trust_features": _static_context,
    "collection_tiles": _collection_tiles_context,
    "quick_links": _quick_links_context,
    "faq": _static_context,
    "testimonials": _static_context,
    "video_section": _video_section_context,
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
