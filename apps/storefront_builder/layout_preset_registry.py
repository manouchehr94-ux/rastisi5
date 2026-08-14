"""Layout Preset Registry — Phase 6: پیش‌تنظیمِ چندصفحه‌ایِ سازنده‌ی V2.

**این ماژول جایگزین/گسترشِ ``preset_registry.py`` نیست.** طبقِ تصمیمِ
مالک ۸ (``docs/architecture/STOREFRONT_BUILDER_V2_REUSE_MATRIX.md:35``)،
``preset_registry.py``/``family_registry.py`` منجمدند — هیچ ورودیِ تازه‌ای
به آن‌ها اضافه نمی‌شود. آن سیستم یک بسته‌یِ توکن *درونِ یک Family خاص*
است (``PresetDefinition.family_slug`` الزامی) و فقط صفحه‌ی اصلی را
می‌پوشاند. این ماژول یک مفهومِ کاملاً جدا و مستقل از Family است — یک
``LayoutPresetDefinition`` روی موتورِ یکتای Universal (همان چیزی که
Phaseهای ۰.۵ تا ۵ ساختند) کار می‌کند، هر ۶ نوع صفحه را می‌تواند بپوشاند،
و هرگز به یک Family خاص قفل نمی‌شود (طبقِ الزامِ صریحِ کار: «Preset X
should not automatically become Family X»).

Preset **داده** است، نه یک Renderer/Family جدید (spec §5.7: «A preset is
data, not a new family implementation»). اعمالِ آن هرگز:

- رنگ را تغییر نمی‌دهد (``palette_slug``/``color_overrides`` مستقلِ کاملاً
  جدا می‌مانند — تصمیمِ مالک: «Palette همیشه Global می‌ماند»؛ اینجا فقط
  یک Paletteِ *پیشنهادی* حمل می‌شود، نه یک قفل)؛
- شناسه‌ی محصول/دسته/کالکشنِ مشخصی را در جایی ذخیره نمی‌کند (طبقِ الزامِ
  صریحِ کار «Reference Safety» — نگاه کنید به Phase 6 Audit، بخشِ ۲۱)؛
- خارج از Draft چیزی را لمس نمی‌کند (اعمال، کاملاً وظیفه‌ی
  ``services/preset_service.py`` است، نه اینجا).

الگویِ این فایل عمداً همانِ الگویِ ``section_registry.py``/
``family_registry.py``/``appearance_registry.py``/``preset_registry.py``
است: یک دیکشنریِ ثابتِ پایتونی، Store-agnostic، بدونِ وابستگی به مدل/
دیتابیس (پس امن است در هر لحظه‌ای import شود، حتی پیش از آماده‌شدنِ
اپ‌هایِ Django) — طراحی‌شده/بازبینی‌شده توسطِ تیمِ پلتفرم، نه چیزی که
مرچنت بسازد.

اعتبارسنجیِ **شکلِ ترکیبِ section/page** (که فقط به ``section_registry``ی
کاملاً خالص وابسته است) همین‌جا، در زمانِ import انجام می‌شود — دقیقاً
همان فلسفه‌ی ``_finalize_registry``. اعتبارسنجیِ header/footer/appearance
(که به ``services/layout_service`` و از آن‌جا به مدل‌هایِ Django وابسته
است) عمداً اینجا انجام نمی‌شود — در ``services/preset_service.validate_layout_preset``
است، هم برایِ جلوگیری از هرگونه وابستگیِ چرخه‌ای، هم چون همان لایه دقیقاً
همان اعتبارسنج‌هایی را دارد که ادیتورِ Header/Footer/Appearance از قبل
مصرف می‌کند."""

from __future__ import annotations

import dataclasses

from . import section_registry


class InvalidLayoutPresetError(Exception):
    """یک ``LayoutPresetDefinition`` ساخته‌شده (کدِ پلتفرم، نه ورودیِ مرچنت)
    شکلِ نامعتبر دارد — همیشه در زمانِ import رخ می‌دهد، هرگز در زمانِ
    اجرا برایِ یک مرچنتِ واقعی (طبقِ الزامِ صریحِ کار: «Invalid built-in
    Presets should fail tests/startup validation rather than fail at
    runtime»)."""


