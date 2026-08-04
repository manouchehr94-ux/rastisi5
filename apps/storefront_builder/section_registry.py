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
    #: آیا این نوع بخش تنظیمات قابل‌ویرایش (فرم) دارد؟ اکثر انواع فعلی
    #: بدون تنظیم، همان داده‌های فعال فروشگاه را (دقیقاً مثل صفحه اصلی قدیمی)
    #: نمایش می‌دهند — «ویرایش تنظیمات» فقط برای انواعی که واقعاً محتوای
    #: قابل‌تنظیم دارند (rich_text، image_text) نمایش داده می‌شود.
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
SECTION_REGISTRY: dict[str, SectionDefinition] = {
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
    "trust_features": SectionDefinition(
        key="trust_features", label_fa="ردیف اعتماد و ویژگی‌ها", icon="shield-check",
        template_name="storefront_builder/sections/trust_features.html",
        validate_settings=_passthrough_dict, default_settings=_empty_defaults,
        max_instances=1, duplicable=False, removable=True,
    ),
}


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
