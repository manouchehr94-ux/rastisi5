"""مهاجرت غیرمخرب فروشگاه‌های موجود — تولید یک Draft اولیه که دقیقاً منعکس‌کننده‌ی
صفحه اصلی قدیمی (hard-coded) هر فروشگاه است، نه یک بوم خالی.

طبق الزام صریح («هیچ فروشگاهی نباید صفحه اصلی خالی دریافت کند») و بخش ۲۳
گزارش ممیزی: این Draft **منتشر نمی‌شود** — پرچم
``StorefrontLayout.uses_visual_storefront_layout`` فقط با اولین Publish
دستیِ تاجر True می‌شود (در ``layout_service.publish``). تا آن لحظه،
``apps.catalog.views.home`` بدون تغییر از مسیر قدیمی رندر می‌کند.

منطق تشخیص بخش‌ها عمداً از سرویس‌های موجود catalog استفاده می‌کند
(``storefront_listing_products``) — نه بازنویسی قوانین «قابل‌مشاهده بودن».
"""

from __future__ import annotations

from apps.catalog.services.product_publish_service import storefront_listing_products
from apps.content.models import HeroSlide, PromotionalBanner

from .. import section_registry
from ..models import StorefrontLayoutVersion, StorefrontSection


def _defaults(section_key: str) -> dict:
    """تنظیماتِ پیش‌فرضِ کاملاً معتبر (نه ``{}`` خام) — طبقِ همان الگویی که
    ``build_industry_default_sections`` پایینِ همین فایل و
    ``storefront_section_add`` (``views.py``) از قبل استفاده می‌کنند.
    اهمیتِ این تفاوت: بعضی انواع section (مثلاً ``hero_banner``/
    ``image_slider``) پیش‌فرضِ True برایِ برخی کلیدها دارند (autoplay) —
    اگر ``settings`` خام ``{}`` ذخیره شود، تمپلیت‌ها هرگز نمی‌توانند بینِ
    «کلید غایب» و «صریحاً False» تمایز درست بگذارند (بر خلافِ
    ``responsive`` که پیش‌فرضش با «کلید غایب» تصادفاً یکی است)."""
    return section_registry.get_definition(section_key).default_settings()


def build_bootstrap_sections(store) -> list[dict]:
    """فهرست بخش‌های اولیه — دقیقاً همان چیزی که در حال حاضر روی صفحه اصلی
    قدیمی این Store رندر می‌شود (بخش ۲.۲ گزارش ممیزی)."""
    sections: list[dict] = []
    order = 0

    if HeroSlide.objects.filter(store=store, is_active=True).exists():
        sections.append({"section_key": "hero_banner", "order": order, "settings": _defaults("hero_banner")})
        order += 1

    if PromotionalBanner.objects.filter(store=store, is_active=True).exists():
        sections.append({"section_key": "multi_banner", "order": order, "settings": _defaults("multi_banner")})
        order += 1

    sections.append({"section_key": "category_grid", "order": order, "settings": _defaults("category_grid")})
    order += 1

    sections.append({"section_key": "newest_products", "order": order, "settings": _defaults("newest_products")})
    order += 1

    sections.append({"section_key": "best_sellers", "order": order, "settings": _defaults("best_sellers")})
    order += 1

    if storefront_listing_products(store).filter(discount_percent__gt=0).exists():
        sections.append({"section_key": "discounted_products", "order": order, "settings": _defaults("discounted_products")})
        order += 1

    sections.append({"section_key": "trust_features", "order": order, "settings": _defaults("trust_features")})
    order += 1

    return sections


def bootstrap_appearance_config(store) -> dict:
    """پیکربندیِ اولیه‌ی ظاهر برایِ اولین Draft — رنگ‌هایِ *زنده‌ی فعلیِ*
    ``ShopSettings`` را به‌عنوانِ ``color_overrides`` (بدونِ Palette
    نام‌دار) کپی می‌کند تا این مهاجرت هرگز ظاهرِ فروشگاه را عوض نکند
    (دقیقاً همان الزامِ «فروشگاه‌های موجود باید بدونِ تغییرِ بصری بمانند»
    — بخشِ ۴۰ کارِ کاربر). اگر ``ShopSettings`` هنوز provision نشده،
    پیش‌فرضِ ``appearance_registry.DEFAULT_COLORS`` (که خودش دقیقاً
    برابرِ پیش‌فرض‌هایِ مدلِ ShopSettings است) بی‌صدا استفاده می‌شود."""
    from apps.core.color_utils import mix_hex, safe_hex
    from apps.core.models import ShopSettings, ShopSettingsNotProvisionedError

    from .. import appearance_registry

    try:
        shop = ShopSettings.load(store=store)
    except ShopSettingsNotProvisionedError:
        return {"palette_slug": None, "color_overrides": {}}

    text = safe_hex(shop.text_color, "#241C3A")
    surface = safe_hex(shop.surface_color, "#FFFFFF")
    return {
        "palette_slug": None,
        "color_overrides": {
            "primary": safe_hex(shop.primary_color, "#6D28D9"),
            "secondary": safe_hex(shop.secondary_color, "#7C3AED"),
            "accent": safe_hex(shop.accent_color, "#FF4D77"),
            "background": safe_hex(shop.background_color, "#F7F5FC"),
            "surface": surface,
            "text": text,
            "muted": safe_hex(shop.muted_text_color, "#8B86A3"),
            "border": mix_hex(text, surface, 0.12),
        },
    }


