"""Section Registry — allowlist سرور-محورِ انواع بخش قابل استفاده در سازنده بصری.

طبق بخش ۱۲ گزارش ممیزی (``docs/reports/STOREFRONT_VISUAL_BUILDER_AUDIT.md``):
این یک دیکشنری **ثابت پایتونی** است، نه دیتابیس — بارگذاری template همیشه از
همین نگاشت ثابت انجام می‌شود، هرگز از رشته‌ای که کاربر کنترل می‌کند. این
دقیقاً همان چیزی است که از موارد زیر جلوگیری می‌کند:

- بارگذاری template دلخواه (``template_name`` همیشه هارد‌کد همین‌جاست)
- import پویا/``eval`` بر اساس داده کاربر (هیچ‌کدام استفاده نمی‌شود)
- ثبت نوع section نامعتبر (``StorefrontSection.section_key`` همیشه در
  سرویس در برابر ``SECTION_REGISTRY`` چک می‌شود، نه صرفاً در دیتابیس)

هر ``SectionDefinition`` یک نوع settings schema (تابع اعتبارسنجی) دارد که
شکل JSON را چک می‌کند؛ اعتبارسنجی مالکیت Store برای ارجاعات (محصول/دسته/
برند/بنر) در ``services/section_data_service.py`` انجام می‌شود، نه اینجا.
"""

from __future__ import annotations

import dataclasses
from typing import Callable


@dataclasses.dataclass(frozen=True)
class SectionDefinition:
    key: str
    label_fa: str
    icon: str
    template_name: str
    validate_settings: Callable[[dict], dict]
    default_settings: Callable[[], dict]
    min_instances: int = 0
    max_instances: int | None = None
    duplicable: bool = True
    removable: bool = True
    #: آیا این نوع بخش تنظیمات قابل‌ویرایش (فرم) دارد؟ تا فازِ C فقط
    #: انواعی که واقعاً محتوای قابل‌تنظیم داشتند (rich_text، image_text،
    #: product_section) این پرچم را True داشتند. از فازِ D به بعد **همه‌ی**
    #: انواع True هستند — چون همه اکنون حداقل بلوکِ «تنظیماتِ نمایش در
    #: دستگاه‌ها» (``responsive``) را دارند؛ این پرچم دیگر توسطِ کدِ
    #: دستی در registry تنظیم نمی‌شود، بلکه توسطِ ``_finalize_registry``
    #: پایینِ همین فایل، یکنواخت روی True قرار می‌گیرد.
    has_settings_form: bool = False


def _passthrough_dict(raw: dict) -> dict:
    """اعتبارسنجی placeholder — با اعتبارسنجی دقیق در چکپوینت‌های بعدی جایگزین می‌شود."""
    if not isinstance(raw, dict):
        raise ValueError("تنظیمات باید یک شیء JSON باشد")
    return raw


def _empty_defaults() -> dict:
    return {}


_MAX_RICH_TEXT_LENGTH = 20_000
_MAX_IMAGE_TEXT_TITLE_LENGTH = 200


def _validate_rich_text_settings(raw: dict) -> dict:
    """``body_html`` — خودِ رشته در سرویس ذخیره می‌شود؛ پاک‌سازیِ HTML واقعی
    در زمان رندر توسط ``sanitize_rich_text`` (همان ساینیتایزر allowlist
    توضیحات کالا) انجام می‌شود، نه اینجا — اینجا فقط شکل/طول ورودی چک
    می‌شود."""
    if not isinstance(raw, dict):
        raise ValueError("تنظیمات باید یک شیء JSON باشد")
    body_html = str(raw.get("body_html", ""))
    if len(body_html) > _MAX_RICH_TEXT_LENGTH:
        raise ValueError(f"متن نباید بیشتر از {_MAX_RICH_TEXT_LENGTH} نویسه باشد")
    return {"body_html": body_html}


#: منابع مجازِ داده‌یِ بخشِ محصول (فاز C) — enum بسته؛ هر مقدارِ دیگر رد
#: می‌شود. این تنها لیستِ مجاز در کل کدبیس است — مصرف‌کننده‌ها (فرم
#: ادیتور، ``section_data_service``) باید همین ثابت را import کنند، نه
#: رشته را جای دیگری تکرار کنند.
PRODUCT_SECTION_DATA_SOURCES = (
    "collection", "category", "brand", "manual",
    "newest", "discounted", "best_sellers", "most_viewed",
)
#: منابعی که به یک شیءِ واحدِ دیگر (کالکشن/دسته/برند) ارجاع می‌دهند —
#: این‌ها به ``source_id`` نیاز دارند.
_SINGLE_REFERENCE_SOURCES = {"collection", "category", "brand"}

