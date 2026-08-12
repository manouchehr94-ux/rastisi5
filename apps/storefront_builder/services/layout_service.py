"""چرخه حیات چیدمان صفحه فروشگاه — Draft / Preview / Publish / Discard / Restore.

قوانین معماری (طبق تصمیمات حل‌شده کاربر، بخش ۳۲ گزارش ممیزی):

- هر عملیات با ``store`` (نه ``layout_id``/``version_id`` خام از ورودی
  کاربر) شروع می‌شود؛ تمام lookupهای بعدی transitively به همان Store
  محدود می‌شوند — این همان تفکیک مستأجر دوگانه (view + سرویس) است که در
  کل کدبیس رعایت شده.
- انتشار (``publish``) کاملاً اتمیک است: تنها کاری که انجام می‌شود عوض
  کردن دو اشاره‌گر (``published_version``/``draft_version``) روی
  ``StorefrontLayout`` است — محتوای نسخه از قبل کامل/معتبر است، پس
  انتشار ناموفق هرگز نمی‌تواند نیمه‌کاره storefront زنده را جایگزین کند.
- بازگردانی (``restore_version``) هرگز مستقیماً منتشر نمی‌شود — همیشه
  یک Draft جدید می‌سازد که باید جداگانه publish شود.
- Rate limiting فقط روی عملیات حساس (publish/restore/ساخت نسخه جدید)
  اعمال می‌شود، نه روی بازچینش معمولی — با استفاده مجدد از
  ``apps.core.services.rate_limit`` موجود، نه یک مکانیزم جدید.
"""

from __future__ import annotations

from django.db import transaction
from django.utils import timezone

from apps.core.services.rate_limit import enforce_rate_limit

from .. import appearance_registry, family_registry, preset_registry
from ..models import (
    APPEARANCE_COLOR_KEYS,
    APPEARANCE_CONFIG_DEFAULTS,
    FOOTER_CONFIG_DEFAULTS,
    FOOTER_RESPONSIVE_AWARE_KEYS,
    FOOTER_TOGGLE_FIELDS,
    HEADER_CONFIG_DEFAULTS,
    HEADER_RESPONSIVE_AWARE_KEYS,
    HEADER_TOGGLE_FIELDS,
    StorefrontLayout,
    StorefrontLayoutVersion,
    StorefrontSection,
)

_PUBLISH_RATE_LIMIT = dict(max_attempts=20, window_seconds=3600)
_RESTORE_RATE_LIMIT = dict(max_attempts=20, window_seconds=3600)
_NEW_DRAFT_RATE_LIMIT = dict(max_attempts=30, window_seconds=3600)


class NoDraftToPublishError(Exception):
    """چیزی برای انتشار وجود ندارد — هیچ Draft فعالی برای این فروشگاه نیست."""


class CrossStoreVersionError(Exception):
    """نسخه‌ی درخواست‌شده متعلق به این فروشگاه نیست."""


class StorefrontAlreadyPublishedError(Exception):
    """این فروشگاه از قبل یک نسخه‌ی منتشرشده (سفارشی‌سازی‌شده) دارد — اعمال
    چیدمان پیشنهادی صنف بدون تأیید صریح کاربر مجاز نیست (تصمیم کاربر:
    «هرگز storefront سفارشی‌سازی‌شده و منتشرشده را بدون تأیید صریح رونویسی
    نکن»)."""


class HeaderConfigValidationError(Exception):
    """پیکربندی پیشنهادی هدر نامعتبر است — نباید ذخیره شود (پیام فارسی
    قابل‌نمایش مستقیم به کاربر)."""


class AppearanceConfigValidationError(Exception):
    """پیکربندی پیشنهادی ظاهر نامعتبر است — نباید ذخیره شود (پیام فارسی
    قابل‌نمایش مستقیم به کاربر)."""


class FooterConfigValidationError(Exception):
    """پیکربندی پیشنهادی فوتر نامعتبر است — نباید ذخیره شود (پیام فارسی
    قابل‌نمایش مستقیم به کاربر)."""