@dataclasses.dataclass(frozen=True)
class PresetSectionEntry:
    """یک ردیفِ چیدمانِ پیشنهادیِ Preset برایِ یک section — دقیقاً همان شکلِ
    خروجیِ ``bootstrap_service.build_default_non_home_sections`` (بدونِ
    ``order`` صریح؛ ترتیب همانِ ترتیبِ فهرست است)."""

    section_key: str
    #: None یعنی «از ``default_settings()`` خودِ این نوع section استفاده
    #: کن» — اکثرِ Presetهای ساخته‌شده در این فاز از همین حالت استفاده
    #: می‌کنند (طبقِ الزامِ صریحِ کار: هرگز ID فروشگاه‌محور را در یک
    #: Preset سراسری Hard-code نکن). فقط اگر واقعاً لازم باشد یک مقدارِ
    #: enum-محورِ خنثی (مثلاً ``data_source: "newest"``) تغییر کند، یک
    #: دیکشنریِ *جزئی* اینجا می‌آید — ``validate_settings`` خودِ آن نوع،
    #: کلیدهایِ غایب را با پیش‌فرضِ امنِ خودشان پر می‌کند.
    settings: dict | None = None
    #: Phase 3 (Universal Storefront — V5 Golden Homepage) — عضویتِ ردیفِ
    #: ترکیبی (``row_service``/Phase 1 معماری). خالی (پیش‌فرض) یعنی
    #: section مستقل/عرضِ کامل — دقیقاً همان معنایی که خودِ مدل دارد؛ یک
    #: Preset که هرگز از ردیفِ ترکیبی استفاده نمی‌کند (اکثریتِ Presetهای
    #: قبل از این فاز) بدونِ هیچ تغییری همچنان معتبر می‌ماند.
    row_key: str = ""
    row_span: int = 12


@dataclasses.dataclass(frozen=True)
class LayoutPresetDefinition:
    key: str
    label_fa: str
    description_fa: str
    #: فقط کلیدهایِ ساختاریِ ``appearance_config`` (هرگز رنگ) — زیرمجموعه‌ای
    #: از: font/radius/button_radius/density/motion/type_scale/button_style/
    #: image_fit/image_hover/card_image_crossfade/card_image_zoom. کلیدِ
    #: غایب یعنی «دست‌نخورده بماند» (نه بازنشانی به پیش‌فرضِ پلتفرم) —
    #: منطقِ merge در ``preset_service.apply_preset`` است.
    appearance: dict = dataclasses.field(default_factory=dict)
    #: فقط یک *پیشنهاد* — طبقِ تصمیمِ مالک، Palette همیشه آزادانه توسطِ
    #: مرچنت قابل‌تغییر می‌ماند؛ اگر مرچنت از قبل Paletteای انتخاب کرده
    #: باشد، اعمالِ Preset آن انتخاب را بازنویسی نمی‌کند (نگاه کنید به
    #: ``preset_service.apply_preset``).
    default_palette_slug: str | None = None
    #: کلیدهایِ جزئیِ ``header_config``/``footer_config`` — دقیقاً همان
    #: قراردادِ ``layout_service.validate_header_config``/
    #: ``validate_footer_config``؛ کلیدِ غایب یعنی دست‌نخورده بماند
    #: (شاملِ ``announcement_text`` — یک Preset هرگز متنِ تبلیغاتیِ
    #: مرچنت را می‌نویسد/پاک نمی‌کند).
    header: dict | None = None
    footer: dict | None = None
    #: چیدمانِ پیشنهادیِ هرکدام از (حداکثر) شش نوع صفحه — کلیدهایِ
    #: ``section_registry.ALL_PAGE_TYPES``. یک ``page_type`` غایب یعنی
    #: «این Preset عمداً این صفحه را دست‌نخورده می‌گذارد» (طبقِ الزامِ
    #: صریحِ کار: «A preset may omit a page deliberately»).
    pages: dict[str, tuple[PresetSectionEntry, ...]] = dataclasses.field(default_factory=dict)
    #: ``None`` یعنی «با هر فروشگاهی روی پوسته‌ی Universal (V2) سازگار
    #: است» — Familyهای قدیمی هرگز از موتورِ V2 عبور نمی‌کنند، پس اصلاً
    #: مشمولِ این فهرست نیستند (طبقِ الزامِ صریحِ کار: «Preset X should
    #: not automatically become Family X» — اینجا هیچ کوپلینگِ ۱:۱ای
    #: با Family تعریف نشده، برخلافِ ``preset_registry.PresetDefinition``یِ
    #: منجمد).
    compatible_families: frozenset[str] | None = None


