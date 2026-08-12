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

#: شش نوعِ صفحه — دقیقاً همان رشته‌های ``StorefrontPage.PageType.values``
#: (``apps/storefront_builder/models.py``)، اینجا به‌شکلِ ثابتِ رشته‌ای
#: تکرار شده‌اند تا این ماژول (طبقِ فلسفه‌یِ صریحِ خودش در docstring بالا:
#: «دیکشنری ثابت پایتونی»، بدونِ وابستگی به مدل/دیتابیس) به ``models.py``
#: وابسته نشود — هماهنگی با enum واقعی توسطِ
#: ``test_section_registry.py::PageTypeConstantsMatchModelTests`` تضمین
#: می‌شود، نه import مستقیم.
PAGE_TYPE_HOME = "home"
PAGE_TYPE_PRODUCT_DETAIL = "product_detail"
PAGE_TYPE_LISTING = "listing"
PAGE_TYPE_COLLECTION = "collection"
PAGE_TYPE_SEARCH = "search"
PAGE_TYPE_CART = "cart"
ALL_PAGE_TYPES: frozenset[str] = frozenset({
    PAGE_TYPE_HOME, PAGE_TYPE_PRODUCT_DETAIL, PAGE_TYPE_LISTING,
    PAGE_TYPE_COLLECTION, PAGE_TYPE_SEARCH, PAGE_TYPE_CART,
})


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
    #: Phase 5: این نوع section روی کدام نوع(های) صفحه قابلِ افزودن است.
    #: پیش‌فرض یعنی «همه‌جا» — ۱۷ نوعِ محتواییِ عمومیِ موجود از پیش
    #: (hero/banner/rich_text/faq/...) بدونِ تغییرِ رفتار همین پیش‌فرض
    #: را نگه می‌دارند (طبقِ الزامِ صریحِ کار: «Home-only sections may be
    #: reusable where appropriate»). فقط انواعِ جدیدِ context-aware
    #: (``product_main``، ``cart_items``، ...) این را صریحاً به یک/دو
    #: نوعِ صفحه محدود می‌کنند.
    page_types: frozenset[str] = ALL_PAGE_TYPES
    #: آیا این نوع بخش تنظیمات قابل‌ویرایش (فرم) دارد؟ تا فازِ C فقط
    #: انواعی که واقعاً محتوای قابل‌تنظیم داشتند (rich_text، image_text،
    #: product_section) این پرچم را True داشتند. از فازِ D به بعد **همه‌ی**
    #: انواع True هستند — چون همه اکنون حداقل بلوکِ «تنظیماتِ نمایش در
    #: دستگاه‌ها» (``responsive``) را دارند؛ این پرچم دیگر توسطِ کدِ
    #: دستی در registry تنظیم نمی‌شود، بلکه توسطِ ``_finalize_registry``
    #: پایینِ همین فایل، یکنواخت روی True قرار می‌گیرد.
    has_settings_form: bool = False
    #: اگر True، این نوع در کتابخانه‌ی «افزودن بخش جدید» نمایش داده
    #: نمی‌شود (نمونه‌های موجود دست‌نخورده می‌مانند — رندر/تنظیمات/حذف
    #: کاملاً کار می‌کنند، فقط امکانِ ساختنِ نمونه‌ی *جدید* پنهان است).
    #: مورد استفاده: وقتی یک نوعِ دیگر (اینجا: تنظیماتِ نوارِ اعلانِ هدر)
    #: دقیقاً همان قابلیت را به‌شکلِ واقعاً قابل‌تنظیم پوشش می‌دهد — طبقِ
    #: الزامِ صریحِ کار «هرگز کنترلی که اثری ندارد نشان داده نشود».
    hidden_from_library: bool = False
    #: دسته‌بندیِ کسب‌وکاریِ کتابخانه‌ی «افزودن بخش جدید» (چکپوینتِ ۱۰) —
    #: پنج گروهِ ثابت (نگاه کنید به ``SECTION_LIBRARY_CATEGORIES``)، نه
    #: اصطلاحِ فنی/مدل. هر ورودی در ``_BASE_SECTION_REGISTRY`` صراحتاً
    #: مقدار می‌دهد — پیش‌فرض اینجا صرفاً محدودیتِ dataclass را دور می‌زند.
    category_fa: str = "محتوا"


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
#: حالتِ کارتِ محصول — enum بسته، مستقل از هر Familyی خاص (تصمیمِ مالک Q-09).
PRODUCT_SECTION_CARD_MODES = ("default", "campaign")

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


def _clean_positive_int_list(raw_list, *, max_len: int, error_cls=None, error_message: str | None = None) -> list[int]:
    """دِدوپ + پاک‌سازیِ یک فهرستِ شناسه (کالای دستی/دسته‌بندی/برند) —
    ترتیبِ ورودی حفظ می‌شود (ترتیبِ انتخابِ مرچنت، نه ترتیبِ دیتابیس)."""
    error_cls = error_cls or ProductSectionSettingsError
    if not isinstance(raw_list, list):
        raise error_cls(error_message or "فهرستِ شناسه‌ها باید یک آرایه باشد")
    cleaned: list[int] = []
    seen = set()
    for value in raw_list:
        try:
            int_value = int(value)
        except (TypeError, ValueError):
            raise error_cls(error_message or "شناسه نامعتبر است") from None
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

    # حالتِ کارتِ محصول — فقط برایِ Familyهایی معنا دارد که واقعاً بیش از
    # یک Renderer کارت دارند (تصمیمِ مالک، Q-09: ثابت per-family، با
    # استثنایِ صریحِ Heritage Premium که دو حالت دارد). این کلید عمداً
    # عمومی/بی‌نام‌ Familyی خاص است — یک مکانیزمِ توسعه‌پذیر برایِ *هر*
    # Familyی که در آینده حالتِ دوم اضافه کند، نه شرطِ سخت‌کدشده‌یِ
    # «اگر Family == heritage_premium». Familyهایی بدونِ حالتِ دوم این
    # کلید را نادیده می‌گیرند (نگاه کنید به ``FamilyDefinition.product_card_campaign_variant``).
    card_mode = raw.get("card_mode")
    if card_mode not in PRODUCT_SECTION_CARD_MODES:
        card_mode = "default"

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
        "card_mode": card_mode,
    }


