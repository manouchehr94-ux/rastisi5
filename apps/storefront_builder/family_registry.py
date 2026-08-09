"""Family Registry — دقیقاً همان الگویِ ``section_registry.py``/
``appearance_registry.py``: یک دیکشنریِ ثابتِ پایتونی، پلتفرم‌محور،
Store-agnostic. تعریفِ هر «خانواده‌ی قالب» اینجا زندگی می‌کند؛ انتخابِ
مرچنت (کدام Family/Preset فعال است) در
``StorefrontLayoutVersion.appearance_config`` ذخیره می‌شود (Store-owned،
Draft/Publish-aware) — دقیقاً همان تفکیکِ مسئولیتی که
``appearance_registry.TEMPLATE_REGISTRY``/``appearance_config`` از قبل دارد.

چرا این از ``appearance_registry.TEMPLATE_REGISTRY`` مستقل است، نه گسترشِ
آن (تصمیمِ مالک، Q-01 — ``docs/template-references/live-audit/10_OWNER_DECISION_LOG.md``):
یک ``TemplateDefinition`` فقط توکن‌هایِ CSS (رنگ/فونت/گردی/تراکم/حرکت) را
رویِ یک DOM *مشترک* تغییر می‌دهد. یک ``FamilyDefinition`` DOM/Renderer
واقعاً متفاوتی برایِ هدر/ناوبری/هیرو/دسته‌بندی/کارتِ محصول/صفحه‌ی
محصول/فوتر انتخاب می‌کند. هر ۱۰ Template و ۲۰ Palette موجود بدونِ تغییرِ
مخرب باقی می‌مانند؛ یک Store در هر لحظه یا یک Templateِ قدیمی (DOMِ
مشترک) یا یک Familyِ جدید (DOMِ اختصاصی) را برایِ *ساختار* انتخاب کرده —
هرگز هر دو همزمان (نگاه کنید به ``services/layout_service.validate_appearance_config``
و ``views.storefront_appearance_editor`` برایِ منطقِ انحصارِ متقابل).

Preset (سطحِ بینِ Family و Palette، تصمیمِ مالک Q-02) در
``preset_registry.py`` تعریف شده، نه اینجا."""

from __future__ import annotations

import dataclasses


@dataclasses.dataclass(frozen=True)
class FamilyDefinition:
    slug: str
    name_fa: str
    description_fa: str
    #: شناسه‌ی هرکدام مسیرِ کاملِ یک partial واقعی است (نه یک کلیدِ انتزاعی
    #: که جایی دیگر نگاشت شود) — ``{% include SHOP_FAMILY.header_variant %}``
    #: مستقیماً همین رشته را include می‌کند؛ تنها نقطه‌ی انتخاب Renderer،
    #: دقیقاً طبقِ الزامِ صریحِ مالک («Registry/Strategy، نه if/elif پراکنده»).
    header_variant: str
    hero_variant: str
    category_variant: str
    footer_variant: str
    product_card_variant: str
    product_page_variant: str
    #: Presetِ پیش‌فرضِ امنِ این Family (``preset_registry.PRESET_REGISTRY``)
    #: — انتخابِ این Family به‌تنهایی باید فوراً یک نتیجه‌ی کامل و معتبر
    #: بدهد (تصمیمِ مالک، بندِ ۱۱ تصمیمِ جامع).
    default_preset_slug: str
    schema_version: int = 1
    #: Rendererِ اختیاریِ «حالتِ کمپین» کارتِ محصول — فقط Familyهایی که
    #: واقعاً بیش از یک حالت دارند (تصمیمِ مالک Q-09: امروز فقط Heritage
    #: Premium) این را مقدار می‌دهند؛ بقیه None می‌مانند و ``card_mode``
    #: هر Section (اگر مرچنت آن را «campaign» بگذارد) بی‌اثر می‌ماند.
    product_card_campaign_variant: str | None = None
    #: چیدمانِ پیش‌فرضِ واقعیِ صفحه‌ی اصلیِ همین Family — ترتیب و نوعِ
    #: Sectionهایی که با انتخابِ *فقط همین Family* (بدونِ هیچ تنظیمِ
    #: دستیِ دیگر) باید ساخته شوند (تصمیمِ مالک، مشکلِ ۳: «تغییرِ Family
    #: باید پیش‌فرضِ واقعیِ همان Family را بارگذاری کند»، نه چیدمانِ
    #: Familyِ قبلی را نگه دارد). دقیقاً همان الگویِ
    #: ``bootstrap_service.build_industry_default_sections`` برایِ قالبِ
    #: صنف — کلیدهایِ نامعتبر بی‌صدا کنار گذاشته می‌شوند.
    default_section_keys: tuple = ()
    #: فقط برایِ گالریِ انتخابِ Family در Builder — بدونِ اثرِ رفتاری.
    swatch: tuple = ("#6D28D9", "#FF4D77", "#FFFFFF")