LAYOUT_PRESET_REGISTRY: dict[str, LayoutPresetDefinition] = {}


def register_layout_preset(definition: LayoutPresetDefinition) -> None:
    _validate_page_composition_shape(definition)
    LAYOUT_PRESET_REGISTRY[definition.key] = definition


def get_layout_preset(key: str) -> LayoutPresetDefinition | None:
    return LAYOUT_PRESET_REGISTRY.get(key)


def list_layout_presets() -> list[LayoutPresetDefinition]:
    return list(LAYOUT_PRESET_REGISTRY.values())


def _validate_page_composition_shape(definition: LayoutPresetDefinition) -> None:
    """اعتبارسنجیِ بخشِ section/page در زمانِ import — تنها به
    ``section_registry`` (کاملاً خالص) وابسته است، پس اینجا امن است.
    اعتبارسنجیِ appearance/header/footer در ``preset_service`` است (به
    ``layout_service`` نیاز دارد — نگاه کنید به docstring بالایِ فایل)."""
    for page_type, entries in definition.pages.items():
        if page_type not in section_registry.ALL_PAGE_TYPES:
            raise InvalidLayoutPresetError(
                f"Preset «{definition.key}»: نوعِ صفحه‌ی «{page_type}» ناشناخته است"
            )
        for entry in entries:
            if not section_registry.is_valid_section_key(entry.section_key):
                raise InvalidLayoutPresetError(
                    f"Preset «{definition.key}»: نوعِ section «{entry.section_key}» ناشناخته است"
                )
            if not section_registry.is_section_allowed_on_page(entry.section_key, page_type):
                raise InvalidLayoutPresetError(
                    f"Preset «{definition.key}»: section «{entry.section_key}» روی صفحه‌ی "
                    f"«{page_type}» مجاز نیست"
                )
            definition_obj = section_registry.get_definition(entry.section_key)
            try:
                if entry.settings is None:
                    definition_obj.default_settings()
                else:
                    definition_obj.validate_settings(entry.settings)
            except Exception as exc:  # noqa: BLE001 — هر نوع خطایِ اعتبارسنجیِ خودِ section اینجا یکسان گزارش می‌شود
                raise InvalidLayoutPresetError(
                    f"Preset «{definition.key}»: تنظیماتِ section «{entry.section_key}» نامعتبر است: {exc}"
                ) from exc

        # Phase 3 — عضویتِ ردیفِ ترکیبی (``row_key``/``row_span``) هم در
        # زمانِ import اعتبارسنجی می‌شود — همان ``row_service`` که
        # مسیرهایِ نوشتنِ Section استفاده می‌کنند (duck-typing: فقط به
        # ``row_key``/``row_span``/``section_key`` نیاز دارد، هرگز به
        # مدلِ Django — پس اینجا هم امن است).
        from .services import row_service

        try:
            row_service.validate_page_row_layout(entries)
        except row_service.RowAssignmentError as exc:
            raise InvalidLayoutPresetError(
                f"Preset «{definition.key}»: ترکیبِ ردیفِ صفحه‌ی «{page_type}» نامعتبر است: {exc}"
            ) from exc


# ==================================================================
# چهار Preset درون‌ساختِ نماینده — طبقِ الزامِ صریحِ کار: «3-5 clearly
# different data presets... differ through composition, spacing/
# density, typography, motion, Header/Footer settings — not merely
# color». هر Preset حتماً پالتِ خودش را با یک Preset دیگر به اشتراک
# نمی‌گذارد (تا در پیش‌نمایش هم بصراحت متفاوت به‌نظر برسند)، اما این
# مستقل از دلیلِ اصلیِ تفاوتشان است.
# ==================================================================

