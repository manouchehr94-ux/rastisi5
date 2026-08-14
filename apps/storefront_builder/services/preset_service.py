"""Preset Application Service — Phase 6: اعمالِ یک ``LayoutPresetDefinition``
(``layout_preset_registry.py``) روی یک Draft.

قوانینِ معماریِ الزامی (طبقِ Phase 6 Audit):

- همیشه یک Draftِ صریح می‌گیرد (هرگز خودش «Draftِ جاری» را resolve
  نمی‌کند) — دقیقاً همان الگویِ ``bootstrap_service.apply_family_default_sections``.
  ``published_version`` هرگز از این ماژول قابلِ‌دسترس نیست.
- تراکنشی است: تمامِ اعتبارسنجی پیش از هر نوشتنی انجام می‌شود؛ اگر هرچیزی
  نامعتبر باشد، Draft کاملاً دست‌نخورده می‌ماند (نه نیمه‌اعمال‌شده).
- فقط ``StorefrontSection``هایِ صفحاتی که خودِ Preset صراحتاً پوشش داده
  حذف/بازسازی می‌شوند — صفحه‌ای که Preset آن را ذکر نکرده دست‌نخورده
  می‌ماند (طبقِ الزامِ صریحِ کار: «A preset may omit a page deliberately»).
- رنگ هرگز توسطِ این ماژول تغییر نمی‌کند مگر مرچنت هنوز هیچ Paletteای
  انتخاب نکرده باشد (فقط آنگاه پیشنهادِ Preset اعمال می‌شود) — Palette
  همیشه مستقل/آزاد می‌ماند (تصمیمِ مالک).
- هیچ محتوایِ کسب‌وکاریِ مرچنت (رسانه، محصول/دسته/کالکشنِ انتخابی، متنِ
  اعلانِ هدر) توسطِ این ماژول نوشته/پاک نمی‌شود — فقط section composition
  و تنظیماتِ ساختاری/بصری (طبقِ تفکیکِ صریحِ کار: STRUCTURAL/VISUAL در
  برابرِ MERCHANT CONTENT)."""

from __future__ import annotations

from django.db import transaction

from .. import layout_preset_registry, section_registry
from ..layout_preset_registry import LayoutPresetDefinition
from ..models import StorefrontLayoutVersion, StorefrontSection
from . import layout_service


class InvalidPresetError(Exception):
    """یک Preset (تعریف یا اعمال) نامعتبر است — Draft نباید تغییر کند."""


class UnknownPresetError(InvalidPresetError):
    """کلیدِ Preset درخواست‌شده در ``LAYOUT_PRESET_REGISTRY`` وجود ندارد."""


class LockedSectionsPresentError(InvalidPresetError):
    """Phase 1 correction (spec §37 — Lock): یک/چند section از صفحاتی که
    این Preset صریحاً می‌خواهد جایگزین کند قفل هستند. اعمالِ Preset
    یعنی حذفِ کاملِ sectionهایِ آن صفحه و ساختِ فهرستِ تازه — این دقیقاً
    همان «حذفِ یک section قفل‌شده» است که ``storefront_section_remove``
    از مسیرِ تک‌section از قبل رد می‌کند؛ یک «مسیرِ جایگزین» (Preset) نباید
    بتواند همان محافظت را دور بزند. ``InvalidPresetError`` را ارث‌بری
    می‌کند تا کدِ ویوِ موجود (``except InvalidPresetError``) بدونِ تغییر
    این خطا را هم درست نشان دهد."""


def _validate_appearance_overlay(base_config: dict, overlay: dict) -> dict:
    """اعتبارسنجیِ زیرمجموعه‌ی ساختاریِ ``appearance`` یک Preset — رویِ
    یک پیکربندیِ پایه (پیش‌فرضِ خنثی یا پیکربندیِ واقعیِ یک Draft) قرار
    می‌گیرد و از همان اعتبارسنجِ رسمیِ ادیتور
    (``layout_service.validate_appearance_config``) عبور می‌کند — پس هر
    قاعده‌ای که آن ادیتور اعمال می‌کند (enum بسته، بازه‌ی عدد، ...) اینجا
    هم رعایت می‌شود، بدونِ تکرارِ منطق."""
    merged = {**base_config, **overlay}
    return layout_service.validate_appearance_config(merged)