def _validate_shell_component_responsive(raw, allowed_keys: list[str]) -> dict:
    """قراردادِ مشترکِ «نمایش در دستگاه‌ها» برایِ کامپوننت‌هایِ هدر/فوتر
    (Phase 4) — دقیقاً همان الگویِ ``section_registry.validate_responsive_settings``
    (بخشِ سازنده بصری برایِ section‌ها): کلیدِ غایب/شکلِ نامعتبر یعنی
    «نمایان در همه‌جا» (بی‌صدا، نه خطا)؛ فقط کلیدهایِ عضوِ ``allowed_keys``
    خوانده می‌شوند — بقیه‌یِ کلیدهایِ ورودی (حتی اگر تاجر چیزِ دیگری
    فرستاده باشد) بی‌صدا نادیده گرفته می‌شوند."""
    if not isinstance(raw, dict):
        raw = {}
    cleaned = {}
    for key in allowed_keys:
        component_raw = raw.get(key)
        if not isinstance(component_raw, dict):
            component_raw = {}
        cleaned[key] = {
            "hide_on_tablet": bool(component_raw.get("hide_on_tablet", False)),
            "hide_on_mobile": bool(component_raw.get("hide_on_mobile", False)),
        }
    return cleaned


def validate_header_config(config: dict) -> dict:
    """پیکربندی خام هدر (خروجی فرم ادیتور) را اعتبارسنجی و پاک‌سازی می‌کند.

    قوانین بر اساس بررسی مستقیم قرارداد فعلی (نه فرض‌های سند معماری):
    ``HEADER_TOGGLE_FIELDS`` (``models.py``) و دو تمپلیت مصرف‌کننده
    (``page_shell_header.html``، مشترک بین Preview و Storefront، فاز A1).

    - فقط کلیدهای شناخته‌شده (``HEADER_TOGGLE_FIELDS`` + ``announcement_text``)
      وارد پیکربندی نهایی می‌شوند — کلید ناشناخته بی‌صدا حذف می‌شود.
    - هر toggle باید دقیقاً بولی باشد.
    - ``show_cart``: در معماری فعلی، آیکون سبد خرید در هدر تنها مسیر
      موجود به سبد خرید است — نه در فوتر، نه در ناوبری. غیرفعال کردن آن
      یعنی مشتری هیچ راهی برای رسیدن به سبد خرید ندارد؛ رد می‌شود.
    - بازگشت به صفحه اصلی (لوگو) در هیچ تمپلیتی پشت هیچ toggle‌ای نیست —
      همیشه بدون قید رندر می‌شود، پس نیازی به قانون جداگانه ندارد.
    """
    cleaned = dict(HEADER_CONFIG_DEFAULTS)
    for field in HEADER_TOGGLE_FIELDS:
        value = config.get(field, True)
        if not isinstance(value, bool):
            raise HeaderConfigValidationError(f"مقدار فیلد «{field}» باید درست/نادرست باشد")
        cleaned[field] = value

    announcement_text = config.get("announcement_text", "")
    if not isinstance(announcement_text, str):
        raise HeaderConfigValidationError("متن نوار اعلان نامعتبر است")
    cleaned["announcement_text"] = announcement_text[:300]

    cleaned["responsive"] = _validate_shell_component_responsive(
        config.get("responsive"), HEADER_RESPONSIVE_AWARE_KEYS,
    )

    if not cleaned["show_cart"]:
        raise HeaderConfigValidationError(
            "دسترسی به سبد خرید نمی‌تواند از هدر حذف شود — در حال حاضر هیچ مسیر "
            "جایگزینی برای رسیدن مشتری به سبد خرید در ناوبری فروشگاه وجود ندارد."
        )
    return cleaned


def validate_footer_config(config: dict) -> dict:
    """پیکربندی خام فوتر را اعتبارسنجی و پاک‌سازی می‌کند.

    قانون: فوتر نباید کاملاً خالی منتشر شود — طبق تصمیم محصولی این فاز،
    حداقل یکی از ۹ بخش قابل‌تنظیم فوتر (``FOOTER_TOGGLE_FIELDS``) باید
    فعال بماند. هیچ محتوای اضافه‌ای که معماری فعلی اجازه‌ی غیابش را
    می‌دهد (مثلاً محتوای هر ستون) اینجا اجباری نشده — فقط از یک نوار
    فوتر کاملاً نامرئی/تهی جلوگیری می‌شود.
    """
    cleaned = dict(FOOTER_CONFIG_DEFAULTS)
    for field in FOOTER_TOGGLE_FIELDS:
        value = config.get(field, True)
        if not isinstance(value, bool):
            raise FooterConfigValidationError(f"مقدار فیلد «{field}» باید درست/نادرست باشد")
        cleaned[field] = value

    cleaned["responsive"] = _validate_shell_component_responsive(
        config.get("responsive"), FOOTER_RESPONSIVE_AWARE_KEYS,
    )

    if not any(cleaned[field] for field in FOOTER_TOGGLE_FIELDS):
        raise FooterConfigValidationError(
            "فوتر نمی‌تواند کاملاً خالی باشد — حداقل یکی از بخش‌های فوتر "
            "(درباره فروشگاه، تماس، لینک‌های مفید، دسته‌بندی‌ها، شبکه‌های اجتماعی، "
            "نشان‌های اعتماد، لوگوهای پرداخت، خبرنامه یا کپی‌رایت) باید فعال بماند."
        )
    return cleaned


