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
    #: Optional generic settings for the Container created for this standalone
    #: entry or contiguous row run. Presets stay pure data; no Store IDs or
    #: renderer-specific hooks belong here.
    container_settings: dict | None = None


@dataclasses.dataclass(frozen=True)
class LayoutPresetDefinition:
    key: str
    label_fa: str
    description_fa: str
    #: U7 — Ready Template baseline version. A ``LayoutPresetDefinition`` is
    #: itself the "versioned recipe" the master contract calls a Ready
    #: Template (page composition + appearance + header/footer overlay,
    #: already the exact same shape U10's 8 Ready Templates need) — this
    #: field is the missing piece that lets ``preset_service.apply_preset``
    #: record *which* baseline a Draft is currently built from
    #: (``variant_contract.build_template_provenance``), so a later reset
    #: can restore that exact recorded version rather than "whatever this
    #: preset key currently means" (which could have changed under a store
    #: if the preset's own Python definition is edited in a future release).
    #: A plain string (not int) to match ``build_template_provenance``'s
    #: existing ``template_version: str | None`` contract.
    version: str = "1"
    #: Acceptance Batch 1 (post-U11) — the explicit registry-level
    #: distinction the master contract asked for: ``True`` only for the 8
    #: official U10 Ready Template recipe keys. ``False`` (default) for
    #: the 5 historical/internal presets (``clean_minimal``/
    #: ``editorial_story``/``dense_catalog``/``premium_boutique``/
    #: ``v5_golden_homepage``) — they remain fully registered and
    #: applicable (Advanced mode, `apply-preset` endpoint, tests), just not
    #: surfaced on the normal merchant-facing Ready Template Gallery. A
    #: plain boolean rather than a separate second registry/file, so a
    #: future Ready Template only ever needs this one flag, not a parallel
    #: structure to keep in sync.
    is_ready_template: bool = False
    #: فقط کلیدهایِ ساختاریِ ``appearance_config`` (هرگز رنگ) — زیرمجموعه‌ای
    #: از: font/radius/button_radius/density/motion/type_scale/button_style/
    #: image_fit/image_hover/card_image_crossfade/card_image_zoom. کلیدِ
    #: غایب یعنی «دست‌نخورده بماند» (نه بازنشانی به پیش‌فرضِ پلتفرم) —
    #: منطقِ merge در ``preset_service.apply_preset`` است.
    appearance: dict = dataclasses.field(default_factory=dict)
    #: Acceptance Batch 1 (post-U11) correction — this is the Ready
    #: Template's *default baseline* palette, applied unconditionally by
    #: ``preset_service.apply_preset`` whenever an explicit apply/reset
    #: happens (see that function's own docstring for why the older
    #: "only if the merchant has no palette yet" rule was wrong for an
    #: explicit Template switch). The merchant remains completely free to
    #: change the palette afterward — this only ever fires at apply/reset
    #: time, never on its own.
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


def list_ready_templates() -> list[LayoutPresetDefinition]:
    """Acceptance Batch 1 (post-U11) — the merchant-facing catalog: only
    the presets explicitly marked ``is_ready_template=True`` (U10's 8
    official recipe keys). ``list_layout_presets()`` above is unchanged
    and still returns all 13 — the historical/internal presets remain
    fully registered and applicable, just not surfaced here."""
    return [preset for preset in list_layout_presets() if preset.is_ready_template]