def _product_section_defaults() -> dict:
    return {
        "data_source": "newest",
        "source_id": None,
        "product_ids": [],
        "item_limit": _PRODUCT_SECTION_DEFAULT_LIMIT,
        "display_mode": "carousel",
        "show_view_all": True,
        "card_mode": "default",
        "title": "",
        "subtitle": "",
    }


#: انواعی که «ستون» به‌عنوان مفهوم قراردادی/دیتایی معنا دارد — تعدادِ
#: ستون برایِ این‌ها اعتبارسنجی و ذخیره می‌شود (قراردادِ عمداً
#: آینده‌نگر و عمومی، طبقِ بخشِ ۵ مشخصاتِ فیکسِ فازِ D: «Keep the
#: responsive contract generic internally for future expansion»).
#: **این ثابت هرگز مستقیماً برایِ تصمیمِ نمایش/عدم‌نمایشِ کنترلِ UI
#: استفاده نشود** — سه نوعِ باقی‌مانده‌یِ ``category_grid``/
#: ``promo_cards``/``brand_carousel`` مقدار را ذخیره می‌کنند اما
#: چیدمانِ ثابتِ فعلی‌شان (tiles/auto-fill) اصلاً آن را در رندر
#: نمی‌خواند — نمایشِ کنترل به تاجر برایِ این سه نوع صرفاً گمراه‌کننده
#: است (تغییرِ عدد هیچ اثرِ بصری‌ای ندارد). برایِ آن تصمیم از
#: ``COLUMN_VISUAL_SECTION_KEYS`` پایین استفاده کنید.
COLUMN_AWARE_SECTION_KEYS = frozenset({
    "product_section", "category_grid", "multi_banner", "promo_cards", "brand_carousel",
})

#: زیرمجموعه‌یِ ``COLUMN_AWARE_SECTION_KEYS`` که تغییرِ تعدادِ ستون
#: واقعاً چیدمانِ رندرشده را عوض می‌کند (فیکسِ فازِ D، پس از گزارشِ
#: تستِ دستیِ کاربر روی Brand Carousel: تغییرِ ستونِ موبایل هیچ اثرِ
#: بصری‌ای نداشت). فقط همین مجموعه باید کنترلِ «تعدادِ ستون‌ها» را در
#: فرمِ تنظیماتِ ادیتور نشان دهد — نه ``COLUMN_AWARE_SECTION_KEYS``ی
#: بالا. ``product_section`` از قبل یک grid/carousel پارامتری دارد
#: (``.rsec-cols`` در ``product_card.css``)؛ ``multi_banner`` در Phase 3
#: (کتابخانه‌ی بلوک‌هایِ صفحه‌ی اصلی — بستنِ شکافِ «Two-Banner Row»/
#: «Multi-Banner Grid») به همین مجموعه اضافه شد و از همان کلاسِ
#: ``.grid.rsec-cols``یِ موجود استفاده می‌کند (کدِ CSSِ تازه‌ای نساخته
#: شد). وقتی چیدمانِ ``category_grid``/``promo_cards``/``brand_carousel``
#: هم در آینده بازطراحی شد، همان کلید را از ``COLUMN_AWARE_SECTION_KEYS``
#: به اینجا هم منتقل کنید.
COLUMN_VISUAL_SECTION_KEYS = frozenset({"product_section", "multi_banner"})

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


#: انواعی که یک بلوکِ «لینک/مقصد» استاندارد (چکپوینتِ استانداردسازیِ لینک)
#: در تنظیماتشان دارند — معادلِ JSON-شکلِ ``apps.content.models.DestinationMixin``
#: برایِ محتوایِ ذخیره‌شده در ``StorefrontSection.settings`` (نه یک ردیفِ
#: مدلِ جدا). عمداً مثلِ ``COLUMN_AWARE_SECTION_KEYS`` یک allowlist صریح
#: است، نه پیش‌فرضِ همه‌ی انواع — چون بعضی انواع (rich_text، trust_features)
#: اصلاً معنایِ «لینکِ سطحِ section» ندارند، و بعضیِ دیگر (hero_banner،
#: single_banner/multi_banner) لینکشان per-slide/per-banner است، نه
#: per-section (نگاه کنید به مدلِ ``HeroSlide``/``PromotionalBanner`` که
#: خودشان از قبل ``DestinationMixin`` واقعی دارند). برایِ ``product_section``
#: این بلوک معنایِ «override دستیِ لینکِ "مشاهده همه"» را دارد؛ برایِ
#: ``image_text`` معنایِ «لینکِ تصویر/دکمه» را دارد.
DESTINATION_AWARE_SECTION_KEYS = frozenset({"image_text", "product_section", "brand_carousel"})

_DEFAULT_DESTINATION_SETTINGS = {
    "destination_type": "none",
    "destination_id": None,
    "destination_external_url": "",
    "open_in_new_tab": False,
}


class DestinationSettingsError(ValueError):
    """شکلِ خامِ بلوکِ ``destination`` نامعتبر است — پیامِ فارسیِ
    قابل‌نمایشِ مستقیم به تاجر."""


def validate_destination_settings(raw) -> dict:
    """قراردادِ مشترکِ «لینک/مقصد» — معادلِ JSON بلوکِ ``DestinationMixin``
    برایِ تنظیماتِ یک section (نه یک ردیفِ مدلِ جدا). فقط شکل/enum را چک
    می‌کند — مالکیتِ Store برایِ ``destination_id`` (دسته/محصول/برند/کالکشن)
    عمداً اینجا چک نمی‌شود، دقیقاً همان تفکیکِ مسئولیتی که
    ``_validate_product_section_settings`` برایِ ``source_id`` دارد؛ چکِ
    واقعی در ``apps.content.services.resolve_destination_setting`` انجام
    می‌شود.

    غایب بودنِ کلیدِ ``destination`` (سکشن‌هایِ از‌قبل‌موجود که هرگز از این
    فرم عبور نکرده‌اند) دقیقاً هم‌ارزِ «بدون مقصد» است."""
    from apps.content.models import DestinationType, validate_external_url
    from django.core.exceptions import ValidationError as DjangoValidationError

    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        raise DestinationSettingsError("تنظیماتِ لینک باید یک شیء باشد")

    valid_types = {choice.value for choice in DestinationType}
    dtype = raw.get("destination_type") or "none"
    if dtype not in valid_types:
        raise DestinationSettingsError("نوع مقصدِ انتخاب‌شده نامعتبر است")

    cleaned = dict(_DEFAULT_DESTINATION_SETTINGS)
    cleaned["destination_type"] = dtype
    cleaned["open_in_new_tab"] = bool(raw.get("open_in_new_tab", False))

    if dtype in ("category", "product", "brand", "collection"):
        try:
            destination_id = int(raw.get("destination_id"))
        except (TypeError, ValueError):
            raise DestinationSettingsError("مقصدِ انتخاب‌شده نامعتبر است") from None
        if destination_id <= 0:
            raise DestinationSettingsError("مقصدِ انتخاب‌شده نامعتبر است")
        cleaned["destination_id"] = destination_id
    elif dtype == "external":
        external_url = str(raw.get("destination_external_url", "")).strip()
        try:
            validate_external_url(external_url)
        except DjangoValidationError as exc:
            raise DestinationSettingsError("; ".join(exc.messages)) from exc
        cleaned["destination_external_url"] = external_url

    return cleaned