FAMILY_REGISTRY: dict[str, FamilyDefinition] = {}


def register_family(definition: FamilyDefinition) -> None:
    FAMILY_REGISTRY[definition.slug] = definition


def get_family(slug: str | None) -> FamilyDefinition | None:
    if not slug:
        return None
    return FAMILY_REGISTRY.get(slug)


def list_families() -> list[FamilyDefinition]:
    return list(FAMILY_REGISTRY.values())


# ------------------------------------------------------------- خانواده‌ها
#
# هر خانواده فقط وقتی اینجا ثبت می‌شود که Rendererهای واقعی‌اش (هدر/هیرو/
# دسته‌بندی/کارت/صفحه‌ی محصول/فوتر) ساخته و تست شده باشند — یک Family در
# گالریِ مرچنت هرگز placeholder نیست (طبقِ الزامِ صریحِ کار).

register_family(FamilyDefinition(
    slug="modern_fashion",
    name_fa="مد امروز",
    description_fa="فروشگاه مد با هدر جست‌وجو-محور، هیرو تصویری، کارت محصول ۹:۱۲ با Wishlist و چیدمان قیمت/عنوان جداشده.",
    header_variant="storefront_builder/partials/families/modern_fashion/header.html",
    hero_variant="storefront_builder/partials/families/modern_fashion/hero.html",
    category_variant="storefront_builder/partials/families/modern_fashion/category.html",
    footer_variant="storefront_builder/partials/families/modern_fashion/footer.html",
    product_card_variant="catalog/partials/product_cards/fashion_portrait_gallery.html",
    product_page_variant="catalog/partials/product_pages/modern_fashion.html",
    default_preset_slug="modern_fashion_default",
    default_section_keys=(
        "hero_banner", "category_grid", "newest_products", "best_sellers",
        "discounted_products", "trust_features",
    ),
    swatch=("#FCBD15", "#FF0080", "#FFFFFF"),
))

register_family(FamilyDefinition(
    slug="artisan_editorial",
    name_fa="روایت هنر",
    description_fa="فروشگاه صنایع‌دستی/داستان‌محور با هدر آرام تک‌ردیفه، هیروی تحریریه‌ایِ لبه‌تیز، کارتِ محصول با متادیتای اختیاریِ سازنده/منطقه.",
    header_variant="storefront_builder/partials/families/artisan_editorial/header.html",
    hero_variant="storefront_builder/partials/families/artisan_editorial/hero.html",
    category_variant="storefront_builder/partials/families/artisan_editorial/category.html",
    footer_variant="storefront_builder/partials/families/artisan_editorial/footer.html",
    product_card_variant="catalog/partials/product_cards/artisan_story_card.html",
    product_page_variant="catalog/partials/product_pages/artisan_editorial.html",
    default_preset_slug="artisan_editorial_default",
    # مرجع (deeyarstore.com) بعد از هیرو (که خودش موزائیکِ دسته‌ها را در
    # دل دارد — نگاه کنید به hero.html) مستقیماً به فهرستِ محصولات می‌رود؛
    # category_grid جداگانه ندارد.
    default_section_keys=("hero_banner", "newest_products", "best_sellers", "trust_features"),
    swatch=("#888210", "#EFEADF", "#3B2923"),
))