def _validate_page_composition_shape(definition: LayoutPresetDefinition) -> None:
    """اعتبارسنجیِ بخشِ section/page در زمانِ import — تنها به
    ``section_registry`` (کاملاً خالص) وابسته است، پس اینجا امن است.
    اعتبارسنجیِ appearance/header/footer در ``preset_service`` است (به
    ``layout_service`` نیاز دارد — نگاه کنید به docstring بالایِ فایل)."""
    if not isinstance(definition.version, str) or not definition.version.strip():
        raise InvalidLayoutPresetError(f"Preset «{definition.key}»: version باید یک رشته‌ی غیرخالی باشد")
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
            if entry.container_settings is not None:
                if not isinstance(entry.container_settings, dict):
                    raise InvalidLayoutPresetError(
                        f"Preset «{definition.key}»: container_settings باید دیکشنری باشد"
                    )
                allowed_container_keys = {
                    "gap", "mobile_mode", "content_width", "vertical_align",
                    "height_mode", "background_mode", "background_color",
                    "background_pattern",
                }
                unknown = set(entry.container_settings) - allowed_container_keys
                if unknown:
                    raise InvalidLayoutPresetError(
                        f"Preset «{definition.key}»: کلیدهای ناشناخته‌ی Container: {sorted(unknown)}"
                    )

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
    # U7 — header/footer *variant* selection (U2A/U2B global regions), not
    # just the boolean toggles already here: makes this genuinely a
    # composed Ready Template (page composition + appearance + global
    # component variants), not composition-only.
    header={"announcement_enabled": False, "sticky": True, "header_variant": "legacy_default"},
    footer={"show_newsletter": False, "footer_variant": "legacy_default"},
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
    header={"sticky": True, "announcement_enabled": True, "header_variant": "boutique_centered"},
    footer={"footer_variant": "boutique_editorial"},
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
    header={"sticky": True, "announcement_enabled": False, "header_variant": "marketplace_search_first"},
    footer={"show_newsletter": False, "footer_variant": "marketplace_dense"},
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
    header={"sticky": True, "announcement_enabled": True, "header_variant": "premium_three_column"},
    footer={"show_trust_badges": True, "show_payment_logos": True, "show_newsletter": True, "footer_variant": "premium_columns"},
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
# Golden dense-commerce homepage preset — PURE DATA.
#
# This preset intentionally mirrors the approved dense marketplace reference
# using only reusable Universal blocks.  No renderer knows this key and no
# section stores tenant-specific IDs.  Visual variety comes from composition,
# row spans, responsive columns, reusable banner variants and generic product
# sources (newest / discounted / best_sellers / most_viewed).
# ==================================================================
register_layout_preset(LayoutPresetDefinition(
    key="v5_golden_homepage",
    label_fa="فروشگاه رنگی و کاتالوگی — مرجع",
    description_fa=(
        "شروع نزدیک به صفحه مرجع تأییدشده: هدر جستجو-محور، Hero و پیشنهاد جانبی، "
        "دسته‌بندی تصویری، بنرهای تبلیغاتی، ردیف‌های رنگی محصول، ترکیب‌های دو ستونه "
        "و فوتر کامل. بعد از اعمال، همه بخش‌ها و پس‌زمینه‌ها آزادانه قابل ویرایش‌اند."
    ),
    appearance={
        "font": "Vazirmatn", "radius": 7, "button_radius": 4,
        "density": "compact", "motion": "none", "type_scale": "normal",
        "button_style": "filled", "image_fit": "contain", "image_hover": "none",
        "card_image_crossfade": False, "card_image_zoom": False,
        "content_width": 1500, "grid_density": 6,
        "card_shadow": "none", "card_hover": "none", "hero_style": "wide",
    },
    default_palette_slug="catalog-colorful",
    header={
        "sticky": False, "announcement_enabled": True,
        "show_search": True, "show_account": True, "show_wishlist": True, "show_cart": True,
        "extra_blocks": [{"type": "tagline"}],
    },
    footer={
        "show_about": True, "show_contact": True, "show_categories": True,
        "show_quick_links": True, "show_social": True,
        "show_trust_badges": True, "show_payment_logos": True,
        "show_newsletter": False, "show_copyright": True,
        "extra_blocks": [
            {"type": "custom_text", "title": "خدمات فروشگاه", "text": "ارسال سریع • ضمانت اصالت • امکان مرجوعی • پشتیبانی خرید"},
        ],
    },
    pages={
        "home": (
            PresetSectionEntry(
                "product_section", row_key="golden-hero-row", row_span=3,
                container_settings={
                    "gap": 8, "mobile_mode": "stack",
                    "vertical_align": "start", "height_mode": "equal",
                },
                settings={
                    "title": "پیشنهاد لحظه‌ای", "data_source": "discounted", "item_limit": 4,
                    "display_mode": "carousel", "show_view_all": False,
                    "carousel_autoplay": True, "carousel_interval_ms": 3500,
                    "carousel_show_arrows": True, "header_position": "inside",
                    "responsive": {"desktop_columns": 1, "tablet_columns": 1, "mobile_columns": 1},
                    "card": {
                        "card_style": "compact", "show_brand": False, "show_rating": False,
                        "show_wishlist": False, "show_quick_add": False, "show_badge": True,
                        "show_price": True, "card_border": True, "image_ratio": "square",
                        "quick_add_reveal": "always",
                    },
                    "spacing": {"vertical_spacing": "small"},
                },
            ),
            PresetSectionEntry(
                "hero_banner", row_key="golden-hero-row", row_span=9,
                settings={
                    "text_position": "start",
                    "layout": {"height": "standard"},
                    "spacing": {"vertical_spacing": "small"},
                },
            ),
            PresetSectionEntry(
                "category_grid",
                settings={
                    "title": "", "display_mode": "image_strip", "category_ids": [], "item_limit": 7,
                    "spacing": {"vertical_spacing": "small"},
                },
            ),
            PresetSectionEntry(
                "trust_features",
                settings={
                    "items": [
                        {"icon": "↙", "title": "تضمین بهترین قیمت", "subtitle": "خرید مطمئن"},
                        {"icon": "◎", "title": "ضمانت اصالت کالا", "subtitle": "کالای اصل"},
                        {"icon": "▣", "title": "پرداخت امن", "subtitle": "درگاه و کارت"},
                        {"icon": "⌂", "title": "تحویل حضوری", "subtitle": "دریافت آسان"},
                        {"icon": "⇢", "title": "ارسال سریع", "subtitle": "به سراسر کشور"},
                    ],
                    "spacing": {"vertical_spacing": "small"},
                },
            ),
            PresetSectionEntry(
                "multi_banner",
                settings={
                    "item_limit": 4, "offset": 0, "layout_variant": "promo-4",
                    "responsive": {"desktop_columns": 4, "tablet_columns": 2, "mobile_columns": 2},
                    "spacing": {"vertical_spacing": "small"},
                },
            ),
            PresetSectionEntry(
                "product_section",
                settings={
                    "title": "پرفروش‌ترین‌های هفته", "data_source": "most_viewed", "item_limit": 6,
                    "display_mode": "carousel", "show_view_all": True,
                    "responsive": {"desktop_columns": 6, "tablet_columns": 3, "mobile_columns": 2},
                    "card": {
                        "card_style": "compact", "show_brand": False, "show_rating": False,
                        "show_wishlist": False, "show_quick_add": True, "show_badge": True,
                        "show_price": True, "card_border": True, "image_ratio": "square",
                        "quick_add_reveal": "always",
                    },
                    "background": {"mode": "palette_pattern", "pattern_slug": "commerce-doodle", "palette_role": "tone-1"},
                    "spacing": {"vertical_spacing": "small"},
                },
            ),
            PresetSectionEntry(
                "amazing_offers",
                settings={
                    "item_limit": 4, "deadline_hours": 8, "title": "پیشنهاد شگفت‌انگیز برایتو",
                    "spacing": {"vertical_spacing": "small"},
                },
            ),
            PresetSectionEntry(
                "product_section",
                settings={
                    "title": "ترندهای این هفته", "data_source": "discounted", "item_limit": 6,
                    "display_mode": "carousel", "show_view_all": True,
                    "responsive": {"desktop_columns": 6, "tablet_columns": 3, "mobile_columns": 2},
                    "card": {
                        "card_style": "compact", "show_brand": False, "show_rating": False,
                        "show_wishlist": False, "show_quick_add": True, "show_badge": True,
                        "show_price": True, "card_border": True, "image_ratio": "square",
                        "quick_add_reveal": "always",
                    },
                    "background": {"mode": "palette_pattern", "pattern_slug": "commerce-doodle", "palette_role": "tone-2"},
                    "spacing": {"vertical_spacing": "small"},
                },
            ),
            PresetSectionEntry(
                "multi_banner", row_key="golden-banner-pair-a", row_span=6,
                container_settings={"gap": 10, "mobile_mode": "stack", "height_mode": "equal"},
                settings={
                    "item_limit": 1, "offset": 4, "layout_variant": "wide-single",
                    "responsive": {"desktop_columns": 1, "tablet_columns": 1, "mobile_columns": 1},
                    "spacing": {"vertical_spacing": "small"},
                },
            ),
            PresetSectionEntry(
                "multi_banner", row_key="golden-banner-pair-a", row_span=6,
                settings={
                    "item_limit": 1, "offset": 5, "layout_variant": "wide-single",
                    "responsive": {"desktop_columns": 1, "tablet_columns": 1, "mobile_columns": 1},
                    "spacing": {"vertical_spacing": "small"},
                },
            ),
            PresetSectionEntry(
                "product_section",
                settings={
                    "title": "تازه‌های فروشگاه", "data_source": "newest", "item_limit": 6,
                    "display_mode": "carousel", "show_view_all": True,
                    "responsive": {"desktop_columns": 6, "tablet_columns": 3, "mobile_columns": 2},
                    "card": {
                        "card_style": "compact", "show_brand": False, "show_rating": False,
                        "show_wishlist": False, "show_quick_add": True, "show_badge": True,
                        "show_price": True, "card_border": True, "image_ratio": "square",
                        "quick_add_reveal": "always",
                    },
                    "background": {"mode": "palette_pattern", "pattern_slug": "commerce-doodle", "palette_role": "tone-3"},
                    "spacing": {"vertical_spacing": "small"},
                },
            ),
            PresetSectionEntry(
                "multi_banner", row_key="golden-banner-pair-b", row_span=6,
                container_settings={"gap": 10, "mobile_mode": "stack", "height_mode": "equal"},
                settings={
                    "item_limit": 1, "offset": 6, "layout_variant": "wide-single",
                    "responsive": {"desktop_columns": 1, "tablet_columns": 1, "mobile_columns": 1},
                    "spacing": {"vertical_spacing": "small"},
                },
            ),
            PresetSectionEntry(
                "multi_banner", row_key="golden-banner-pair-b", row_span=6,
                settings={
                    "item_limit": 1, "offset": 7, "layout_variant": "wide-single",
                    "responsive": {"desktop_columns": 1, "tablet_columns": 1, "mobile_columns": 1},
                    "spacing": {"vertical_spacing": "small"},
                },
            ),
            PresetSectionEntry(
                "product_section", row_key="golden-compact-row-a", row_span=6,
                container_settings={"gap": 10, "mobile_mode": "stack", "height_mode": "equal"},
                settings={
                    "title": "پیشنهادهای منتخب", "data_source": "newest", "item_limit": 3,
                    "display_mode": "grid", "show_view_all": True,
                    "responsive": {"desktop_columns": 3, "tablet_columns": 3, "mobile_columns": 1},
                    "card": {
                        "card_style": "compact", "show_brand": False, "show_rating": False,
                        "show_wishlist": False, "show_quick_add": True, "show_badge": True,
                        "show_price": True, "card_border": True, "image_ratio": "square",
                        "quick_add_reveal": "always",
                    },
                    "spacing": {"vertical_spacing": "small"},
                },
            ),
            PresetSectionEntry(
                "product_section", row_key="golden-compact-row-a", row_span=6,
                settings={
                    "title": "محبوب‌ترین انتخاب‌ها", "data_source": "most_viewed", "item_limit": 3,
                    "display_mode": "grid", "show_view_all": True,
                    "responsive": {"desktop_columns": 3, "tablet_columns": 3, "mobile_columns": 1},
                    "card": {
                        "card_style": "compact", "show_brand": False, "show_rating": False,
                        "show_wishlist": False, "show_quick_add": True, "show_badge": True,
                        "show_price": True, "card_border": True, "image_ratio": "square",
                        "quick_add_reveal": "always",
                    },
                    "spacing": {"vertical_spacing": "small"},
                },
            ),
            PresetSectionEntry(
                "product_section",
                settings={
                    "title": "پیشنهادهای ویژه", "data_source": "most_viewed", "item_limit": 6,
                    "display_mode": "carousel", "show_view_all": True,
                    "responsive": {"desktop_columns": 6, "tablet_columns": 3, "mobile_columns": 2},
                    "card": {
                        "card_style": "compact", "show_brand": False, "show_rating": False,
                        "show_wishlist": False, "show_quick_add": True, "show_badge": True,
                        "show_price": True, "card_border": True, "image_ratio": "square",
                        "quick_add_reveal": "always",
                    },
                    "background": {"mode": "palette_pattern", "pattern_slug": "commerce-doodle", "palette_role": "tone-4"},
                    "spacing": {"vertical_spacing": "small"},
                },
            ),
            PresetSectionEntry(
                "product_section", row_key="golden-compact-row-b", row_span=6,
                container_settings={"gap": 10, "mobile_mode": "stack", "height_mode": "equal"},
                settings={
                    "title": "انتخاب روز", "data_source": "discounted", "item_limit": 3,
                    "display_mode": "grid", "show_view_all": True,
                    "responsive": {"desktop_columns": 3, "tablet_columns": 3, "mobile_columns": 1},
                    "card": {
                        "card_style": "compact", "show_brand": False, "show_rating": False,
                        "show_wishlist": False, "show_quick_add": True, "show_badge": True,
                        "show_price": True, "card_border": True, "image_ratio": "square",
                        "quick_add_reveal": "always",
                    },
                    "spacing": {"vertical_spacing": "small"},
                },
            ),
            PresetSectionEntry(
                "product_section", row_key="golden-compact-row-b", row_span=6,
                settings={
                    "title": "بیشتر دیده‌شده‌ها", "data_source": "most_viewed", "item_limit": 3,
                    "display_mode": "grid", "show_view_all": True,
                    "responsive": {"desktop_columns": 3, "tablet_columns": 3, "mobile_columns": 1},
                    "card": {
                        "card_style": "compact", "show_brand": False, "show_rating": False,
                        "show_wishlist": False, "show_quick_add": True, "show_badge": True,
                        "show_price": True, "card_border": True, "image_ratio": "square",
                        "quick_add_reveal": "always",
                    },
                    "spacing": {"vertical_spacing": "small"},
                },
            ),
            PresetSectionEntry(
                "multi_banner",
                settings={
                    "item_limit": 4, "offset": 8, "layout_variant": "mini-4",
                    "responsive": {"desktop_columns": 4, "tablet_columns": 2, "mobile_columns": 2},
                    "spacing": {"vertical_spacing": "small"},
                },
            ),
            PresetSectionEntry(
                "product_section",
                settings={
                    "title": "محبوب‌های فروشگاه", "data_source": "newest", "item_limit": 6,
                    "display_mode": "carousel", "show_view_all": True,
                    "responsive": {"desktop_columns": 6, "tablet_columns": 3, "mobile_columns": 2},
                    "card": {
                        "card_style": "compact", "show_brand": False, "show_rating": False,
                        "show_wishlist": False, "show_quick_add": True, "show_badge": True,
                        "show_price": True, "card_border": True, "image_ratio": "square",
                        "quick_add_reveal": "always",
                    },
                    "background": {"mode": "palette_pattern", "pattern_slug": "commerce-doodle", "palette_role": "tone-5"},
                    "spacing": {"vertical_spacing": "small"},
                },
            ),
            PresetSectionEntry(
                "multi_banner",
                settings={
                    "item_limit": 1, "offset": 12, "layout_variant": "strip",
                    "responsive": {"desktop_columns": 1, "tablet_columns": 1, "mobile_columns": 1},
                    "spacing": {"vertical_spacing": "small"},
                },
            ),
            PresetSectionEntry(
                "product_section",
                settings={
                    "title": "منتخب برای شما", "data_source": "discounted", "item_limit": 6,
                    "display_mode": "carousel", "show_view_all": True,
                    "responsive": {"desktop_columns": 6, "tablet_columns": 3, "mobile_columns": 2},
                    "card": {
                        "card_style": "compact", "show_brand": False, "show_rating": False,
                        "show_wishlist": False, "show_quick_add": True, "show_badge": True,
                        "show_price": True, "card_border": True, "image_ratio": "square",
                        "quick_add_reveal": "always",
                    },
                    "spacing": {"vertical_spacing": "small"},
                },
            ),
        ),
    },
))