PRODUCT_SECTION_DISPLAY_MODES = ("carousel", "grid")

_PRODUCT_SECTION_MIN_LIMIT = 2
_PRODUCT_SECTION_MAX_LIMIT = 24
_PRODUCT_SECTION_DEFAULT_LIMIT = 8
_MAX_PRODUCT_SECTION_TITLE_LENGTH = 60
_MAX_PRODUCT_SECTION_SUBTITLE_LENGTH = 150
#: سقفِ تعدادِ کالای دستی — به‌قدرِ کافی بزرگ‌تر از بیشینه‌یِ item_limit
#: تا مرچنت بتواند بیش از حدِ نمایش، کالا انتخاب کند (مثلاً برایِ چرخشِ
#: بعدی)، اما نه نامحدود.
_MAX_MANUAL_PRODUCT_IDS = 60


class ProductSectionSettingsError(ValueError):
    """شکلِ خامِ تنظیماتِ بخشِ محصول نامعتبر است (فقط اعتبارسنجیِ شکل/enum/
    بازه — مالکیتِ Store برایِ ``source_id``/``product_ids`` در
    ``services/section_data_service.py`` چک می‌شود، نه اینجا)."""


def _clean_positive_int_list(raw_list, *, max_len: int) -> list[int]:
    if not isinstance(raw_list, list):
        raise ProductSectionSettingsError("فهرستِ کالاها باید یک آرایه باشد")
    cleaned: list[int] = []
    seen = set()
    for value in raw_list:
        try:
            int_value = int(value)
        except (TypeError, ValueError):
            raise ProductSectionSettingsError("شناسه‌ی کالا نامعتبر است") from None
        if int_value <= 0 or int_value in seen:
            continue
        seen.add(int_value)
        cleaned.append(int_value)
    return cleaned[:max_len]


def _validate_product_section_settings(raw: dict) -> dict:
    """قراردادِ تنظیماتِ «بخشِ محصول» (فازِ C) — تنها اعتبارسنجیِ شکل/
    enum/بازه‌یِ ایمن؛ هیچ کوئریِ دیتابیس/چکِ مالکیتِ Store اینجا انجام
    نمی‌شود (طبقِ همان تفکیکِ مسئولیتی که مستندسازیِ بالایِ فایل توصیف
    می‌کند). خروجی همیشه دقیقاً همین ۸ کلید را دارد — کلیدِ ناشناخته‌یِ
    ورودی بی‌صدا حذف می‌شود."""
    if not isinstance(raw, dict):
        raise ProductSectionSettingsError("تنظیمات باید یک شیء JSON باشد")

    data_source = raw.get("data_source")
    if data_source not in PRODUCT_SECTION_DATA_SOURCES:
        raise ProductSectionSettingsError("منبعِ داده‌یِ انتخاب‌شده نامعتبر است")

    display_mode = raw.get("display_mode")
    if display_mode not in PRODUCT_SECTION_DISPLAY_MODES:
        display_mode = "carousel"

    try:
        item_limit = int(raw.get("item_limit", _PRODUCT_SECTION_DEFAULT_LIMIT))
    except (TypeError, ValueError):
        raise ProductSectionSettingsError("تعدادِ کالا باید عدد باشد") from None
    item_limit = max(_PRODUCT_SECTION_MIN_LIMIT, min(_PRODUCT_SECTION_MAX_LIMIT, item_limit))

    show_view_all = raw.get("show_view_all", True)
    if not isinstance(show_view_all, bool):
        show_view_all = bool(show_view_all)

    title = str(raw.get("title", "")).strip()[:_MAX_PRODUCT_SECTION_TITLE_LENGTH]
    subtitle = str(raw.get("subtitle", "")).strip()[:_MAX_PRODUCT_SECTION_SUBTITLE_LENGTH]

    # source_id/product_ids فقط برایِ منبعِ متناظرشان معنا دارند — برایِ
    # بقیه همیشه به مقدارِ خنثی (None/[]) بازنشانی می‌شوند تا تنظیماتِ
    # ذخیره‌شده هرگز حاویِ ارجاعِ یتیمِ بی‌ربط به data_source فعلی نباشد.
    source_id = None
    if data_source in _SINGLE_REFERENCE_SOURCES:
        raw_source_id = raw.get("source_id")
        try:
            source_id = int(raw_source_id)
        except (TypeError, ValueError):
            raise ProductSectionSettingsError("مقصدِ انتخاب‌شده نامعتبر است") from None
        if source_id <= 0:
            raise ProductSectionSettingsError("مقصدِ انتخاب‌شده نامعتبر است")

    product_ids: list[int] = []
    if data_source == "manual":
        product_ids = _clean_positive_int_list(raw.get("product_ids", []), max_len=_MAX_MANUAL_PRODUCT_IDS)
        if not product_ids:
            raise ProductSectionSettingsError("برایِ «کالاهایِ دستی» باید حداقل یک کالا انتخاب شود")

    return {
        "data_source": data_source,
        "source_id": source_id,
        "product_ids": product_ids,
        "item_limit": item_limit,
        "display_mode": display_mode,
        "show_view_all": show_view_all,
        "title": title,
        "subtitle": subtitle,
    }