def default_destination_settings() -> dict:
    return dict(_DEFAULT_DESTINATION_SETTINGS)


def _with_destination(section_key: str, validate_fn, default_fn):
    """هر جفتِ (validate_settings, default_settings) موجود را با پشتیبانیِ
    بلوکِ ``destination`` می‌پوشاند — فقط برایِ کلیدهایِ
    ``DESTINATION_AWARE_SECTION_KEYS``. دقیقاً همان الگویِ ``_with_responsive``
    بالا: منطقِ خودِ نوع کاملاً دست‌نخورده می‌ماند."""
    if section_key not in DESTINATION_AWARE_SECTION_KEYS:
        return validate_fn, default_fn

    def wrapped_validate(raw: dict) -> dict:
        if not isinstance(raw, dict):
            return validate_fn(raw)
        destination_raw = raw.get("destination")
        base_raw = {k: v for k, v in raw.items() if k != "destination"}
        cleaned = validate_fn(base_raw)
        cleaned["destination"] = validate_destination_settings(destination_raw)
        return cleaned

    def wrapped_default() -> dict:
        base = default_fn()
        return {**base, "destination": default_destination_settings()}

    return wrapped_validate, wrapped_default


#: انواعی که یک بلوکِ «حرکت» (Phase 3: کتابخانه‌ی بلوک‌هایِ صفحه‌ی
#: اصلی) دارند — جلوه‌ی ورود/hover که کاملاً config-محور است (CSS در
#: storefront_builder.css)، نه کدِ Renderer/family. عمداً یک allowlist
#: صریح است (مثلِ ``COLUMN_AWARE_SECTION_KEYS``/``DESTINATION_AWARE_SECTION_KEYS``
#: بالا)، نه پیش‌فرضِ همه‌ی انواع — بعضی انواع (rich_text/faq/testimonials/
#: quick_links/video_section/trust_features/...) معنایِ بصریِ روشنی برایِ
#: hover/ورودِ متحرک ندارند.
MOTION_AWARE_SECTION_KEYS = frozenset({
    "hero_banner", "image_slider", "single_banner", "multi_banner",
    "category_grid", "brand_carousel", "product_section", "collection_tiles",
    "image_text",
})

#: enum بستهٔ سبکِ حرکت — ``none`` پیش‌فرض (رفتارِ فعلی، بدونِ تغییر).
MOTION_CHOICES = ("none", "fade", "slide", "subtle_zoom", "hover_lift")


class MotionSettingsError(ValueError):
    """شکلِ خامِ بلوکِ ``motion`` نامعتبر است."""


def validate_motion_settings(raw) -> dict:
    """قراردادِ مشترکِ «حرکت» — سبکِ نامعتبر/غایب بی‌صدا به ``none``
    بازمی‌گردد (نه خطا)، دقیقاً همان تسامحی که ``validate_responsive_settings``
    برایِ کلیدهایِ ناشناخته/غایب دارد."""
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        raise MotionSettingsError("تنظیماتِ حرکت باید یک شیء باشد")
    style = raw.get("style")
    if style not in MOTION_CHOICES:
        style = "none"
    return {"style": style}


def default_motion_settings() -> dict:
    return {"style": "none"}


def _with_motion(section_key: str, validate_fn, default_fn):
    """هر جفتِ (validate_settings, default_settings) موجود را با پشتیبانیِ
    بلوکِ ``motion`` می‌پوشاند — فقط برایِ کلیدهایِ ``MOTION_AWARE_SECTION_KEYS``.
    دقیقاً همان الگویِ ``_with_responsive``/``_with_destination`` بالا."""
    if section_key not in MOTION_AWARE_SECTION_KEYS:
        return validate_fn, default_fn

    def wrapped_validate(raw: dict) -> dict:
        if not isinstance(raw, dict):
            return validate_fn(raw)
        motion_raw = raw.get("motion")
        base_raw = {k: v for k, v in raw.items() if k != "motion"}
        cleaned = validate_fn(base_raw)
        cleaned["motion"] = validate_motion_settings(motion_raw)
        return cleaned

    def wrapped_default() -> dict:
        base = default_fn()
        return {**base, "motion": default_motion_settings()}

    return wrapped_validate, wrapped_default


#: بازه‌یِ مجازِ فاصله‌یِ خودکارِ اسلایدر (میلی‌ثانیه) — enum بسته نیست
#: (چون یک بازه‌یِ عددیِ معقول است، نه چند گزینه‌یِ مجزا)، اما clamp
#: می‌شود تا هرگز مقدارِ نامعقول (خیلی سریع/خیلی کند) ذخیره نشود.
_SLIDER_MIN_INTERVAL_MS = 2000
_SLIDER_MAX_INTERVAL_MS = 10000
_SLIDER_DEFAULT_INTERVAL_MS = 4500