# ==================================================================
# U10 — the 8 required Ready Template recipe keys. Each is built purely
# from the Universal Storefront Engine already completed in U1-U9: real
# global header/footer variants (U2A/U2B), real registered section
# variants including U4's additions (hero_style/tile_style/image_position/
# display_mode), real appearance tokens/palettes, real product_section
# card settings — never a new renderer, never a store-specific ID, never
# fabricated commercial copy (no invented discounts/guarantees/stock
# claims — sections read real store data at render time as always).
#
# Difference between templates comes from *combinations* of: home
# composition, header/footer variant, density/typography/motion, palette,
# and product-card presentation — exactly the axes the master contract
# names, not duplicated code. product_detail/listing/collection/search/
# cart intentionally share one composition across all 8 (see
# ``_u10_standard_non_home_pages`` below) — the same, already-established
# pattern the 5 pre-U10 presets already use; real product/cart data drives
# those pages far more than section arrangement does, so bespoke
# per-template composition there would be difference for its own sake,
# not a real one.
# ==================================================================

_U10_STANDARD_PRODUCT_DETAIL_PAGE = (
    PresetSectionEntry("product_main"),
    PresetSectionEntry("product_description"),
    PresetSectionEntry("related_products"),
)
_U10_STANDARD_LISTING_PAGE = (PresetSectionEntry("product_listing"),)
_U10_STANDARD_COLLECTION_PAGE = (
    PresetSectionEntry("collection_header"),
    PresetSectionEntry("collection_products"),
)
_U10_STANDARD_CART_PAGE = (
    PresetSectionEntry("cart_items"),
    PresetSectionEntry("cart_summary"),
)