def _product_section_defaults() -> dict:
    return {
        "data_source": "newest",
        "source_id": None,
        "product_ids": [],
        "item_limit": _PRODUCT_SECTION_DEFAULT_LIMIT,
        "display_mode": "carousel",
        "show_view_all": True,
        "title": "",
        "subtitle": "",
    }


#: انواعی که واقعاً «ستون» به‌عنوان مفهوم بصری معنا دارد (فازِ D، بخشِ ۴
#: مشخصات) — کنترلِ تعدادِ ستون فقط برایِ این‌ها در فرمِ تنظیمات نمایش
#: داده می‌شود. توجهِ مهم: در این چک‌پوینت، اثرِ بصریِ واقعیِ تعدادِ
#: ستون فقط برایِ ``product_section`` پیاده‌سازی شده (تنها نوعی که از
#: ابتدا یک grid/carousel پارامتری دارد) — چهار نوعِ دیگر همچنان
#: تنظیمات را اعتبارسنجی/ذخیره می‌کنند (قراردادِ آینده‌نگر) اما چیدمانِ
#: ثابتِ فعلی‌شان (tiles/ردیفِ بنر/auto-fill) دست‌نخورده می‌ماند —
#: بازطراحیِ آن ۴ قالب یک کارِ جداگانه و بزرگ‌تر از scope این فاز است.
COLUMN_AWARE_SECTION_KEYS = frozenset({
    "product_section", "category_grid", "multi_banner", "promo_cards", "brand_carousel",
})

#: مقادیرِ مجازِ enum بستهٔ تعدادِ ستون به‌ازای هر دستگاه — طبقِ بخشِ ۴
#: مشخصات؛ هیچ عددِ دلخواهی پذیرفته نمی‌شود.
MOBILE_COLUMN_CHOICES = (1, 2)
TABLET_COLUMN_CHOICES = (1, 2, 3)
DESKTOP_COLUMN_CHOICES = (1, 2, 3, 4, 5, 6)

_DEFAULT_MOBILE_COLUMNS = 2
_DEFAULT_TABLET_COLUMNS = 3
_DEFAULT_DESKTOP_COLUMNS = 4


class ResponsiveSettingsError(ValueError):
    """شکلِ خامِ بلوکِ ``responsive`` نامعتبر است — پیامِ فارسیِ
    قابل‌نمایشِ مستقیم به تاجر."""


def _closed_column_choice(raw_value, choices: tuple[int, ...], *, default: int, field_label: str) -> int:
    if raw_value is None:
        return default
    try:
        value = int(raw_value)
    except (TypeError, ValueError):
        raise ResponsiveSettingsError(f"تعدادِ ستونِ «{field_label}» نامعتبر است") from None
    if value not in choices:
        raise ResponsiveSettingsError(f"تعدادِ ستونِ «{field_label}» باید یکی از مقادیرِ مجاز باشد")
    return value