def _validate_slider_settings(raw: dict) -> dict:
    """قراردادِ تنظیماتِ سطحِ اسلایدر (نه تک‌تکِ اسلایدها — آن‌ها روی خودِ
    ``HeroSlide`` ذخیره می‌شوند) — برایِ ``hero_banner``/``image_slider``.
    اسلایدهایِ خودِ section از طریقِ ``HeroSlide.section`` (نه اینجا)
    مدیریت می‌شوند؛ این فقط رفتارِ نمایشِ اسلایدر را کنترل می‌کند."""
    if not isinstance(raw, dict):
        raise ValueError("تنظیمات باید یک شیء JSON باشد")

    autoplay = raw.get("autoplay", True)
    if not isinstance(autoplay, bool):
        autoplay = bool(autoplay)

    try:
        interval_ms = int(raw.get("interval_ms", _SLIDER_DEFAULT_INTERVAL_MS))
    except (TypeError, ValueError):
        interval_ms = _SLIDER_DEFAULT_INTERVAL_MS
    interval_ms = max(_SLIDER_MIN_INTERVAL_MS, min(_SLIDER_MAX_INTERVAL_MS, interval_ms))

    show_arrows = raw.get("show_arrows", True)
    if not isinstance(show_arrows, bool):
        show_arrows = bool(show_arrows)

    show_dots = raw.get("show_dots", True)
    if not isinstance(show_dots, bool):
        show_dots = bool(show_dots)

    loop = raw.get("loop", True)
    if not isinstance(loop, bool):
        loop = bool(loop)

    return {
        "autoplay": autoplay, "interval_ms": interval_ms,
        "show_arrows": show_arrows, "show_dots": show_dots, "loop": loop,
    }


def default_slider_settings() -> dict:
    return {
        "autoplay": True, "interval_ms": _SLIDER_DEFAULT_INTERVAL_MS,
        "show_arrows": True, "show_dots": True, "loop": True,
    }


class CategoryGridSettingsError(ValueError):
    """شکلِ خامِ تنظیماتِ «گرید دسته‌بندی» نامعتبر است (فقط شکل/enum —
    مالکیتِ Storeِ ``category_ids`` در خودِ ``render_service`` چک می‌شود،
    چون یک کوئریِ QuerySet ساده است، نه سرویسِ جداگانه)."""


_MAX_CATEGORY_GRID_IDS = 12
_MAX_SECTION_TITLE_LENGTH = 60
CATEGORY_GRID_DISPLAY_MODES = ("grid", "carousel")


def _validate_category_grid_settings(raw: dict) -> dict:
    """چکپوینتِ ۱۱: ``category_grid`` از یک بلوکِ سراسریِ ثابت (۳+۱ دسته‌ی
    اولِ فروشگاه) به یک section واقعاً per-instance ارتقا یافت —
    ``category_ids`` خالی یعنی «هنوز مرچنت انتخاب نکرده»، که در
    ``render_service`` دقیقاً همان رفتارِ قبل از این چکپوینت (auto-pick
    از دسته‌های فعالِ سطحِ اول) را بازتولید می‌کند — سازگاریِ کامل با
    گذشته."""
    if not isinstance(raw, dict):
        raise CategoryGridSettingsError("تنظیمات باید یک شیء JSON باشد")

    title = str(raw.get("title", "")).strip()[:_MAX_SECTION_TITLE_LENGTH]
    display_mode = raw.get("display_mode")
    if display_mode not in CATEGORY_GRID_DISPLAY_MODES:
        display_mode = "grid"
    category_ids = _clean_positive_int_list(
        raw.get("category_ids", []), max_len=_MAX_CATEGORY_GRID_IDS,
        error_cls=CategoryGridSettingsError, error_message="شناسه‌ی دسته‌بندی نامعتبر است",
    )
    return {"title": title, "display_mode": display_mode, "category_ids": category_ids}


def default_category_grid_settings() -> dict:
    return {"title": "", "display_mode": "grid", "category_ids": []}


class BrandCarouselSettingsError(ValueError):
    """شکلِ خامِ تنظیماتِ «کاروسل برندها» نامعتبر است."""


_MAX_BRAND_CAROUSEL_IDS = 24
BRAND_CAROUSEL_DISPLAY_MODES = ("grid", "carousel")


def _validate_brand_carousel_settings(raw: dict) -> dict:
    """چکپوینتِ ۱۱: همان ارتقایِ ``category_grid`` برایِ ``brand_carousel``
    — ``brand_ids`` خالی یعنی رفتارِ قبل از این چکپوینت (همه‌ی برندهایِ
    فعالِ فروشگاه) دست‌نخورده می‌ماند. ``destination`` (لینکِ اختیاریِ
    «مشاهده همه») از طریقِ ``DESTINATION_AWARE_SECTION_KEYS`` عمومی
    اضافه می‌شود، نه اینجا — دقیقاً همان زیرساختِ لینکِ استانداردِ کارِ
    ۱."""
    if not isinstance(raw, dict):
        raise BrandCarouselSettingsError("تنظیمات باید یک شیء JSON باشد")

    title = str(raw.get("title", "")).strip()[:_MAX_SECTION_TITLE_LENGTH]
    display_mode = raw.get("display_mode")
    if display_mode not in BRAND_CAROUSEL_DISPLAY_MODES:
        display_mode = "grid"
    show_view_all = raw.get("show_view_all", False)
    if not isinstance(show_view_all, bool):
        show_view_all = bool(show_view_all)
    brand_ids = _clean_positive_int_list(
        raw.get("brand_ids", []), max_len=_MAX_BRAND_CAROUSEL_IDS,
        error_cls=BrandCarouselSettingsError, error_message="شناسه‌ی برند نامعتبر است",
    )
    return {"title": title, "display_mode": display_mode, "show_view_all": show_view_all, "brand_ids": brand_ids}


def default_brand_carousel_settings() -> dict:
    return {"title": "", "display_mode": "grid", "show_view_all": False, "brand_ids": []}


class CollectionTilesSettingsError(ValueError):
    """شکلِ خامِ تنظیماتِ «کارت‌های کالکشن» نامعتبر است."""


_MAX_COLLECTION_TILES_IDS = 12


def _validate_collection_tiles_settings(raw: dict) -> dict:
    """چکپوینتِ ۱۲: بخشِ جدیدِ «کارت‌های کالکشن» — خودِ کالکشن‌ها را نشان
    می‌دهد (تصویر/نام/تعدادِ کالا/لینک به صفحه‌ی کالکشن)، نه کالاهایِ
    *داخلِ* یک کالکشن (که همان ``product_section`` با ``data_source=collection``
    است). ``collection_ids`` خالی = نمایشِ خودکارِ همه‌ی کالکشن‌های فعال."""
    if not isinstance(raw, dict):
        raise CollectionTilesSettingsError("تنظیمات باید یک شیء JSON باشد")
    title = str(raw.get("title", "")).strip()[:_MAX_SECTION_TITLE_LENGTH]
    collection_ids = _clean_positive_int_list(
        raw.get("collection_ids", []), max_len=_MAX_COLLECTION_TILES_IDS,
        error_cls=CollectionTilesSettingsError, error_message="شناسه‌ی کالکشن نامعتبر است",
    )
    return {"title": title, "collection_ids": collection_ids}