def _u10_standard_non_home_pages() -> dict:
    return {
        "product_detail": _U10_STANDARD_PRODUCT_DETAIL_PAGE,
        "listing": _U10_STANDARD_LISTING_PAGE,
        "collection": _U10_STANDARD_COLLECTION_PAGE,
        "search": _U10_STANDARD_LISTING_PAGE,
        "cart": _U10_STANDARD_CART_PAGE,
    }


register_layout_preset(LayoutPresetDefinition(
    key="dense_marketplace",
    is_ready_template=True,
    label_fa="بازارگاه پرتراکم",
    description_fa="چیدمانِ فشرده و پرمحصول برایِ فروشگاه‌هایی با کاتالوگِ بزرگ که می‌خواهند در نگاهِ اول محصولِ زیادی نشان دهند.",
    appearance={
        "font": "Vazirmatn", "radius": 6, "button_radius": 6,
        "density": "compact", "motion": "none", "type_scale": "compact",
        "button_style": "filled", "image_fit": "cover", "image_hover": "none",
        "card_image_crossfade": False, "card_image_zoom": False,
    },
    default_palette_slug="digired",
    header={"sticky": True, "announcement_enabled": True, "header_variant": "marketplace_search_first"},
    footer={"show_newsletter": False, "footer_variant": "marketplace_dense"},
    pages={
        "home": (
            PresetSectionEntry("category_grid", settings={"display_mode": "image_strip"}),
            PresetSectionEntry("product_section", settings={
                "title": "پرفروش‌ترین‌ها", "data_source": "best_sellers", "display_mode": "grid",
                "item_limit": 12, "card": {"card_style": "compact"},
            }),
            PresetSectionEntry("discounted_products"),
            PresetSectionEntry("amazing_offers"),
            PresetSectionEntry("brand_carousel", settings={"display_mode": "carousel"}),
            PresetSectionEntry("trust_features"),
        ),
        **_u10_standard_non_home_pages(),
    },
))