def validate_appearance_config(config: dict) -> dict:
    """پیکربندی خامِ ظاهر (Template/Palette/Override/فونت/گردی/تراکم/حرکت)
    را اعتبارسنجی و پاک‌سازی می‌کند — دقیقاً همان الگویِ
    ``validate_header_config``: کلیدِ ناشناخته بی‌صدا حذف می‌شود، هر
    مقدار در برابرِ یک enum بسته/بازه‌ی معقول چک می‌شود.

    ``template_slug``/``palette_slug`` در برابرِ ``appearance_registry``
    (نه یک لیستِ رشته‌ایِ تکراری اینجا) چک می‌شوند — همان الگویی که
    ``StorefrontSection.section_key`` در برابرِ ``SECTION_REGISTRY`` چک
    می‌شود. ``palette_slug=None`` مجاز است (یعنی «بدونِ پالتِ نام‌دار،
    فقط رنگ‌هایِ دستی») — دقیقاً حالتِ فروشگاه‌هایی که هنوز به این سیستم
    مهاجرت نکرده‌اند."""
    from django.core.exceptions import ValidationError as DjangoValidationError

    from apps.core.models import validate_hex_color

    if not isinstance(config, dict):
        raise AppearanceConfigValidationError("تنظیمات ظاهر باید یک شیء باشد")

    cleaned = dict(APPEARANCE_CONFIG_DEFAULTS)

    template_slug = config.get("template_slug", APPEARANCE_CONFIG_DEFAULTS["template_slug"])
    if appearance_registry.get_template(template_slug) is None:
        raise AppearanceConfigValidationError(f"قالبِ «{template_slug}» در دسترس نیست")
    cleaned["template_slug"] = template_slug

    palette_slug = config.get("palette_slug")
    if palette_slug is not None:
        if appearance_registry.get_palette(palette_slug) is None:
            raise AppearanceConfigValidationError(f"پالتِ «{palette_slug}» در دسترس نیست")
    cleaned["palette_slug"] = palette_slug

    raw_overrides = config.get("color_overrides") or {}
    if not isinstance(raw_overrides, dict):
        raise AppearanceConfigValidationError("رنگ‌های سفارشی باید یک شیء باشد")
    cleaned_overrides = {}
    for key, value in raw_overrides.items():
        if key not in APPEARANCE_COLOR_KEYS:
            continue
        if not isinstance(value, str):
            raise AppearanceConfigValidationError(f"رنگِ «{key}» نامعتبر است")
        try:
            validate_hex_color(value)
        except DjangoValidationError as exc:
            raise AppearanceConfigValidationError("; ".join(exc.messages)) from exc
        cleaned_overrides[key] = value
    cleaned["color_overrides"] = cleaned_overrides

    font = config.get("font", APPEARANCE_CONFIG_DEFAULTS["font"])
    if font not in appearance_registry.FONT_CHOICES:
        raise AppearanceConfigValidationError("فونتِ انتخاب‌شده در فهرستِ فونت‌های مجاز نیست")
    cleaned["font"] = font

    for field, min_v, max_v in (("radius", 0, 32), ("button_radius", 0, 32)):
        try:
            value = int(config.get(field, APPEARANCE_CONFIG_DEFAULTS[field]))
        except (TypeError, ValueError):
            raise AppearanceConfigValidationError(f"مقدار «{field}» باید عدد باشد") from None
        cleaned[field] = max(min_v, min(max_v, value))

    density = config.get("density", APPEARANCE_CONFIG_DEFAULTS["density"])
    if density not in appearance_registry.DENSITY_CHOICES:
        raise AppearanceConfigValidationError("تراکمِ انتخاب‌شده نامعتبر است")
    cleaned["density"] = density

    motion = config.get("motion", APPEARANCE_CONFIG_DEFAULTS["motion"])
    if motion not in appearance_registry.MOTION_CHOICES:
        raise AppearanceConfigValidationError("سبکِ حرکتِ انتخاب‌شده نامعتبر است")
    cleaned["motion"] = motion

    type_scale = config.get("type_scale", APPEARANCE_CONFIG_DEFAULTS["type_scale"])
    if type_scale not in appearance_registry.TYPE_SCALE_CHOICES:
        raise AppearanceConfigValidationError("اندازه‌ی متنِ انتخاب‌شده نامعتبر است")
    cleaned["type_scale"] = type_scale

    button_style = config.get("button_style", APPEARANCE_CONFIG_DEFAULTS["button_style"])
    if button_style not in appearance_registry.BUTTON_STYLE_CHOICES:
        raise AppearanceConfigValidationError("سبکِ دکمه‌یِ انتخاب‌شده نامعتبر است")
    cleaned["button_style"] = button_style

    image_fit = config.get("image_fit", APPEARANCE_CONFIG_DEFAULTS["image_fit"])
    if image_fit not in appearance_registry.IMAGE_FIT_CHOICES:
        raise AppearanceConfigValidationError("نوعِ نمایشِ تصویرِ انتخاب‌شده نامعتبر است")
    cleaned["image_fit"] = image_fit

    image_hover = config.get("image_hover", APPEARANCE_CONFIG_DEFAULTS["image_hover"])
    if image_hover not in appearance_registry.IMAGE_HOVER_CHOICES:
        raise AppearanceConfigValidationError("افکتِ هاورِ تصویرِ انتخاب‌شده نامعتبر است")
    cleaned["image_hover"] = image_hover

    # Family/Preset — تصمیمِ مالک Q-01/Q-02. family_slug=None (پیش‌فرض)
    # یعنی «بدونِ Family»، همان DOMِ مشترکِ ۱۰ Templateِ قدیمی. هر دو
    # مستقل از Palette اعتبارسنجی می‌شوند (Palette همیشه Global می‌ماند،
    # حتی وقتی Family انتخاب شده — تصمیمِ صریحِ مالک).
    family_slug = config.get("family_slug", APPEARANCE_CONFIG_DEFAULTS["family_slug"])
    if family_slug is not None and family_registry.get_family(family_slug) is None:
        raise AppearanceConfigValidationError(f"خانواده‌ی «{family_slug}» در دسترس نیست")
    cleaned["family_slug"] = family_slug

    preset_slug = config.get("preset_slug", APPEARANCE_CONFIG_DEFAULTS["preset_slug"])
    if preset_slug is not None:
        preset = preset_registry.get_preset(preset_slug)
        if preset is None:
            raise AppearanceConfigValidationError(f"پیش‌تنظیمِ «{preset_slug}» در دسترس نیست")
        if family_slug is None or preset.family_slug != family_slug:
            raise AppearanceConfigValidationError("پیش‌تنظیمِ انتخاب‌شده متعلق به این خانواده نیست")
    cleaned["preset_slug"] = preset_slug

    return cleaned