register_layout_preset(LayoutPresetDefinition(
    key="clean_minimal",
    label_fa="ساده و مینیمال",
    description_fa="چیدمانِ کم‌جزئیات با تراکمِ فشرده، بدونِ حرکت، مناسبِ فروشگاه‌هایی که می‌خواهند تمرکز کامل روی محصول باشد.",
    appearance={
        "font": "Vazirmatn", "radius": 8, "button_radius": 6,
        "density": "compact", "motion": "none", "type_scale": "compact",
        "button_style": "outline", "image_fit": "cover", "image_hover": "none",
        "card_image_crossfade": False, "card_image_zoom": False,
    },
    default_palette_slug="mono",
    header={"announcement_enabled": False, "sticky": True},
    footer={"show_newsletter": False},
    pages={
        "home": (
            PresetSectionEntry("hero_banner"),
            PresetSectionEntry("newest_products"),
            PresetSectionEntry("category_grid"),
            PresetSectionEntry("trust_features"),
        ),
        "product_detail": (
            PresetSectionEntry("product_main"),
            PresetSectionEntry("product_description"),
        ),
        "listing": (PresetSectionEntry("product_listing"),),
        "collection": (
            PresetSectionEntry("collection_header"),
            PresetSectionEntry("collection_products"),
        ),
        "search": (PresetSectionEntry("product_listing"),),
        "cart": (
            PresetSectionEntry("cart_items"),
            PresetSectionEntry("cart_summary"),
        ),
    },
))

register_layout_preset(LayoutPresetDefinition(
    key="editorial_story",
    label_fa="روایت‌محور",
    description_fa="چیدمانِ محتوامحور با تایپوگرافیِ بزرگ‌تر، تراکمِ بازتر و حرکتِ ملایم — مناسبِ برندهایی که با روایت/تصویر می‌فروشند.",
    appearance={
        "font": "Georgia", "radius": 4, "button_radius": 4,
        "density": "relaxed", "motion": "subtle", "type_scale": "large",
        "button_style": "soft", "image_fit": "cover", "image_hover": "zoom",
        "card_image_crossfade": True, "card_image_zoom": True,
    },
    default_palette_slug="terracotta",
    header={"sticky": True, "announcement_enabled": True},
    pages={
        "home": (
            PresetSectionEntry("story_rail"),
            PresetSectionEntry("hero_banner"),
            PresetSectionEntry("image_text"),
            PresetSectionEntry("featured_products"),
            PresetSectionEntry("testimonials"),
            PresetSectionEntry("newsletter"),
        ),
        "product_detail": (
            PresetSectionEntry("product_main"),
            PresetSectionEntry("product_description"),
            PresetSectionEntry("product_video"),
            PresetSectionEntry("related_products"),
        ),
        "listing": (PresetSectionEntry("product_listing"),),
        "collection": (
            PresetSectionEntry("collection_header"),
            PresetSectionEntry("collection_products"),
        ),
        "search": (PresetSectionEntry("product_listing"),),
        "cart": (
            PresetSectionEntry("cart_items"),
            PresetSectionEntry("cart_summary"),
        ),
    },
))

register_layout_preset(LayoutPresetDefinition(
    key="dense_catalog",
    label_fa="کاتالوگ فشرده",
    description_fa="چیدمانِ پرتراکم با چند ردیفِ گریدِ محصول پشتِ‌سرِهم — مناسبِ فروشگاه‌هایی با تعدادِ زیادِ کالا که می‌خواهند حداکثرِ محصول را زود نشان دهند.",
    appearance={
        "font": "Vazirmatn", "radius": 6, "button_radius": 6,
        "density": "compact", "motion": "none", "type_scale": "compact",
        "button_style": "filled", "image_fit": "cover", "image_hover": "none",
        "card_image_crossfade": False, "card_image_zoom": False,
    },
    default_palette_slug="slate",
    header={"sticky": True, "announcement_enabled": False},
    footer={"show_newsletter": False},
    pages={
        "home": (
            PresetSectionEntry("category_grid"),
            PresetSectionEntry("newest_products"),
            PresetSectionEntry("best_sellers"),
            PresetSectionEntry("discounted_products"),
            PresetSectionEntry("amazing_offers"),
            PresetSectionEntry("brand_carousel"),
            PresetSectionEntry("trust_features"),
        ),
        "product_detail": (
            PresetSectionEntry("product_main"),
            PresetSectionEntry("product_description"),
            PresetSectionEntry("related_products"),
        ),
        "listing": (PresetSectionEntry("product_listing"),),
        "collection": (
            PresetSectionEntry("collection_header"),
            PresetSectionEntry("collection_products"),
        ),
        "search": (PresetSectionEntry("product_listing"),),
        "cart": (
            PresetSectionEntry("cart_items"),
            PresetSectionEntry("cart_summary"),
        ),
    },
))