register_layout_preset(LayoutPresetDefinition(
    key="premium_leather",
    is_ready_template=True,
    label_fa="چرمِ پرمیوم",
    description_fa="چیدمانِ لوکس با تراکمِ باز و حرکتِ ملایم — مناسبِ برندهایِ چرم/کالایِ دستی با موضعِ قیمتیِ بالا.",
    appearance={
        "font": "Georgia", "radius": 10, "button_radius": 10,
        "density": "relaxed", "motion": "subtle", "type_scale": "large",
        "button_style": "filled", "image_fit": "cover", "image_hover": "zoom",
        "card_image_crossfade": True, "card_image_zoom": True,
    },
    default_palette_slug="amber",
    header={"sticky": True, "announcement_enabled": True, "header_variant": "premium_three_column"},
    footer={"show_trust_badges": True, "show_payment_logos": True, "footer_variant": "premium_columns"},
    pages={
        "home": (
            PresetSectionEntry("hero_banner", settings={"hero_style": "split"}),
            PresetSectionEntry("brand_carousel"),
            PresetSectionEntry("product_section", settings={
                "title": "منتخبِ فصل", "data_source": "newest", "display_mode": "carousel",
                "item_limit": 8, "card": {"card_style": "standard"},
            }),
            PresetSectionEntry("story_rail"),
            PresetSectionEntry("testimonials"),
            PresetSectionEntry("trust_features"),
            PresetSectionEntry("newsletter"),
        ),
        **_u10_standard_non_home_pages(),
    },
))