def get_or_create_layout(store) -> StorefrontLayout:
    return StorefrontLayout.provision_for(store)


def _next_version_number(layout: StorefrontLayout) -> int:
    last = layout.versions.order_by("-version_number").first()
    return (last.version_number + 1) if last else 1


#: نگاشتِ نوعِ رسانه‌یِ مقیّد به section → (نامِ related_name رویِ
#: StorefrontSection، لیستِ فیلدهایی که مستقیماً کپی می‌شوند بدونِ تغییرِ
#: معنا). ``asset`` فیلدهای FKِ اشاره‌گر به ``MediaAsset`` عمداً از این
#: لیست جدا نگه داشته شده‌اند (نگاه کنید به ``_ASSET_FK_FIELDS`` پایین) —
#: تصمیمِ مالک ۴/۵: کلون‌کردنِ Placement هرگز نباید Placementِ منبع (که
#: معمولاً به نسخه‌ی Published تعلق دارد) را تغییر دهد؛ فقط یک ردیفِ
#: **جدید** با همان اشاره‌گرِ MediaAsset ساخته می‌شود.
_SCOPED_MEDIA_MODELS = ("hero_slides", "banners", "story_items")

#: هر مدلِ Placement کدام فیلدهایِ FKِ اشاره‌گر به ``MediaAsset`` دارد —
#: این‌ها هم دقیقاً مثلِ بقیه‌ی فیلدها کپی می‌شوند (همان مقدارِ
#: asset_id، نه ساختنِ asset تازه) چون تصمیمِ مالک ۵ صریحاً می‌گوید
#: Placementِ کلون‌شده باید به **همان** ``MediaAsset`` اشاره کند، نه یک
#: کپیِ تازه از فایل.
_ASSET_FK_FIELDS = {
    "hero_slides": ("desktop_asset_id", "mobile_asset_id"),
    "banners": ("desktop_asset_id", "mobile_asset_id"),
    "story_items": ("image_asset_id",),
}