def _validate_header_overlay(base_config: dict, overlay: dict | None) -> dict | None:
    if overlay is None:
        return None
    merged = {**base_config, **overlay}
    return layout_service.validate_header_config(merged)


def _validate_footer_overlay(base_config: dict, overlay: dict | None) -> dict | None:
    if overlay is None:
        return None
    merged = {**base_config, **overlay}
    return layout_service.validate_footer_config(merged)


def validate_layout_preset(preset: LayoutPresetDefinition) -> None:
    """اعتبارسنجیِ کاملِ یک تعریفِ Preset، مستقل از هر Draftِ واقعی —
    همان چیزی که تستِ Presetهایِ درون‌ساخت باید پیش از هر اجرا تضمین
    کند (طبقِ الزامِ صریحِ کار: «Invalid built-in Presets should fail
    tests/startup validation rather than fail at runtime for a
    merchant»). بخشِ section/page از قبل در زمانِ import توسطِ
    ``layout_preset_registry._validate_page_composition_shape`` چک شده؛
    اینجا فقط appearance/header/footer (که به ``layout_service`` نیاز
    دارند) روی یک پایه‌ی خنثی (پیش‌فرض‌هایِ پلتفرم) چک می‌شود."""
    from ..models import APPEARANCE_CONFIG_DEFAULTS, FOOTER_CONFIG_DEFAULTS, HEADER_CONFIG_DEFAULTS

    try:
        _validate_appearance_overlay(dict(APPEARANCE_CONFIG_DEFAULTS), dict(preset.appearance))
        _validate_header_overlay(dict(HEADER_CONFIG_DEFAULTS), preset.header)
        _validate_footer_overlay(dict(FOOTER_CONFIG_DEFAULTS), preset.footer)
    except (
        layout_service.AppearanceConfigValidationError,
        layout_service.HeaderConfigValidationError,
        layout_service.FooterConfigValidationError,
    ) as exc:
        raise InvalidPresetError(f"Preset «{preset.key}» نامعتبر است: {exc}") from exc

    if preset.default_palette_slug is not None:
        from .. import appearance_registry
        if appearance_registry.get_palette(preset.default_palette_slug) is None:
            raise InvalidPresetError(
                f"Preset «{preset.key}»: پالتِ پیشنهادیِ «{preset.default_palette_slug}» در دسترس نیست"
            )


def _build_sections_for_page(page, entries) -> list[StorefrontSection]:
    rows = []
    for order, entry in enumerate(entries):
        definition = section_registry.get_definition(entry.section_key)
        if entry.settings is None:
            settings = definition.default_settings()
        else:
            settings = definition.validate_settings(entry.settings)
        rows.append(StorefrontSection(
            page=page, section_key=entry.section_key, order=order, settings=settings,
            row_key=entry.row_key, row_span=entry.row_span,
        ))
    return rows