register_layout_preset(LayoutPresetDefinition(
    key="warm_boutique",
    is_ready_template=True,
    label_fa="بوتیکِ گرم",
    description_fa="چیدمانِ گرم و دعوت‌کننده با لوگویِ مرکزی — مناسبِ بوتیک‌ها و برندهایِ کوچکِ خانوادگی.",
    appearance={
        "font": "Georgia", "radius": 14, "button_radius": 14,
        "density": "relaxed", "motion": "subtle", "type_scale": "normal",
        "button_style": "soft", "image_fit": "cover", "image_hover": "zoom",
        "card_image_crossfade": True, "card_image_zoom": True,
    },
    default_palette_slug="rose",
    header={"sticky": True, "announcement_enabled": True, "header_variant": "boutique_centered"},
    footer={"show_newsletter": True, "footer_variant": "boutique_editorial"},
    pages={
        "home": (
            PresetSectionEntry("hero_banner", settings={"hero_style": "overlay"}),
            PresetSectionEntry("image_text", settings={"image_position": "right"}),
            PresetSectionEntry("product_section", settings={
                "title": "پیشنهادِ فروشگاه", "data_source": "newest", "display_mode": "grid",
                "item_limit": 8, "card": {"card_style": "minimal"},
            }),
            PresetSectionEntry("testimonials"),
            PresetSectionEntry("newsletter"),
        ),
        **_u10_standard_non_home_pages(),
    },
))

#: Site-target-overhaul (ibolak reference) — the reusable card presentation
#: this Ready Template opts into: the ``fashion_sale`` card style (see
#: ``section_registry.CARD_STYLE_CHOICES``), a portrait product photo
#: (already a registered ``image_ratio`` choice), and no quick-add bar —
#: ibolak's own listing/home cards never offer a one-click add, since a
#: real color/size choice is required first; hiding it here is an honest
#: match, not a fabricated capability.
_FASHION_PROMO_CARD = {"card_style": "fashion_sale", "image_ratio": "portrait", "show_quick_add": False}
#: Part 2B (ibolak Home rebuild) — 5 cards per row on desktop, matching
#: the reference's dense product-wall rhythm (an already-registered
#: ``responsive.desktop_columns`` choice, see ``section_registry.
#: DESKTOP_COLUMN_CHOICES`` — no new primitive needed for this axis).
_FASHION_PROMO_ROW = {"responsive": {"desktop_columns": 5}}


def _fashion_promo_row(title: str, data_source: str) -> PresetSectionEntry:
    return PresetSectionEntry("product_section", settings={
        "title": title, "data_source": data_source, "display_mode": "carousel",
        "item_limit": 14, "card": _FASHION_PROMO_CARD, **_FASHION_PROMO_ROW,
    })