#: فیلدهایِ محتواییِ غیرِ FK هر مدلِ Placement — کپی می‌شوند دقیقاً همان‌طور
#: که هستند (بدونِ منطقِ خاص).
_PLACEMENT_CONTENT_FIELDS = {
    "hero_slides": (
        "title", "subtitle", "button_label", "show_button", "is_active", "display_order",
        "destination_type", "destination_category_id", "destination_product_id",
        "destination_brand_id", "destination_collection_id", "destination_external_url",
        "open_in_new_tab",
    ),
    "banners": (
        "title", "description", "button_label", "show_button", "is_active", "display_order",
        "destination_type", "destination_category_id", "destination_product_id",
        "destination_brand_id", "destination_collection_id", "destination_external_url",
        "open_in_new_tab",
    ),
    "story_items": (
        "title", "is_active", "display_order",
        "destination_type", "destination_category_id", "destination_product_id",
        "destination_brand_id", "destination_collection_id", "destination_external_url",
        "open_in_new_tab",
    ),
}


def _clone_section_scoped_media(source_section: StorefrontSection, target_section: StorefrontSection) -> None:
    """برایِ ``source_section`` (متعلق به نسخه‌ی منبع — معمولاً Published)،
    هر ردیفِ رسانه‌یِ section-scoped (``HeroSlide``/``PromotionalBanner``/
    ``StoryRailItem`` که ``section == source_section``) را روی
    ``target_section`` (بخشِ تازه‌کلون‌شده، متعلق به نسخه‌ی جدید) **کلون
    می‌کند** — یعنی یک ردیفِ کاملاً جدید می‌سازد، هرگز ردیفِ منبع را
    UPDATE یا MOVE نمی‌کند (تصمیمِ مالک ۴: «Published و Draft باید همزمان
    و مستقل قابل‌رندر باشند»).

    ردیفِ جدید دقیقاً همان فیلدهایِ FKِ MediaAsset را کپی می‌کند (همان
    asset_id — بدونِ ساختنِ asset تازه، بدونِ کپیِ بایتِ فایل؛ تصمیمِ
    مالک ۵) — پس اگر Placementِ منبع به یک ``MediaAsset`` مشترک اشاره
    می‌کند، Placementِ جدیدِ کلون‌شده هم به **همان** ردیفِ ``MediaAsset``
    اشاره می‌کند."""
    from apps.content.models import HeroSlide, PromotionalBanner, StoryRailItem

    model_by_related_name = {
        "hero_slides": HeroSlide, "banners": PromotionalBanner, "story_items": StoryRailItem,
    }
    for related_name in _SCOPED_MEDIA_MODELS:
        model = model_by_related_name[related_name]
        source_rows = getattr(source_section, related_name).all()
        clones = []
        for row in source_rows:
            kwargs = {"store_id": row.store_id, "section": target_section}
            for field in _PLACEMENT_CONTENT_FIELDS[related_name]:
                kwargs[field] = getattr(row, field)
            for field in _ASSET_FK_FIELDS[related_name]:
                kwargs[field] = getattr(row, field)
            # فیلدهایِ فایلِ legacy (desktop_image/mobile_image/image) عمداً
            # کپی نمی‌شوند — این کلون فقط برایِ Placementهایی معنا دارد که
            # از قبل به یک MediaAsset منتقل شده‌اند (نگاه کنید به
            # STOREFRONT_BUILDER_V2_PHASE_0_5_REPORT.md، محدودیت‌ها). یک
            # Placementِ section-scoped که هنوز asset FK ندارد (خیلی
            # قدیمی، از قبلِ Phase 0.5 و هرگز ازطریقِ فرمِ ویرایش لمس‌
            # نشده) در این کلون نادیده گرفته می‌شود — نه خطا، نه کرش؛ فقط
            # در نسخه‌ی جدید ظاهر نمی‌شود، دقیقاً همان رفتاری که پیش از
            # این Fix هم برایِ *همه‌ی* Placementهایِ section-scoped وجود
            # داشت (نگاه کنید به بخشِ «محدودیت‌های باقی‌مانده» در گزارش).
            has_any_asset = any(kwargs[f] for f in _ASSET_FK_FIELDS[related_name])
            if not has_any_asset:
                continue
            clones.append(model(**kwargs))
        if clones:
            model.objects.bulk_create(clones)