register_layout_preset(LayoutPresetDefinition(
    key="premium_boutique",
    label_fa="پرمیوم بوتیک",
    description_fa="چیدمانِ لوکس با تراکمِ باز، حرکتِ محسوس‌تر و تأکیدِ بازاریابی — مناسبِ برندهایی با موضعِ قیمتیِ بالا.",
    appearance={
        "font": "Georgia", "radius": 20, "button_radius": 18,
        "density": "relaxed", "motion": "dynamic", "type_scale": "large",
        "button_style": "filled", "image_fit": "cover", "image_hover": "zoom",
        "card_image_crossfade": True, "card_image_zoom": True,
    },
    default_palette_slug="luxury-black",
    header={"sticky": True, "announcement_enabled": True},
    footer={"show_trust_badges": True, "show_payment_logos": True, "show_newsletter": True},
    pages={
        "home": (
            PresetSectionEntry("hero_banner"),
            PresetSectionEntry("brand_carousel"),
            PresetSectionEntry("featured_products"),
            PresetSectionEntry("story_rail"),
            PresetSectionEntry("promo_cards"),
            PresetSectionEntry("testimonials"),
            PresetSectionEntry("trust_features"),
            PresetSectionEntry("newsletter"),
        ),
        "product_detail": (
            PresetSectionEntry("product_main"),
            PresetSectionEntry("product_description"),
            PresetSectionEntry("product_video"),
            PresetSectionEntry("related_products"),
        ),
        "listing": (PresetSectionEntry("product_listing"),),
        "collection": (
            PresetSectionEntry("collection_header"),
            PresetSectionEntry("collection_products"),
        ),
        "search": (PresetSectionEntry("product_listing"),),
        "cart": (
            PresetSectionEntry("cart_items"),
            PresetSectionEntry("cart_summary"),
        ),
    },
))