register_layout_preset(LayoutPresetDefinition(
    key="fashion_promo_catalog",
    # Part 2C (ibolak Home precision pass) — merchant visual QA #2: the
    # Part 2B structural rebuild was approved as an architecture, but the
    # macro geometry (hero height, category moments, density, background,
    # content width) still diverged materially from the reference. Bumped
    # again from "2" for the same reason "2" was bumped from "1": the Home
    # composition's real content changed (two category moments instead of
    # one, a shorter/wider hero, denser product rows), so a Draft that
    # already recorded a "2" baseline snapshot must be recognized as
    # *not* matching this new content on reapply.
    version="3",
    is_ready_template=True,
    label_fa="کاتالوگِ پوشاک و پیشنهادها",
    description_fa="چیدمانِ کاتالوگ‌محور با بنرهایِ تبلیغاتیِ متعدد — مناسبِ پوشاک/مدی که مرتب کمپین/تخفیف اجرا می‌کند.",
    appearance={
        "font": "Vazirmatn", "radius": 14, "button_radius": 999,
        "density": "normal", "motion": "dynamic", "type_scale": "normal",
        "button_style": "filled", "image_fit": "cover", "image_hover": "zoom",
        "card_image_crossfade": True, "card_image_zoom": True,
        # Part 2C — the reference's product wall/hero/category mosaic reads
        # as nearly full-bleed at a 1440 viewport (~14px gutters), not a
        # classic centered ~1200-1320 container. ``content_width`` is an
        # existing, generic, already-registered structural appearance field
        # (``appearance_registry.SITE_CONTENT_WIDTH_CHOICES``) that flows
        # straight into ``--sfb-content-width`` via ``apply_preset``'s
        # existing ``overlay = dict(preset.appearance)`` copy — no new
        # mechanism, and no other Ready Template sets this key, so the
        # other 7 keep whatever their own Draft/CSS default already is.
        # 1500 is the largest registered choice; combined with the existing
        # ``.wrap{width:min(var(--sfb-content-width),calc(100% - 28px))}``
        # rule it resolves to ~1412px at a 1440 viewport — a ~14px gutter,
        # matching the reference's measured content width almost exactly.
        "content_width": 1500,
    },
    default_palette_slug="magenta-pop",
    header={"sticky": True, "announcement_enabled": True, "header_variant": "promo_search_nav"},
    footer={"footer_variant": "promo_columns"},
    pages={
        # Part 2B (ibolak Home rebuild) — the old ``hero_banner``/
        # ``promo_cards``/``amazing_offers``/``brand_carousel`` mix left
        # too much of the shared generic RastiSi Home rhythm (large
        # colored promo blocks, a brand-name pill row) that has no
        # equivalent in the reference at all. Real merchant data behind
        # those sections is untouched — a merchant can still add any of
        # them back in the editor.
        #
        # Part 2C (precision pass) — the reference actually has TWO
        # distinct category moments, not one: a compact circular shortcut
        # rail close to the header (``fashion_flat``, moved here BEFORE the
        # hero — it used to render after it), and a larger post-hero
        # category mosaic (the new ``fashion_mosaic`` display_mode). Both
        # reuse ``category_grid``'s existing empty-``category_ids``
        # auto-pick behavior (real, active top-level Store categories —
        # never a hardcoded Store-specific ID, safe for any merchant who
        # applies this Ready Template). The product wall stays on the 4
        # ID-free, Store-agnostic data sources (``PRODUCT_SECTION_
        # DATA_SOURCES``'s "category"/"collection"/"brand" all require a
        # real per-Store numeric ``source_id`` — hardcoding one of
        # rasti-mode-demo's own here would either leak that Store's ID into
        # every other merchant's copy of this Ready Template or silently
        # render empty for them; neither is acceptable for an official,
        # reusable Ready Template) — each row's ``item_limit`` raised for a
        # visibly denser, longer carousel per section.
        "home": (
            PresetSectionEntry("category_grid", settings={"display_mode": "fashion_flat", "item_limit": 12}),
            PresetSectionEntry("fashion_lifestyle_hero"),
            PresetSectionEntry("category_grid", settings={"display_mode": "fashion_mosaic", "item_limit": 8}),
            _fashion_promo_row("تخفیف‌های ویژه", "discounted"),
            _fashion_promo_row("جدیدترین‌ها", "newest"),
            _fashion_promo_row("پرفروش‌ترین‌ها", "best_sellers"),
            _fashion_promo_row("پربازدیدترین‌ها", "most_viewed"),
        ),
        **{
            **_u10_standard_non_home_pages(),
            # Site-target-overhaul — the master contract's shared
            # listing/product_detail *composition* (which sections, in
            # which order) is intentionally unchanged (still exactly
            # ``_U10_STANDARD_LISTING_PAGE``/``_U10_STANDARD_PRODUCT_DETAIL_PAGE``'s
            # one ``product_listing``/(``product_main``, ``product_description``,
            # ``related_products``) section list) -- only each entry's own
            # ``settings.layout_variant``/``settings.card`` differ, exactly
            # the same axis ``card_style`` already varies on. No other Ready
            # Template's ``pages[...]`` is touched by this override.
            "listing": (PresetSectionEntry("product_listing", settings={
                "layout_variant": "sidebar_dense", "card": _FASHION_PROMO_CARD,
            }),),
            "search": (PresetSectionEntry("product_listing", settings={
                "layout_variant": "sidebar_dense", "card": _FASHION_PROMO_CARD,
            }),),
            "product_detail": (
                PresetSectionEntry("product_main", settings={"layout_variant": "fashion"}),
                PresetSectionEntry("product_description"),
                PresetSectionEntry("related_products", settings={"card": _FASHION_PROMO_CARD}),
            ),
        },
    },
))

register_layout_preset(LayoutPresetDefinition(
    key="playful_lifestyle",
    is_ready_template=True,
    label_fa="سبکِ زندگیِ شاد",
    description_fa="چیدمانِ رنگی و پرحرکت با گوشه‌هایِ گرد — مناسبِ برندهایِ سبکِ زندگی/کودک/سرگرمی.",
    appearance={
        "font": "Vazirmatn", "radius": 20, "button_radius": 20,
        "density": "relaxed", "motion": "dynamic", "type_scale": "normal",
        "button_style": "soft", "image_fit": "cover", "image_hover": "zoom",
        "card_image_crossfade": True, "card_image_zoom": True,
    },
    default_palette_slug="mint",
    header={"sticky": True, "announcement_enabled": True, "header_variant": "boutique_centered"},
    footer={"show_newsletter": True, "footer_variant": "boutique_editorial"},
    pages={
        "home": (
            PresetSectionEntry("story_rail"),
            PresetSectionEntry("hero_banner", settings={"hero_style": "split"}),
            PresetSectionEntry("category_grid", settings={"display_mode": "circular"}),
            PresetSectionEntry("product_section", settings={
                "title": "تازه‌های فروشگاه", "data_source": "newest", "display_mode": "carousel",
                "item_limit": 8, "card": {"card_style": "standard"},
            }),
            PresetSectionEntry("testimonials"),
        ),
        **_u10_standard_non_home_pages(),
    },
))

