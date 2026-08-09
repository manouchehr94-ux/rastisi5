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
    swatch=("#FCBD15", "#FF0080", "#FFFFFF"),
))