def validate_responsive_settings(raw, *, supports_columns: bool) -> dict:
    """قراردادِ مشترکِ «تنظیماتِ نمایش در دستگاه‌ها» — یک بار نوشته شده و
    توسطِ همه‌یِ ۱۷ نوعِ section (نه فقط ``product_section``) استفاده
    می‌شود (بخشِ ۶ مشخصات: «Use one shared helper where possible»).

    غایب بودنِ کلیدِ ``responsive`` (سکشن‌هایِ از‌قبل‌موجود که هرگز از
    این فرم عبور نکرده‌اند) دقیقاً هم‌ارزِ خروجیِ پیش‌فرضِ این تابع
    است — یعنی «نمایان در همه‌یِ دستگاه‌ها»، رفتارِ فعلیِ بدونِ تغییر.
    کلیدِ ناشناخته بی‌صدا حذف می‌شود (همان قراردادِ
    ``layout_service.validate_header_config``/``validate_footer_config``)."""
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        raise ResponsiveSettingsError("تنظیماتِ نمایش در دستگاه‌ها باید یک شیء باشد")

    cleaned = {
        "hide_on_desktop": bool(raw.get("hide_on_desktop", False)),
        "hide_on_tablet": bool(raw.get("hide_on_tablet", False)),
        "hide_on_mobile": bool(raw.get("hide_on_mobile", False)),
    }
    if supports_columns:
        cleaned["desktop_columns"] = _closed_column_choice(
            raw.get("desktop_columns"), DESKTOP_COLUMN_CHOICES, default=_DEFAULT_DESKTOP_COLUMNS, field_label="دسکتاپ",
        )
        cleaned["tablet_columns"] = _closed_column_choice(
            raw.get("tablet_columns"), TABLET_COLUMN_CHOICES, default=_DEFAULT_TABLET_COLUMNS, field_label="تبلت",
        )
        cleaned["mobile_columns"] = _closed_column_choice(
            raw.get("mobile_columns"), MOBILE_COLUMN_CHOICES, default=_DEFAULT_MOBILE_COLUMNS, field_label="موبایل",
        )
    return cleaned


def default_responsive_settings(*, supports_columns: bool) -> dict:
    """پیش‌فرضِ بلوکِ ``responsive`` — دقیقاً معادلِ عبور از
    ``validate_responsive_settings(None, ...)`` (نمایان همه‌جا، ستونِ
    پیش‌فرض)، جدا نوشته شده فقط تا ``default_settings`` نیازی به
    اعتبارسنجیِ یک دیکشنریِ خالی نداشته باشد."""
    return validate_responsive_settings(None, supports_columns=supports_columns)


def _with_responsive(section_key: str, validate_fn, default_fn):
    """هر جفتِ (validate_settings, default_settings) موجود را با پشتیبانیِ
    بلوکِ ``responsive`` می‌پوشاند — منطقِ خودِ نوع (rich_text/image_text/
    product_section/passthrough) کاملاً دست‌نخورده و بی‌خبر از این پوشش
    باقی می‌ماند؛ کلیدِ ``responsive`` قبل از رسیدن به تابعِ اصلی جدا
    می‌شود و بعد از آن دوباره به نتیجه اضافه می‌شود."""
    supports_columns = section_key in COLUMN_AWARE_SECTION_KEYS

    def wrapped_validate(raw: dict) -> dict:
        if not isinstance(raw, dict):
            # اجازه بده تابعِ اصلیِ همان نوع خطایِ تایپ‌شده‌یِ خودش را
            # برایِ ورودیِ غیر-dict پرتاب کند (مثلاً ProductSectionSettingsError)
            # — این wrapper یک نوعِ خطایِ عمومی‌تر را جایگزینِ آن نمی‌کند.
            return validate_fn(raw)
        responsive_raw = raw.get("responsive")
        base_raw = {k: v for k, v in raw.items() if k != "responsive"}
        cleaned = validate_fn(base_raw)
        cleaned["responsive"] = validate_responsive_settings(responsive_raw, supports_columns=supports_columns)
        return cleaned

    def wrapped_default() -> dict:
        base = default_fn()
        return {**base, "responsive": default_responsive_settings(supports_columns=supports_columns)}

    return wrapped_validate, wrapped_default