def apply_bootstrap_content(version: StorefrontLayoutVersion, store) -> None:
    """بخش‌های اولیه را روی یک نسخه‌ی تازه‌ساخته (بدون بخش) اعمال می‌کند."""
    sections = build_bootstrap_sections(store)
    StorefrontSection.objects.bulk_create([
        StorefrontSection(
            version=version, section_key=s["section_key"],
            order=s["order"], settings=s["settings"],
        )
        for s in sections
    ])
    version.appearance_config = bootstrap_appearance_config(store)
    version.save(update_fields=["appearance_config"])


def build_industry_default_sections(store, industry_template) -> list[dict]:
    """چیدمان پیشنهادیِ صفحه اصلی یک صنف — از ``industry_template.default_section_keys``.

    کلیدهای نامعتبر/حذف‌شده از Section Registry بی‌صدا کنار گذاشته می‌شوند
    (هرگز کرش نمی‌کند)؛ اگر صنف هیچ کلید معتبری نداشت، به همان چیدمان
    پیش‌فرض عمومی (``build_bootstrap_sections``) برمی‌گردد تا هرگز یک
    Draft خالی ساخته نشود."""
    keys = list(getattr(industry_template, "default_section_keys", None) or [])
    valid_keys = [k for k in keys if section_registry.is_valid_section_key(k)]
    if not valid_keys:
        return build_bootstrap_sections(store)
    return [
        {"section_key": key, "order": order, "settings": section_registry.get_definition(key).default_settings()}
        for order, key in enumerate(valid_keys)
    ]


def apply_industry_content(version: StorefrontLayoutVersion, store, industry_template) -> None:
    """چیدمان پیشنهادیِ صنف را روی یک نسخه‌ی تازه‌ساخته (بدون بخش) اعمال می‌کند."""
    sections = build_industry_default_sections(store, industry_template)
    StorefrontSection.objects.bulk_create([
        StorefrontSection(
            version=version, section_key=s["section_key"],
            order=s["order"], settings=s["settings"],
        )
        for s in sections
    ])


def build_family_default_sections(family) -> list[dict]:
    """چیدمانِ پیش‌فرضِ واقعیِ همین Family (``family.default_section_keys``).

    دقیقاً همان الگویِ ``build_industry_default_sections`` — کلیدهایِ
    نامعتبر/حذف‌شده از Section Registry بی‌صدا کنار گذاشته می‌شوند؛ اگر
    Family هیچ کلیدِ معتبری نداشت (هنوز پیکربندی نشده)، فهرست خالی
    برمی‌گردد — Section بی‌معنا اضافه نمی‌شود."""
    keys = list(getattr(family, "default_section_keys", None) or [])
    valid_keys = [k for k in keys if section_registry.is_valid_section_key(k)]
    return [
        {"section_key": key, "order": order, "settings": section_registry.get_definition(key).default_settings()}
        for order, key in enumerate(valid_keys)
    ]


def apply_family_default_sections(version: StorefrontLayoutVersion, family) -> None:
    """چیدمانِ Draft فعلی را با چیدمانِ پیش‌فرضِ واقعیِ Familyِ تازه‌انتخاب‌شده
    جایگزین می‌کند (تصمیمِ مالک، مشکلِ ۳: «تغییرِ Family باید پیش‌فرضِ
    واقعیِ همان Family را بارگذاری کند»، نه چیدمانِ Familyِ قبلی را نگه
    دارد). فقط رکوردهایِ ``StorefrontSection`` همینِ نسخه (Draft) حذف
    می‌شوند — محصولات/دسته‌بندی‌ها/اطلاعاتِ فروشگاه/لوگو/سفارش‌ها/مشتریان
    هرگز اینجا لمس نمی‌شوند (مدل‌هایِ کاملاً مجزا در اپ‌هایِ دیگر). این
    عملیات مخربِ *صریحاً خواسته‌شده* روی چیدمانِ Draft است — تأییدِ کاربر
    پیش از فراخوانیِ این تابع، در view (نه اینجا) گرفته می‌شود، دقیقاً
    همان الگویِ ``storefront_apply_industry_layout``."""
    version.sections.all().delete()
    sections = build_family_default_sections(family)
    StorefrontSection.objects.bulk_create([
        StorefrontSection(
            version=version, section_key=s["section_key"],
            order=s["order"], settings=s["settings"],
        )
        for s in sections
    ])