# ==================================================================
# Phase 3 — Universal Storefront: V5 Golden Homepage preset.
#
# This is pure DATA — block order, row composition, and per-block
# settings — built entirely from the Universal Block capabilities
# added/verified in Checkpoints A-D. It never selects a renderer or
# template; the same universal templates every other preset uses
# render this preset's sections. It intentionally omits every
# non-home page (spec scope: Homepage only for this phase) and never
# references a specific Store's category/brand/collection IDs (preset
# Reference Safety rule) — category_grid ships with category_ids=[]
# (merchant must pick real categories before the circular style has
# content to show, exactly like any other store using this section
# type) and multi_banner ships with no per-instance PromotionalBanner
# rows (those are merchant-managed Media, never preset data).
#
# default_palette_slug is intentionally left unset — color fidelity to
# the approved V5 reference is a later, separate pass (this phase's
# scope was structural fidelity, per the explicit A->F priority order),
# and Palette stays a fully independent, merchant-editable concern per
# the Owner's standing decision.
# ==================================================================
register_layout_preset(LayoutPresetDefinition(
    key="v5_golden_homepage",
    label_fa="فروشگاه کامل (V5)",
    description_fa=(
        "چیدمانِ کاملِ صفحه‌ی اصلی با مگامنو، ردیفِ Hero و پیشنهادِ لحظه‌ای، "
        "استریپِ دسته‌بندیِ دایره‌ای، ردیف‌های محصولِ متعدد، پیشنهادِ "
        "شگفت‌انگیزِ چندآیتمی، بلوکِ محصولِ فشرده، برندها و وبلاگ."
    ),
    appearance={
        "font": "Vazirmatn", "radius": 4, "button_radius": 8,
        "density": "normal", "motion": "subtle", "type_scale": "normal",
        "button_style": "filled", "image_fit": "cover", "image_hover": "zoom",
        "card_image_crossfade": False, "card_image_zoom": False,
    },
    header={
        "sticky": True, "announcement_enabled": True,
        "show_search": True, "show_account": True, "show_wishlist": True, "show_cart": True,
        "extra_blocks": [{"type": "phone"}],
    },
    footer={
        "show_about": True, "show_contact": True, "show_categories": True,
        "show_social": True, "show_trust_badges": True, "show_payment_logos": True,
        "show_newsletter": False, "show_copyright": True,
    },
    pages={
        "home": (
            # Hero + Instant Offer -- two independent blocks sharing one
            # row (9+3), never fused into a single section.
            PresetSectionEntry("hero_banner", row_key="v5-hero-row", row_span=9),
            PresetSectionEntry(
                "product_section", row_key="v5-hero-row", row_span=3,
                settings={
                    "title": "پیشنهاد لحظه‌ای", "data_source": "newest", "item_limit": 3,
                    "display_mode": "carousel", "show_view_all": False,
                    "responsive": {"desktop_columns": 1, "tablet_columns": 1, "mobile_columns": 1},
                },
            ),
            PresetSectionEntry(
                "category_grid",
                settings={"title": "دسته‌بندی‌ها", "display_mode": "circular", "category_ids": []},
            ),
            PresetSectionEntry(
                "trust_features",
                settings={"items": [
                    {"icon": "🚚", "title": "ارسال سریع", "subtitle": "به سراسر کشور"},
                    {"icon": "💯", "title": "ضمانت اصالت", "subtitle": "کالای اورجینال"},
                    {"icon": "🎧", "title": "پشتیبانی ۲۴/۷", "subtitle": "پاسخگویی همه‌روزه"},
                    {"icon": "↩️", "title": "۷ روز ضمانت بازگشت", "subtitle": "بدون دردسر"},
                    {"icon": "🔒", "title": "پرداخت امن", "subtitle": "درگاه بانکی معتبر"},
                ]},
            ),
            PresetSectionEntry(
                "multi_banner",
                settings={"responsive": {"desktop_columns": 4, "tablet_columns": 2, "mobile_columns": 1}},
            ),
            PresetSectionEntry(
                "product_section",
                settings={
                    "title": "پرفروش‌ترین‌های هفته", "data_source": "newest", "item_limit": 6,
                    "display_mode": "carousel",
                    "background": {"mode": "color", "color": "#F4F5F9", "media_asset_id": None, "pattern_slug": ""},
                },
            ),
            PresetSectionEntry(
                "amazing_offers",
                settings={"item_limit": 4, "deadline_hours": 8, "title": "⚡ پیشنهاد شگفت‌انگیز"},
            ),
            PresetSectionEntry(
                "multi_banner",
                settings={"responsive": {"desktop_columns": 2, "tablet_columns": 2, "mobile_columns": 1}},
            ),
            # Compact/paired Product Rail -- two ordinary product_section
            # instances sharing a 6+6 row; the narrower/shorter "compact"
            # look is a pure function of the resulting column count, no
            # separate card-density field.
            PresetSectionEntry(
                "product_section", row_key="v5-compact-row", row_span=6,
                settings={
                    "title": "پیشنهادِ منتخب ۱", "data_source": "newest", "item_limit": 4,
                    "display_mode": "grid",
                    "responsive": {"desktop_columns": 2, "tablet_columns": 2, "mobile_columns": 1},
                },
            ),
            PresetSectionEntry(
                "product_section", row_key="v5-compact-row", row_span=6,
                settings={
                    "title": "پیشنهادِ منتخب ۲", "data_source": "discounted", "item_limit": 4,
                    "display_mode": "grid",
                    "responsive": {"desktop_columns": 2, "tablet_columns": 2, "mobile_columns": 1},
                },
            ),
            PresetSectionEntry("brand_carousel", settings={"title": "برندهای منتخب", "display_mode": "carousel"}),
            PresetSectionEntry("blog_posts"),
        ),
    },
))