def _clone_version_content(source: StorefrontLayoutVersion | None, target: StorefrontLayoutVersion) -> None:
    """کپی هدر/فوتر/تمامِ صفحات/بخش‌های ``source`` روی ``target``.

    Phase 1A (تصمیمِ مالک ۲/۳/۵ — ارتقاءِ کلون از «فقط صفحه اصلی» به
    «همه‌یِ شش صفحه»):
    - ``target`` از قبل هر شش ``StorefrontPage`` را دارد (خودکار، از
      طریقِ ``StorefrontLayoutVersion.save()`` — نگاه کنید به
      ``models.py``) — این تابع فقط بخش‌هایِ **موجودِ** هر صفحه‌یِ منبع
      را رویِ صفحه‌یِ متناظرِ همان نوع در ``target`` کلون می‌کند؛ صفحاتی
      که هنوز هیچ بخشی ندارند (فعلاً همه‌یِ صفحات غیرِ صفحه‌اصلی، چون
      Builder UI هنوز فقط صفحه‌اصلی را ویرایش می‌کند) دقیقاً خالی
      می‌مانند — نه محتوایِ ساختگی.
    - هر ``StorefrontSection`` کلون‌شده ``stable_id`` را دقیقاً حفظ می‌کند
      (همان بخشِ منطقی است، فقط در نسخه‌ی دیگر) — نه یک UUID تازه.
    - برایِ هر بخشِ کلون‌شده، رسانه‌یِ section-scoped (HeroSlide/
      PromotionalBanner/StoryRailItem) هم کلون می‌شود — هرگز از بخشِ منبع
      حذف/جابه‌جا نمی‌شود، فقط یک ردیفِ جدید با همان ارجاعِ MediaAsset
      ساخته می‌شود. Placementِ منبع (که معمولاً به نسخه‌ی Published تعلق
      دارد) کاملاً دست‌نخورده می‌ماند — Phase 0.5's مدل رسانه بدونِ هیچ
      تغییری اینجا دوباره استفاده می‌شود (نه بازنویسی)."""
    if source is None:
        return
    target.header_config = dict(source.header_config or {})
    target.footer_config = dict(source.footer_config or {})
    target.appearance_config = dict(source.appearance_config or {})
    target.save(update_fields=["header_config", "footer_config", "appearance_config"])

    target_pages_by_type = {p.page_type: p for p in target.pages.all()}
    for source_page in source.pages.all():
        target_page = target_pages_by_type.get(source_page.page_type)
        if target_page is None:
            # نباید هرگز رخ دهد — ``StorefrontLayoutVersion.save()`` همیشه
            # هر شش صفحه را می‌سازد — اما به‌جایِ کرش، defensive skip
            # (همان الگویِ section_key ناشناخته در render_service).
            continue

        source_sections = list(source_page.sections.order_by("order", "id"))
        cloned_sections = [
            StorefrontSection(
                page=target_page, section_key=s.section_key, order=s.order,
                is_active=s.is_active, settings=dict(s.settings or {}),
                stable_id=s.stable_id,
            )
            for s in source_sections
        ]
        if not cloned_sections:
            continue
        StorefrontSection.objects.bulk_create(cloned_sections)

        # bulk_create روی بک‌اندهایی که RETURNING را پشتیبانی می‌کنند (PostgreSQL،
        # SQLite جدید) PKهایِ تازه را روی خودِ آبجکت‌ها پر می‌کند — اما برایِ
        # اطمینانِ کامل (و سازگاری با هر بک‌اندی)، دوباره از دیتابیس با
        # ``stable_id`` بازخوانی می‌کنیم؛ همین ``stable_id`` تنها کلیدِ قابلِ‌اعتماد
        # برایِ نگاشتِ «این بخشِ منبع → کدام بخشِ کلون‌شده» است (نه ترتیب، نه
        # section_key، چون ممکن است چند نمونه از یک section_key وجود داشته باشد).
        # اسکوپِ این map به همینِ صفحه محدود است (نه کلِ نسخه) — دقیقاً
        # همان معنایِ (page, stable_id) که Phase 1A محدوده‌یِ یکتاییِ
        # stable_id را به آن تغییر داده.
        cloned_by_stable_id = {
            row.stable_id: row for row in target_page.sections.all()
        }
        for source_section in source_sections:
            target_section = cloned_by_stable_id.get(source_section.stable_id)
            if target_section is None:
                continue
            _clone_section_scoped_media(source_section, target_section)