def _validate_image_text_settings(raw: dict) -> dict:
    if not isinstance(raw, dict):
        raise ValueError("تنظیمات باید یک شیء JSON باشد")
    from django.core.exceptions import ValidationError

    from apps.content.models import validate_external_url

    title = str(raw.get("title", ""))[:_MAX_IMAGE_TEXT_TITLE_LENGTH]
    body_html = str(raw.get("body_html", ""))[:_MAX_RICH_TEXT_LENGTH]
    image_url = str(raw.get("image_url", "")).strip()
    if image_url:
        try:
            validate_external_url(image_url)
        except ValidationError as exc:
            raise ValueError("; ".join(exc.messages)) from exc
    position = raw.get("image_position") if raw.get("image_position") in ("left", "right") else "right"
    return {"title": title, "body_html": body_html, "image_url": image_url, "image_position": position}


# ---------------------------------------------------------------- ثبت انواع بخش

# تعاریف کامل settings-schema هر کلید در چکپوینت‌های ۱۱ تا ۱۴ (بنر/دسته/
# محصول/متن غنی) اضافه می‌شود؛ اینجا فقط استخوان‌بندی allowlist با
# اعتبارسنج‌های placeholder ایمن (رد هر چیز غیر-dict) ثبت می‌شود تا خودِ
# Registry از روز اول قابل‌اعتماد و قابل‌تست باشد.
_BASE_SECTION_REGISTRY: dict[str, SectionDefinition] = {
    "announcement_bar": SectionDefinition(
        key="announcement_bar", label_fa="نوار اعلان", icon="megaphone",
        template_name="storefront_builder/sections/announcement_bar.html",
        validate_settings=_passthrough_dict, default_settings=_empty_defaults,
        max_instances=1, duplicable=False, removable=True,
    ),
    "hero_banner": SectionDefinition(
        key="hero_banner", label_fa="بنر هیرو", icon="image",
        template_name="storefront_builder/sections/hero_banner.html",
        validate_settings=_passthrough_dict, default_settings=_empty_defaults,
        max_instances=1, duplicable=False, removable=True,
    ),
    "image_slider": SectionDefinition(
        key="image_slider", label_fa="اسلایدر تصویر", icon="images",
        template_name="storefront_builder/sections/image_slider.html",
        validate_settings=_passthrough_dict, default_settings=_empty_defaults,
        duplicable=True, removable=True,
    ),
    "single_banner": SectionDefinition(
        key="single_banner", label_fa="بنر تکی", icon="image",
        template_name="storefront_builder/sections/single_banner.html",
        validate_settings=_passthrough_dict, default_settings=_empty_defaults,
        duplicable=True, removable=True,
    ),
    "multi_banner": SectionDefinition(
        key="multi_banner", label_fa="ردیف چند بنری", icon="layout-grid",
        template_name="storefront_builder/sections/multi_banner.html",
        validate_settings=_passthrough_dict, default_settings=_empty_defaults,
        duplicable=True, removable=True,
    ),
    "category_grid": SectionDefinition(
        key="category_grid", label_fa="گرید دسته‌بندی", icon="grid",
        template_name="storefront_builder/sections/category_grid.html",
        validate_settings=_passthrough_dict, default_settings=_empty_defaults,
        duplicable=True, removable=True,
    ),
    "featured_products": SectionDefinition(
        key="featured_products", label_fa="محصولات ویژه", icon="star",
        template_name="storefront_builder/sections/featured_products.html",
        validate_settings=_passthrough_dict, default_settings=_empty_defaults,
        duplicable=True, removable=True,
    ),
    "newest_products": SectionDefinition(
        key="newest_products", label_fa="جدیدترین محصولات", icon="sparkles",
        template_name="storefront_builder/sections/newest_products.html",
        validate_settings=_passthrough_dict, default_settings=_empty_defaults,
        duplicable=True, removable=True,
    ),
    "best_sellers": SectionDefinition(
        key="best_sellers", label_fa="پرفروش‌ترین‌ها", icon="trending-up",
        template_name="storefront_builder/sections/best_sellers.html",
        validate_settings=_passthrough_dict, default_settings=_empty_defaults,
        duplicable=True, removable=True,
    ),
    "discounted_products": SectionDefinition(
        key="discounted_products", label_fa="محصولات تخفیف‌دار", icon="percent",
        template_name="storefront_builder/sections/discounted_products.html",
        validate_settings=_passthrough_dict, default_settings=_empty_defaults,
        duplicable=True, removable=True,
    ),
    "amazing_offers": SectionDefinition(
        key="amazing_offers", label_fa="پیشنهادهای شگفت‌انگیز", icon="zap",
        template_name="storefront_builder/sections/amazing_offers.html",
        validate_settings=_passthrough_dict, default_settings=_empty_defaults,
        duplicable=True, removable=True,
    ),
    "brand_carousel": SectionDefinition(
        key="brand_carousel", label_fa="کاروسل برندها", icon="award",
        template_name="storefront_builder/sections/brand_carousel.html",
        validate_settings=_passthrough_dict, default_settings=_empty_defaults,
        duplicable=True, removable=True,
    ),
    "promo_cards": SectionDefinition(
        key="promo_cards", label_fa="کارت‌های تبلیغاتی", icon="layout",
        template_name="storefront_builder/sections/promo_cards.html",
        validate_settings=_passthrough_dict, default_settings=_empty_defaults,
        duplicable=True, removable=True,
    ),
    "rich_text": SectionDefinition(
        key="rich_text", label_fa="متن غنی", icon="text",
        template_name="storefront_builder/sections/rich_text.html",
        validate_settings=_validate_rich_text_settings, default_settings=lambda: {"body_html": ""},
        duplicable=True, removable=True, has_settings_form=True,
    ),
    "image_text": SectionDefinition(
        key="image_text", label_fa="متن و تصویر", icon="image-plus",
        template_name="storefront_builder/sections/image_text.html",
        validate_settings=_validate_image_text_settings,
        default_settings=lambda: {"title": "", "body_html": "", "image_url": "", "image_position": "right"},
        duplicable=True, removable=True, has_settings_form=True,
    ),
    "product_section": SectionDefinition(
        key="product_section", label_fa="بخش محصولات", icon="shopping-bag",
        template_name="storefront_builder/sections/product_section.html",
        validate_settings=_validate_product_section_settings, default_settings=_product_section_defaults,
        duplicable=True, removable=True, has_settings_form=True,
    ),
    "trust_features": SectionDefinition(
        key="trust_features", label_fa="ردیف اعتماد و ویژگی‌ها", icon="shield-check",
        template_name="storefront_builder/sections/trust_features.html",
        validate_settings=_passthrough_dict, default_settings=_empty_defaults,
        max_instances=1, duplicable=False, removable=True,
    ),
}