register_layout_preset(LayoutPresetDefinition(
    key="utility_catalog",
    is_ready_template=True,
    label_fa="کاتالوگِ ابزار و صنعتی",
    description_fa="چیدمانِ ساده و کارکردی، بدونِ حرکت/تزیینِ اضافه — مناسبِ ابزار/قطعات/کالایِ صنعتی که تمرکز باید کاملاً رویِ مشخصات و پیدا کردنِ سریعِ کالا باشد.",
    appearance={
        "font": "Arial", "radius": 4, "button_radius": 4,
        "density": "compact", "motion": "none", "type_scale": "compact",
        "button_style": "outline", "image_fit": "contain", "image_hover": "none",
        "card_image_crossfade": False, "card_image_zoom": False,
    },
    default_palette_slug="navy",
    header={"sticky": True, "announcement_enabled": False, "header_variant": "legacy_default"},
    footer={"show_newsletter": False, "footer_variant": "legacy_default"},
    pages={
        "home": (
            PresetSectionEntry("category_grid", settings={"display_mode": "grid"}),
            PresetSectionEntry("product_section", settings={
                "title": "جدیدترین کالاها", "data_source": "newest", "display_mode": "grid",
                "item_limit": 12, "card": {"card_style": "compact", "show_rating": False},
            }),
            PresetSectionEntry("best_sellers"),
            PresetSectionEntry("trust_features"),
        ),
        **_u10_standard_non_home_pages(),
    },
))

register_layout_preset(LayoutPresetDefinition(
    key="editorial_jewelry",
    is_ready_template=True,
    label_fa="جواهراتِ مجله‌ای",
    description_fa="چیدمانِ روایت‌محور با تایپوگرافیِ بزرگ و فاصله‌ی باز — مناسبِ جواهر/اکسسوری‌یی که با تصویر و داستان می‌فروشد، نه فقط گرید.",
    appearance={
        "font": "Georgia", "radius": 2, "button_radius": 2,
        "density": "relaxed", "motion": "subtle", "type_scale": "large",
        "button_style": "outline", "image_fit": "cover", "image_hover": "zoom",
        "card_image_crossfade": True, "card_image_zoom": True,
    },
    default_palette_slug="plum",
    header={"sticky": True, "announcement_enabled": True, "header_variant": "premium_three_column"},
    footer={"show_trust_badges": True, "footer_variant": "premium_columns"},
    pages={
        "home": (
            PresetSectionEntry("story_rail"),
            PresetSectionEntry("image_text", settings={"image_position": "left"}),
            PresetSectionEntry("hero_banner", settings={"hero_style": "split"}),
            PresetSectionEntry("product_section", settings={
                "title": "مجموعه‌ی منتخب", "data_source": "newest", "display_mode": "grid",
                "item_limit": 6, "card": {"card_style": "minimal", "show_badge": False},
            }),
            PresetSectionEntry("testimonials"),
            PresetSectionEntry("newsletter"),
        ),
        **_u10_standard_non_home_pages(),
    },
))

register_layout_preset(LayoutPresetDefinition(
    key="dark_digital",
    is_ready_template=True,
    label_fa="دیجیتالِ تیره",
    description_fa="چیدمانِ تیره و پرحرکت — مناسبِ فروشگاهِ لوازمِ دیجیتال/فناوری که هویتِ بصریِ تک‌محور می‌خواهد.",
    appearance={
        "font": "Arial", "radius": 6, "button_radius": 6,
        "density": "compact", "motion": "dynamic", "type_scale": "normal",
        "button_style": "filled", "image_fit": "cover", "image_hover": "zoom",
        "card_image_crossfade": True, "card_image_zoom": True,
    },
    default_palette_slug="ocean",
    header={"sticky": True, "announcement_enabled": True, "header_variant": "dark_tech"},
    footer={"footer_variant": "dark_tech"},
    pages={
        "home": (
            PresetSectionEntry("hero_banner", settings={"hero_style": "overlay"}),
            PresetSectionEntry("product_section", settings={
                "title": "جدیدترین محصولات", "data_source": "newest", "display_mode": "grid",
                "item_limit": 8, "card": {"card_style": "standard"},
            }),
            PresetSectionEntry("discounted_products"),
            PresetSectionEntry("brand_carousel", settings={"display_mode": "carousel"}),
            PresetSectionEntry("trust_features"),
        ),
        **_u10_standard_non_home_pages(),
    },
))