@transaction.atomic
def apply_preset(draft: StorefrontLayoutVersion, preset: LayoutPresetDefinition) -> None:
    """Preset را روی ``draft`` اعمال می‌کند — Draft-only (فراخوان مسئولِ
    عبورِ یک نسخه‌یِ واقعاً Draft است، دقیقاً همان قراردادِ
    ``apply_family_default_sections``؛ این تابع خودش هرگز
    ``layout.published_version`` را resolve/لمس نمی‌کند).

    ترتیبِ عملیات عمداً «همه‌چیز را اول اعتبارسنجی کن، بعد بنویس» است —
    اگر هرکدام از appearance/header/footer/هر صفحه نامعتبر باشد، هیچ
    نوشتنی (نه روی Section، نه روی خودِ نسخه) اتفاق نمی‌افتد. علاوه‌براین
    خودِ تابع در یک تراکنشِ دیتابیسی (``@transaction.atomic``) پیچیده شده
    تا حتی یک خطایِ غیرمنتظره‌یِ سطحِ دیتابیس هم Draft را نیمه‌اعمال‌شده
    رها نکند."""
    # --- ۱) اعتبارسنجی/آماده‌سازیِ appearance/header/footer (بدونِ نوشتن) ---
    current_appearance = draft.effective_appearance_config()
    overlay = dict(preset.appearance)
    # Palette فقط اگر مرچنت هنوز هیچ Paletteای انتخاب نکرده — یک پیشنهاد
    # است، نه بازنویسیِ انتخابِ موجود (تصمیمِ مالک: Palette همیشه آزاد/جدا).
    if preset.default_palette_slug is not None and current_appearance.get("palette_slug") is None:
        overlay["palette_slug"] = preset.default_palette_slug
    overlay["layout_preset_key"] = preset.key
    try:
        cleaned_appearance = _validate_appearance_overlay(current_appearance, overlay)
    except layout_service.AppearanceConfigValidationError as exc:
        raise InvalidPresetError(f"Preset «{preset.key}» نامعتبر است: {exc}") from exc

    try:
        cleaned_header = _validate_header_overlay(draft.effective_header_config(), preset.header)
    except layout_service.HeaderConfigValidationError as exc:
        raise InvalidPresetError(f"Preset «{preset.key}» نامعتبر است: {exc}") from exc

    try:
        cleaned_footer = _validate_footer_overlay(draft.effective_footer_config(), preset.footer)
    except layout_service.FooterConfigValidationError as exc:
        raise InvalidPresetError(f"Preset «{preset.key}» نامعتبر است: {exc}") from exc

    # --- ۲) آماده‌سازیِ ردیف‌هایِ هر صفحه (بدونِ نوشتن — فقط ساختِ آبجکت) ---
    pages_to_replace = {}
    for page_type, entries in preset.pages.items():
        page = draft.get_page(page_type)
        # Phase 1 correction (spec §37 — Lock): این صفحه به‌طورِ کامل
        # جایگزین می‌شود (زیر را نگاه کنید) — اگر یکی از sectionهایِ فعلی‌اش
        # قفل باشد، اعمالِ Preset باید کاملاً رد شود، نه اینکه بی‌صدا آن
        # section را هم مثلِ بقیه حذف کند.
        if page.sections.filter(is_locked=True).exists():
            raise LockedSectionsPresentError(
                f"Preset «{preset.key}» قابلِ اعمال نیست — صفحه‌ی "
                f"«{page.get_page_type_display()}» بخشِ قفل‌شده دارد؛ ابتدا قفل آن را باز کنید"
            )
        pages_to_replace[page] = _build_sections_for_page(page, entries)

    # --- ۳) نوشتن — فقط پس از موفقیتِ کاملِ بخشِ اعتبارسنجی ---
    draft.appearance_config = cleaned_appearance
    update_fields = ["appearance_config"]
    if cleaned_header is not None:
        draft.header_config = cleaned_header
        update_fields.append("header_config")
    if cleaned_footer is not None:
        draft.footer_config = cleaned_footer
        update_fields.append("footer_config")
    draft.save(update_fields=update_fields)

    for page, rows in pages_to_replace.items():
        page.sections.all().delete()
        StorefrontSection.objects.bulk_create(rows)


def apply_preset_by_key(draft: StorefrontLayoutVersion, key: str) -> LayoutPresetDefinition:
    """میان‌بُرِ راحت برایِ لایه‌ی ویو — کلیدِ ناشناخته را قبل از هر تغییری
    fail-closed رد می‌کند."""
    preset = layout_preset_registry.get_layout_preset(key)
    if preset is None:
        raise UnknownPresetError(f"پیش‌تنظیمِ «{key}» یافت نشد")
    apply_preset(draft, preset)
    return preset