def default_collection_tiles_settings() -> dict:
    return {"title": "", "collection_ids": []}


class QuickLinksSettingsError(ValueError):
    """شکلِ خامِ تنظیماتِ «دسترسی سریع» نامعتبر است."""


def _validate_quick_links_settings(raw: dict) -> dict:
    """چکپوینتِ ۱۲: «دسترسی سریع» — به‌جایِ اختراعِ یک مدلِ لینکِ جدید،
    مستقیماً یک ``Menu`` موجود (همان زیرساختِ Menu/MenuItem/Destination
    که برایِ ناوبریِ هدر/فوتر استفاده می‌شود) را به‌شکلِ ردیفی از
    کارت‌های بصری نمایش می‌دهد — مالکیتِ Storeِ ``menu_id`` در
    ``render_service`` چک می‌شود."""
    if not isinstance(raw, dict):
        raise QuickLinksSettingsError("تنظیمات باید یک شیء JSON باشد")
    title = str(raw.get("title", "")).strip()[:_MAX_SECTION_TITLE_LENGTH]
    menu_id = raw.get("menu_id")
    if menu_id is not None:
        try:
            menu_id = int(menu_id)
        except (TypeError, ValueError):
            raise QuickLinksSettingsError("منویِ انتخاب‌شده نامعتبر است") from None
        if menu_id <= 0:
            menu_id = None
    return {"title": title, "menu_id": menu_id}


def default_quick_links_settings() -> dict:
    return {"title": "", "menu_id": None}


class FaqSettingsError(ValueError):
    """شکلِ خامِ تنظیماتِ «سوالات متداول» نامعتبر است."""


_MAX_FAQ_ITEMS = 20
_MAX_FAQ_QUESTION_LENGTH = 200
_MAX_FAQ_ANSWER_LENGTH = 1000


def _validate_faq_settings(raw: dict) -> dict:
    """چکپوینتِ ۱۲: هر آیتم فقط دو فیلدِ متنیِ ساده (سوال/پاسخ) — نه HTML
    غنی (سوءاستفاده/XSS از یک بخشِ به‌ظاهر ساده بی‌معناست؛ اگر مرچنت به
    فرمت‌بندیِ غنی نیاز داشت، ``rich_text`` همین حالا برایش هست)."""
    if not isinstance(raw, dict):
        raise FaqSettingsError("تنظیمات باید یک شیء JSON باشد")
    title = str(raw.get("title", "")).strip()[:_MAX_SECTION_TITLE_LENGTH] or "سوالات متداول"

    raw_items = raw.get("items", [])
    if not isinstance(raw_items, list):
        raise FaqSettingsError("فهرستِ سوالات باید یک آرایه باشد")
    items = []
    for raw_item in raw_items[:_MAX_FAQ_ITEMS]:
        if not isinstance(raw_item, dict):
            continue
        question = str(raw_item.get("question", "")).strip()[:_MAX_FAQ_QUESTION_LENGTH]
        answer = str(raw_item.get("answer", "")).strip()[:_MAX_FAQ_ANSWER_LENGTH]
        if not question or not answer:
            continue
        items.append({"question": question, "answer": answer})
    return {"title": title, "items": items}


def default_faq_settings() -> dict:
    return {"title": "سوالات متداول", "items": []}


class TestimonialsSettingsError(ValueError):
    """شکلِ خامِ تنظیماتِ «نظرات مشتریان» نامعتبر است."""


_MAX_TESTIMONIAL_ITEMS = 20
_MAX_TESTIMONIAL_NAME_LENGTH = 80
_MAX_TESTIMONIAL_ROLE_LENGTH = 80
_MAX_TESTIMONIAL_QUOTE_LENGTH = 400


def _validate_testimonials_settings(raw: dict) -> dict:
    if not isinstance(raw, dict):
        raise TestimonialsSettingsError("تنظیمات باید یک شیء JSON باشد")
    title = str(raw.get("title", "")).strip()[:_MAX_SECTION_TITLE_LENGTH] or "نظرات مشتریان"

    raw_items = raw.get("items", [])
    if not isinstance(raw_items, list):
        raise TestimonialsSettingsError("فهرستِ نظرات باید یک آرایه باشد")
    items = []
    for raw_item in raw_items[:_MAX_TESTIMONIAL_ITEMS]:
        if not isinstance(raw_item, dict):
            continue
        name = str(raw_item.get("name", "")).strip()[:_MAX_TESTIMONIAL_NAME_LENGTH]
        quote = str(raw_item.get("quote", "")).strip()[:_MAX_TESTIMONIAL_QUOTE_LENGTH]
        role = str(raw_item.get("role", "")).strip()[:_MAX_TESTIMONIAL_ROLE_LENGTH]
        if not name or not quote:
            continue
        items.append({"name": name, "quote": quote, "role": role})
    return {"title": title, "items": items}


def default_testimonials_settings() -> dict:
    return {"title": "نظرات مشتریان", "items": []}


class VideoSectionSettingsError(ValueError):
    """شکلِ خامِ تنظیماتِ «بخشِ ویدیو» نامعتبر است."""


_MAX_VIDEO_CAPTION_LENGTH = 200


def _validate_video_section_settings(raw: dict) -> dict:
    """چکپوینتِ ۱۲: دقیقاً همان تشخیصِ ارائه‌دهنده/اعتبارسنجیِ URL که
    برایِ ویدیویِ کالا استفاده می‌شود (``product_video_service``) — بدونِ
    بازنویسیِ دوباره‌ی regex/قوانین. آدرسِ نامعتبر رد می‌شود، نه ذخیره‌ی
    بی‌صدا و شکستِ بعدیِ رندر."""
    if not isinstance(raw, dict):
        raise VideoSectionSettingsError("تنظیمات باید یک شیء JSON باشد")
    title = str(raw.get("title", "")).strip()[:_MAX_SECTION_TITLE_LENGTH]
    caption = str(raw.get("caption", "")).strip()[:_MAX_VIDEO_CAPTION_LENGTH]

    video_url = str(raw.get("video_url", "")).strip()
    if video_url:
        from apps.catalog.services.product_video_service import ProductVideoError, detect_provider_and_id

        try:
            detect_provider_and_id(video_url)
        except ProductVideoError as exc:
            raise VideoSectionSettingsError(str(exc)) from exc

    return {"title": title, "video_url": video_url, "caption": caption}