def _finalize_registry(base: dict[str, SectionDefinition]) -> dict[str, SectionDefinition]:
    """هر ۱۷ تعریفِ بالا را با پشتیبانیِ ``responsive`` می‌پوشاند و
    ``has_settings_form`` را یکنواخت True می‌کند (فازِ D) — منطقِ
    اختصاصیِ هر نوع (rich_text/image_text/product_section/passthrough)
    در ``_BASE_SECTION_REGISTRY`` بالا کاملاً دست‌نخورده می‌ماند؛ این تابع
    فقط یک لایه‌یِ یکسان روی همه می‌کشد، نه بازنویسیِ تک‌تکِ ۱۷ ورودی."""
    finalized = {}
    for key, definition in base.items():
        validate_fn, default_fn = _with_responsive(key, definition.validate_settings, definition.default_settings)
        finalized[key] = dataclasses.replace(
            definition, validate_settings=validate_fn, default_settings=default_fn, has_settings_form=True,
        )
    return finalized


SECTION_REGISTRY: dict[str, SectionDefinition] = _finalize_registry(_BASE_SECTION_REGISTRY)


class UnknownSectionTypeError(ValueError):
    def __init__(self, section_key: str):
        super().__init__(f"نوع بخش «{section_key}» در Section Registry ثبت نشده است")
        self.section_key = section_key


def get_definition(section_key: str) -> SectionDefinition:
    """تعریف یک section را برمی‌گرداند؛ اگر کلید نامعتبر باشد رد می‌کند.

    این تنها نقطه‌ورودی مجاز برای resolve کردن یک section_key به template
    است — هرگز مستقیماً از ``SECTION_REGISTRY`` در سرویس‌ها/ویوها resolve
    نکنید، همیشه از این تابع عبور کنید تا کلید ناشناخته همیشه fail-closed رد شود.
    """
    try:
        return SECTION_REGISTRY[section_key]
    except KeyError:
        raise UnknownSectionTypeError(section_key) from None


def list_definitions() -> list[SectionDefinition]:
    return list(SECTION_REGISTRY.values())


def is_valid_section_key(section_key: str) -> bool:
    return section_key in SECTION_REGISTRY