@transaction.atomic
def get_or_create_draft(store, *, user=None) -> StorefrontLayoutVersion:
    """Draft فعلی فروشگاه را برمی‌گرداند؛ اگر وجود نداشته باشد، یکی می‌سازد.

    اگر این فروشگاه هرگز هیچ نسخه‌ای نداشته (نه Draft، نه منتشرشده، نه
    بایگانی‌شده) — یعنی اولین بار است که ویرایشگر باز می‌شود — Draft از
    محتوای صفحه اصلی قدیمی (hard-coded) همین فروشگاه بوت‌استرپ می‌شود
    (``bootstrap_service``) تا هرگز بومِ خالی نشان داده نشود. در غیر این
    صورت از روی نسخه‌ی منتشرشده‌ی فعلی کپی می‌شود — تا ویرایشگر همیشه از
    وضعیت فعلیِ زنده شروع شود.
    """
    layout = get_or_create_layout(store)
    if layout.draft_version_id:
        return layout.draft_version

    enforce_rate_limit("storefront_layout.new_draft", str(store.pk), **_NEW_DRAFT_RATE_LIMIT)

    is_first_ever_version = not layout.versions.exists()
    draft = StorefrontLayoutVersion.objects.create(
        layout=layout, version_number=_next_version_number(layout),
        status=StorefrontLayoutVersion.Status.DRAFT,
        source=(
            StorefrontLayoutVersion.Source.LEGACY_BOOTSTRAP
            if is_first_ever_version else StorefrontLayoutVersion.Source.MANUAL
        ),
        created_by=user if (user and user.is_authenticated) else None,
    )
    if is_first_ever_version:
        from . import bootstrap_service
        bootstrap_service.apply_bootstrap_content(draft, store)
    else:
        _clone_version_content(layout.published_version, draft)
    layout.draft_version = draft
    layout.save(update_fields=["draft_version", "updated_at"])
    return draft


@transaction.atomic
def discard_draft(store) -> None:
    """Draft فعلی را (اگر وجود دارد) حذف می‌کند — بدون اثر روی نسخه منتشرشده."""
    layout = get_or_create_layout(store)
    if not layout.draft_version_id:
        return
    draft = layout.draft_version
    layout.draft_version = None
    layout.save(update_fields=["draft_version", "updated_at"])
    draft.delete()


@transaction.atomic
def publish(store, *, user=None) -> StorefrontLayoutVersion:
    """Draft فعلی را منتشر می‌کند — عملیات اتمیک، فقط تعویض اشاره‌گر.

    نسخه‌ی منتشرشده‌ی قبلی (اگر وجود داشت) به ARCHIVED منتقل می‌شود؛
    Storefront عمومی از این لحظه به بعد نسخه جدید را می‌بیند.
    """
    enforce_rate_limit("storefront_layout.publish", str(store.pk), **_PUBLISH_RATE_LIMIT)

    layout = get_or_create_layout(store)
    draft = layout.draft_version
    if draft is None:
        raise NoDraftToPublishError("هیچ پیش‌نویسی برای انتشار وجود ندارد")

    draft.content_fingerprint = draft.compute_fingerprint()
    draft.status = StorefrontLayoutVersion.Status.PUBLISHED
    draft.published_at = timezone.now()
    draft.save(update_fields=["content_fingerprint", "status", "published_at", "updated_at"])

    previous_published = layout.published_version
    if previous_published is not None:
        previous_published.status = StorefrontLayoutVersion.Status.ARCHIVED
        previous_published.save(update_fields=["status", "updated_at"])

    layout.published_version = draft
    layout.draft_version = None
    layout.uses_visual_storefront_layout = True
    layout.save(update_fields=["published_version", "draft_version", "uses_visual_storefront_layout", "updated_at"])
    return draft