def default_video_section_settings() -> dict:
    return {"title": "", "video_url": "", "caption": ""}


class NewsletterSettingsError(ValueError):
    """شکلِ خامِ تنظیماتِ «خبرنامه» نامعتبر است."""


_MAX_NEWSLETTER_TITLE_LENGTH = 60
_MAX_NEWSLETTER_SUBTITLE_LENGTH = 150
_MAX_NEWSLETTER_BUTTON_LABEL_LENGTH = 30


def _validate_newsletter_settings(raw: dict) -> dict:
    """Phase 3 (کتابخانه‌ی بلوک‌هایِ صفحه‌ی اصلی) — فقط متنِ نمایشی؛ خودِ
    منطقِ ثبتِ ایمیل (اعتبارسنجی/دی‌دوپ/تنظیمِ ذخیره‌سازی) در
    ``apps.content.services.subscribe_to_newsletter`` است، نه اینجا —
    دقیقاً همان تفکیکِ مسئولیتی که ``_validate_product_section_settings``
    برایِ ``source_id`` دارد."""
    if not isinstance(raw, dict):
        raise NewsletterSettingsError("تنظیمات باید یک شیء JSON باشد")
    title = str(raw.get("title", "")).strip()[:_MAX_NEWSLETTER_TITLE_LENGTH]
    subtitle = str(raw.get("subtitle", "")).strip()[:_MAX_NEWSLETTER_SUBTITLE_LENGTH]
    button_label = str(raw.get("button_label", "")).strip()[:_MAX_NEWSLETTER_BUTTON_LABEL_LENGTH] or "عضویت"
    return {"title": title, "subtitle": subtitle, "button_label": button_label}


def default_newsletter_settings() -> dict:
    return {"title": "عضویت در خبرنامه", "subtitle": "", "button_label": "عضویت"}


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

#: ترتیبِ نمایشِ گروه‌هایِ کتابخانه‌ی «افزودن بخش جدید» (چکپوینتِ ۱۰) —
#: پنج گروهِ کسب‌وکاریِ ثابت، نه اصطلاحِ فنی؛ ``category_fa`` هر
#: ``SectionDefinition`` باید دقیقاً یکی از این‌ها باشد (تست می‌شود).
SECTION_LIBRARY_CATEGORIES = ["محصولات", "تصاویر و تبلیغات", "کشف و خرید", "محتوا", "ساختار"]