register_family(FamilyDefinition(
    slug="nordic_living",
    name_fa="خانه آرام",
    description_fa="فروشگاه خانه و دکور Search-first با هدر سه‌ردیفه، هیروی خنثیِ دایره‌ای، کارتِ محصول با Crossfade تصویرِ دوم و Action Rail.",
    header_variant="storefront_builder/partials/families/nordic_living/header.html",
    hero_variant="storefront_builder/partials/families/nordic_living/hero.html",
    category_variant="storefront_builder/partials/families/nordic_living/category.html",
    footer_variant="storefront_builder/partials/families/nordic_living/footer.html",
    product_card_variant="catalog/partials/product_cards/catalog_second_image.html",
    product_page_variant="catalog/partials/product_pages/nordic_living.html",
    default_preset_slug="nordic_living_default",
    # طبقِ خودِ category.html این Family: دسترسیِ دسته‌بندی از طریقِ
    # Mega-menuِ هدر است، نه یک Sectionِ جداگانه در صفحه‌ی اصلی.
    default_section_keys=("hero_banner", "newest_products", "best_sellers", "trust_features"),
    swatch=("#183E85", "#FFDB01", "#F2F2F2"),
))

register_family(FamilyDefinition(
    slug="heritage_premium",
    name_fa="پرمیوم اصیل",
    description_fa="فروشگاه پرمیوم و تصویرمحور با هدر آرام، هیروی کمپینِ تمام‌عرض، دسته‌بندیِ پرتره‌ای، و دو حالتِ کارتِ محصول (استاندارد/کمپین).",
    header_variant="storefront_builder/partials/families/heritage_premium/header.html",
    hero_variant="storefront_builder/partials/families/heritage_premium/hero.html",
    category_variant="storefront_builder/partials/families/heritage_premium/category.html",
    footer_variant="storefront_builder/partials/families/heritage_premium/footer.html",
    product_card_variant="catalog/partials/product_cards/premium_portrait.html",
    product_card_campaign_variant="catalog/partials/product_cards/premium_campaign.html",
    product_page_variant="catalog/partials/product_pages/heritage_premium.html",
    default_preset_slug="heritage_premium_default",
    default_section_keys=(
        "hero_banner", "category_grid", "newest_products", "best_sellers",
        "discounted_products", "trust_features",
    ),
    swatch=("#07705E", "#DDB475", "#F1EBE1"),
))

register_family(FamilyDefinition(
    slug="vibrant_catalog",
    name_fa="کاتالوگ رنگی",
    description_fa="فروشگاه پرتراکم و قیمت‌محور با هدر سه‌لایه، هیرویِ Promo Dashboard چندتایلی، دسته‌بندیِ آیکونیِ سریع، کارتِ محصولِ ۱:۱ وسط‌چین.",
    header_variant="storefront_builder/partials/families/vibrant_catalog/header.html",
    hero_variant="storefront_builder/partials/families/vibrant_catalog/hero.html",
    category_variant="storefront_builder/partials/families/vibrant_catalog/category.html",
    footer_variant="storefront_builder/partials/families/vibrant_catalog/footer.html",
    product_card_variant="catalog/partials/product_cards/square_centered_commerce.html",
    product_page_variant="catalog/partials/product_pages/vibrant_catalog.html",
    default_preset_slug="vibrant_catalog_default",
    default_section_keys=(
        "hero_banner", "category_grid", "newest_products", "best_sellers",
        "discounted_products", "amazing_offers", "trust_features",
    ),
    swatch=("#FD445D", "#FFE6EB", "#F4F5F9"),
))