def list_versions(store):
    """تاریخچه‌ی کامل نسخه‌ها (منتشرشده + بایگانی‌شده + پیش‌نویس فعلی، اگر باشد)."""
    layout = get_or_create_layout(store)
    return layout.versions.order_by("-version_number")


@transaction.atomic
def restore_version(store, version_id, *, user=None) -> StorefrontLayoutVersion:
    """محتوای یک نسخه‌ی قدیمی را در یک Draft **جدید** بازمی‌گرداند — هرگز
    مستقیماً منتشر نمی‌شود. اگر Draft فعلی از قبل وجود دارد، جایگزین می‌شود
    (تأیید/هشدار «تغییرات ذخیره‌نشده» مسئولیت لایه UI است، نه این سرویس)."""
    enforce_rate_limit("storefront_layout.restore", str(store.pk), **_RESTORE_RATE_LIMIT)

    layout = get_or_create_layout(store)
    try:
        source = layout.versions.get(pk=version_id)
    except StorefrontLayoutVersion.DoesNotExist:
        raise CrossStoreVersionError(f"نسخه {version_id} متعلق به این فروشگاه نیست") from None

    if layout.draft_version_id:
        old_draft = layout.draft_version
        layout.draft_version = None
        layout.save(update_fields=["draft_version", "updated_at"])
        old_draft.delete()

    new_draft = StorefrontLayoutVersion.objects.create(
        layout=layout, version_number=_next_version_number(layout),
        status=StorefrontLayoutVersion.Status.DRAFT,
        source=StorefrontLayoutVersion.Source.RESTORED,
        label=f"بازگردانی از نسخه {source.version_number}",
        created_by=user if (user and user.is_authenticated) else None,
    )
    _clone_version_content(source, new_draft)
    layout.draft_version = new_draft
    layout.save(update_fields=["draft_version", "updated_at"])
    return new_draft


@transaction.atomic
def apply_industry_layout(store, industry_template, *, user=None, force: bool = False) -> StorefrontLayoutVersion:
    """چیدمان پیشنهادی یک صنف را در یک Draft **جدید** اعمال می‌کند — هرگز
    مستقیماً منتشر نمی‌شود (همان قانون ``restore_version``).

    اگر فروشگاه از قبل یک نسخه‌ی منتشرشده دارد (یعنی صاحب فروشگاه حداقل
    یک بار storefront بصری را منتشر کرده و ممکن است آن را سفارشی کرده
    باشد)، بدون ``force=True`` رد می‌شود — این دقیقاً همان تأیید صریحی است
    که تصمیم کاربر برای «هرگز رونویسی بی‌صدا» می‌خواهد؛ لایه‌ی View مسئول
    گرفتن تأیید از کاربر (checkbox/confirm) پیش از پاس‌دادن ``force=True``
    است. Draft فعلی (اگر وجود دارد) جایگزین می‌شود، دقیقاً مثل ``restore_version``."""
    enforce_rate_limit("storefront_layout.new_draft", str(store.pk), **_NEW_DRAFT_RATE_LIMIT)

    layout = get_or_create_layout(store)
    if layout.published_version_id and not force:
        raise StorefrontAlreadyPublishedError(
            "این فروشگاه از قبل یک نسخه‌ی منتشرشده دارد — برای اعمال چیدمان صنف، تأیید صریح لازم است"
        )

    if layout.draft_version_id:
        old_draft = layout.draft_version
        layout.draft_version = None
        layout.save(update_fields=["draft_version", "updated_at"])
        old_draft.delete()

    new_draft = StorefrontLayoutVersion.objects.create(
        layout=layout, version_number=_next_version_number(layout),
        status=StorefrontLayoutVersion.Status.DRAFT,
        source=StorefrontLayoutVersion.Source.INDUSTRY_TEMPLATE,
        label=f"چیدمان صنف «{industry_template.name}»",
        created_by=user if (user and user.is_authenticated) else None,
    )
    from . import bootstrap_service
    bootstrap_service.apply_industry_content(new_draft, store, industry_template)
    layout.draft_version = new_draft
    layout.save(update_fields=["draft_version", "updated_at"])
    return new_draft