# تعاریف کامل settings-schema هر کلید در چکپوینت‌های ۱۱ تا ۱۴ (بنر/دسته/
# محصول/متن غنی) اضافه می‌شود؛ اینجا فقط استخوان‌بندی allowlist با
# اعتبارسنج‌های placeholder ایمن (رد هر چیز غیر-dict) ثبت می‌شود تا خودِ
# Registry از روز اول قابل‌اعتماد و قابل‌تست باشد.
_BASE_SECTION_REGISTRY: dict[str, SectionDefinition] = {
    "announcement_bar": SectionDefinition(
        key="announcement_bar", label_fa="نوار اعلان", icon="megaphone",
        template_name="storefront_builder/sections/announcement_bar.html",
        validate_settings=_passthrough_dict, default_settings=_empty_defaults,
        max_instances=1, duplicable=False, removable=True, category_fa="ساختار",
        # پنهان از کتابخانه: تنظیماتِ «نوار اعلان» هدر (متن/فعال‌بودن،
        # همیشه بالای صفحه) همین قابلیت را به‌شکلِ واقعاً قابل‌تنظیم
        # پوشش می‌دهد (نگاه کنید به ``storefront_header_editor``) — این
        # نوعِ section هرگز settings واقعی نداشته (فقط متنِ سخت‌کدشده)،
        # پس امکانِ ساختِ نمونه‌ی جدید از آن گمراه‌کننده است. نمونه‌های
        # قدیمیِ موجود کاملاً دست‌نخورده و کارکردی می‌مانند.
        hidden_from_library=True,
    ),
    "hero_banner": SectionDefinition(
        key="hero_banner", label_fa="اسلایدر اصلی", icon="image",
        template_name="storefront_builder/sections/hero_banner.html",
        validate_settings=_validate_slider_settings, default_settings=default_slider_settings,
        duplicable=True, removable=True, has_settings_form=True, category_fa="تصاویر و تبلیغات",
    ),
    "image_slider": SectionDefinition(
        key="image_slider", label_fa="اسلایدر تصویر", icon="images",
        template_name="storefront_builder/sections/image_slider.html",
        validate_settings=_validate_slider_settings, default_settings=default_slider_settings,
        duplicable=True, removable=True, has_settings_form=True, category_fa="تصاویر و تبلیغات",
    ),
    "single_banner": SectionDefinition(
        key="single_banner", label_fa="بنر تکی", icon="image",
        template_name="storefront_builder/sections/single_banner.html",
        validate_settings=_passthrough_dict, default_settings=_empty_defaults,
        duplicable=True, removable=True, category_fa="تصاویر و تبلیغات",
    ),
    "multi_banner": SectionDefinition(
        key="multi_banner", label_fa="ردیف چند بنری", icon="layout-grid",
        template_name="storefront_builder/sections/multi_banner.html",
        validate_settings=_passthrough_dict, default_settings=_empty_defaults,
        duplicable=True, removable=True, category_fa="تصاویر و تبلیغات",
    ),
    "category_grid": SectionDefinition(
        key="category_grid", label_fa="گرید دسته‌بندی", icon="grid",
        template_name="storefront_builder/sections/category_grid.html",
        validate_settings=_validate_category_grid_settings, default_settings=default_category_grid_settings,
        duplicable=True, removable=True, has_settings_form=True, category_fa="کشف و خرید",
    ),
    "featured_products": SectionDefinition(
        key="featured_products", label_fa="محصولات ویژه", icon="star",
        template_name="storefront_builder/sections/featured_products.html",
        validate_settings=_passthrough_dict, default_settings=_empty_defaults,
        duplicable=True, removable=True, category_fa="محصولات",
    ),
    "newest_products": SectionDefinition(
        key="newest_products", label_fa="جدیدترین محصولات", icon="sparkles",
        template_name="storefront_builder/sections/newest_products.html",
        validate_settings=_passthrough_dict, default_settings=_empty_defaults,
        duplicable=True, removable=True, category_fa="محصولات",
    ),
    "best_sellers": SectionDefinition(
        key="best_sellers", label_fa="پرفروش‌ترین‌ها", icon="trending-up",
        template_name="storefront_builder/sections/best_sellers.html",
        validate_settings=_passthrough_dict, default_settings=_empty_defaults,
        duplicable=True, removable=True, category_fa="محصولات",
    ),
    "discounted_products": SectionDefinition(
        key="discounted_products", label_fa="محصولات تخفیف‌دار", icon="percent",
        template_name="storefront_builder/sections/discounted_products.html",
        validate_settings=_passthrough_dict, default_settings=_empty_defaults,
        duplicable=True, removable=True, category_fa="محصولات",
    ),
    "amazing_offers": SectionDefinition(
        key="amazing_offers", label_fa="پیشنهادهای شگفت‌انگیز", icon="zap",
        template_name="storefront_builder/sections/amazing_offers.html",
        validate_settings=_passthrough_dict, default_settings=_empty_defaults,
        duplicable=True, removable=True, category_fa="محصولات",
    ),
    "brand_carousel": SectionDefinition(
        key="brand_carousel", label_fa="کاروسل برندها", icon="award",
        template_name="storefront_builder/sections/brand_carousel.html",
        validate_settings=_validate_brand_carousel_settings, default_settings=default_brand_carousel_settings,
        duplicable=True, removable=True, has_settings_form=True, category_fa="کشف و خرید",
    ),
    "promo_cards": SectionDefinition(
        key="promo_cards", label_fa="کارت‌های تبلیغاتی", icon="layout",
        template_name="storefront_builder/sections/promo_cards.html",
        validate_settings=_passthrough_dict, default_settings=_empty_defaults,
        duplicable=True, removable=True, category_fa="تصاویر و تبلیغات",
    ),
    "rich_text": SectionDefinition(
        key="rich_text", label_fa="متن غنی", icon="text",
        template_name="storefront_builder/sections/rich_text.html",
        validate_settings=_validate_rich_text_settings, default_settings=lambda: {"body_html": ""},
        duplicable=True, removable=True, has_settings_form=True, category_fa="محتوا",
    ),
    "image_text": SectionDefinition(
        key="image_text", label_fa="متن و تصویر", icon="image-plus",
        template_name="storefront_builder/sections/image_text.html",
        validate_settings=_validate_image_text_settings,
        default_settings=lambda: {"title": "", "body_html": "", "image_url": "", "image_position": "right"},
        duplicable=True, removable=True, has_settings_form=True, category_fa="محتوا",
    ),
    "product_section": SectionDefinition(
        key="product_section", label_fa="بخش محصولات", icon="shopping-bag",
        template_name="storefront_builder/sections/product_section.html",
        validate_settings=_validate_product_section_settings, default_settings=_product_section_defaults,
        duplicable=True, removable=True, has_settings_form=True, category_fa="محصولات",
    ),
    "trust_features": SectionDefinition(
        key="trust_features", label_fa="ردیف اعتماد و ویژگی‌ها", icon="shield-check",
        template_name="storefront_builder/sections/trust_features.html",
        validate_settings=_passthrough_dict, default_settings=_empty_defaults,
        max_instances=1, duplicable=False, removable=True, category_fa="ساختار",
    ),
    # -------------------------------------------------- چکپوینتِ ۱۲: بخش‌های جدید
    "collection_tiles": SectionDefinition(
        key="collection_tiles", label_fa="کارت‌های کالکشن", icon="layers",
        template_name="storefront_builder/sections/collection_tiles.html",
        validate_settings=_validate_collection_tiles_settings, default_settings=default_collection_tiles_settings,
        duplicable=True, removable=True, has_settings_form=True, category_fa="کشف و خرید",
    ),
    "quick_links": SectionDefinition(
        key="quick_links", label_fa="دسترسی سریع", icon="compass",
        template_name="storefront_builder/sections/quick_links.html",
        validate_settings=_validate_quick_links_settings, default_settings=default_quick_links_settings,
        duplicable=True, removable=True, has_settings_form=True, category_fa="کشف و خرید",
    ),
    "faq": SectionDefinition(
        key="faq", label_fa="سوالات متداول", icon="help-circle",
        template_name="storefront_builder/sections/faq.html",
        validate_settings=_validate_faq_settings, default_settings=default_faq_settings,
        duplicable=True, removable=True, has_settings_form=True, category_fa="محتوا",
    ),
    "testimonials": SectionDefinition(
        key="testimonials", label_fa="نظرات مشتریان", icon="message-circle",
        template_name="storefront_builder/sections/testimonials.html",
        validate_settings=_validate_testimonials_settings, default_settings=default_testimonials_settings,
        duplicable=True, removable=True, has_settings_form=True, category_fa="محتوا",
    ),
    "video_section": SectionDefinition(
        key="video_section", label_fa="بخش ویدیو", icon="play-circle",
        template_name="storefront_builder/sections/video_section.html",
        validate_settings=_validate_video_section_settings, default_settings=default_video_section_settings,
        duplicable=True, removable=True, has_settings_form=True, category_fa="محتوا",
    ),
    # -------------------------------------------------- Story Rail (بخشِ مشترکِ اختیاری)
    "story_rail": SectionDefinition(
        key="story_rail", label_fa="ریلِ استوری", icon="circle",
        template_name="storefront_builder/sections/story_rail.html",
        validate_settings=_passthrough_dict, default_settings=_empty_defaults,
        max_instances=1, duplicable=False, removable=True, category_fa="کشف و خرید",
    ),
    # -------------------------------------------------- Phase 3: کتابخانه‌ی بلوک‌های صفحه اصلی
    "newsletter": SectionDefinition(
        key="newsletter", label_fa="خبرنامه", icon="mail",
        template_name="storefront_builder/sections/newsletter.html",
        validate_settings=_validate_newsletter_settings, default_settings=default_newsletter_settings,
        # یک بلوکِ ثبتِ ایمیلِ سراسری کافی‌ست — مثلِ trust_features/
        # story_rail، تکرارِ آن (دو فرمِ مستقل روی یک صفحه) گیج‌کننده است.
        max_instances=1, duplicable=False, removable=True, has_settings_form=True, category_fa="محتوا",
    ),
    # -------------------------------------------------- Phase 5: بخش‌های context-aware صفحه محصول
    # هر چهار نوعِ زیر فقط رویِ product_detail قابل‌افزودن‌اند (page_types)
    # و بدونِ تنظیماتِ واقعی هستند (passthrough) — داده‌شان همیشه از
    # ``page_context``ی که ویوِ مسیر پاس می‌دهد resolve می‌شود، هرگز از
    # یک ID ذخیره‌شده در settings؛ نگاه کنید به
    # ``render_service._CONTEXT_AWARE_BUILDERS``.
    "product_main": SectionDefinition(
        key="product_main", label_fa="گالری و خرید محصول", icon="shopping-bag",
        template_name="storefront_builder/sections/product_main.html",
        validate_settings=_passthrough_dict, default_settings=_empty_defaults,
        # گالری/قیمت/انتخابِ تنوع/افزودن‌به‌سبد یک کامپوننتِ Alpine واحد
        # است (``x-data="variantSelector(...)"``) — تجزیه‌ی آن به
        # section‌های کوچک‌تر اسکوپِ آن کامپوننت را می‌شکست؛ حذفِ کاملِ آن
        # هم یعنی صفحه‌ی محصول هیچ راهی برایِ خرید ندارد، پس removable=False
        # (دقیقاً همان استدلالِ ``show_cart`` در هدر).
        max_instances=1, duplicable=False, removable=False, category_fa="محصولات",
        page_types=frozenset({PAGE_TYPE_PRODUCT_DETAIL}),
    ),
    "product_description": SectionDefinition(
        key="product_description", label_fa="توضیحات، مشخصات و نظرات", icon="text",
        template_name="storefront_builder/sections/product_description.html",
        validate_settings=_passthrough_dict, default_settings=_empty_defaults,
        # سه‌تب (توضیحات/مشخصات/نظرات) یک کامپوننتِ Alpine مشترک
        # (``x-data="{ tab: 'desc' }"``) هستند — طبقِ الزامِ صریحِ کار
        # («prefer sensible compositional primitives... may remain one
        # structured block»)، یک بلوکِ واحد می‌مانند، نه سه section جدا.
        max_instances=1, duplicable=False, removable=True, category_fa="محصولات",
        page_types=frozenset({PAGE_TYPE_PRODUCT_DETAIL}),
    ),
    "product_video": SectionDefinition(
        key="product_video", label_fa="ویدئوهای محصول", icon="play-circle",
        template_name="storefront_builder/sections/product_video.html",
        validate_settings=_passthrough_dict, default_settings=_empty_defaults,
        max_instances=1, duplicable=False, removable=True, category_fa="محصولات",
        page_types=frozenset({PAGE_TYPE_PRODUCT_DETAIL}),
    ),
    "related_products": SectionDefinition(
        key="related_products", label_fa="محصولات مرتبط", icon="grid",
        template_name="storefront_builder/sections/related_products.html",
        validate_settings=_passthrough_dict, default_settings=_empty_defaults,
        max_instances=1, duplicable=False, removable=True, category_fa="محصولات",
        page_types=frozenset({PAGE_TYPE_PRODUCT_DETAIL}),
    ),
    # -------------------------------------------------- Phase 5: بخشِ context-aware صفحه لیست/جستجو
    "product_listing": SectionDefinition(
        key="product_listing", label_fa="فیلتر و گرید محصولات", icon="shopping-bag",
        template_name="storefront_builder/sections/product_listing.html",
        validate_settings=_passthrough_dict, default_settings=_empty_defaults,
        # همان دلیلِ product_main: بدونِ این بلوک صفحه‌یِ لیست/جستجو هیچ
        # راهی برایِ دیدنِ کالاها ندارد.
        max_instances=1, duplicable=False, removable=False, category_fa="محصولات",
        page_types=frozenset({PAGE_TYPE_LISTING, PAGE_TYPE_SEARCH}),
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
        validate_fn, default_fn = _with_destination(key, definition.validate_settings, definition.default_settings)
        validate_fn, default_fn = _with_responsive(key, validate_fn, default_fn)
        validate_fn, default_fn = _with_motion(key, validate_fn, default_fn)
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


def list_library_groups(page_type: str | None = None) -> list[tuple[str, list[SectionDefinition]]]:
    """کتابخانه‌ی «افزودن بخش جدید» (چکپوینتِ ۱۰)، گروه‌بندی‌شده در پنج
    دسته‌ی کسب‌وکاریِ ثابت (``SECTION_LIBRARY_CATEGORIES``) — نوع‌هایِ
    ``hidden_from_library`` هرگز اینجا ظاهر نمی‌شوند (نمونه‌های موجودشان
    هم‌چنان از ``list_definitions()`` کامل resolve می‌شوند). گروه‌هایِ
    خالی حذف می‌شوند تا هرگز یک آکاردئونِ بی‌محتوا نشان داده نشود.

    Phase 5: اگر ``page_type`` داده شود، فقط انواعی که ``page_types``شان
    شاملِ آن صفحه است نمایش داده می‌شوند (مثلاً ``product_main`` هرگز در
    کتابخانه‌ی صفحه‌یِ Cart دیده نمی‌شود) — این فقط لایه‌ی UI است؛ رد
    واقعیِ ترکیبِ نامعتبر همیشه سمتِ سرور در ``is_section_allowed_on_page``
    انجام می‌شود، نه اینجا."""
    groups: list[tuple[str, list[SectionDefinition]]] = []
    for category in SECTION_LIBRARY_CATEGORIES:
        members = [
            d for d in SECTION_REGISTRY.values()
            if d.category_fa == category and not d.hidden_from_library
            and (page_type is None or page_type in d.page_types)
        ]
        if members:
            groups.append((category, members))
    return groups


def is_valid_section_key(section_key: str) -> bool:
    return section_key in SECTION_REGISTRY


def is_section_allowed_on_page(section_key: str, page_type: str) -> bool:
    """تکِ نقطه‌ی ورودیِ اجباریِ سمتِ سرور برایِ اعتبارسنجیِ ترکیبِ
    section/page — Phase 5. کلیدِ ناشناخته همیشه ``False`` برمی‌گرداند
    (fail-closed)، نه پرتاب کردنِ خطا؛ فراخوان (``storefront_section_add``)
    خودش پیش از این تابع کلیدِ نامعتبر را جدا رد می‌کند."""
    definition = SECTION_REGISTRY.get(section_key)
    if definition is None:
        return False
    return page_type in definition.page_types
