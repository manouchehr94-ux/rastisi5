"""Preset Registry — یک بسته‌ی آماده‌ی تنظیمات *درون* یک Family (تصمیمِ
مالک، Q-02): توکن‌هایِ ساختاریِ Typography/Density/Radius/Motion + یک
Paletteِ پیشنهادی + (اختیاری) چیدمانِ اولیه‌یِ Section. Preset هرگز یک
Family یا قالبِ ساختاریِ جدا نیست — DOM/Renderer را تغییر نمی‌دهد (آن‌ها
فقط توسطِ ``family_registry.FamilyDefinition`` انتخاب می‌شوند)؛ Preset
هرگز داده‌یِ فروشگاه را Hard-code نمی‌کند و پس از انتخاب کاملاً
قابل‌ویرایش است (Merchant Overrides، دقیقاً همان مدلِ Base+Override
موجودِ ``appearance_registry.resolve_colors``).

چرا مستقل از ``appearance_registry.TEMPLATE_REGISTRY``: یک Preset به یک
Family خاص محدود است (``family_slug``)؛ ``TemplateDefinition`` مستقل از
هر Familyی و برایِ DOMِ مشترکِ ۱۰ قالبِ قدیمی است (تصمیمِ مالک: هیچ‌کدام
حذف/تغییر نمی‌شود). مقادیرِ enum از همان ثابت‌هایِ موجودِ
``appearance_registry`` می‌آیند تا دوباره تعریف نشوند."""

from __future__ import annotations

import dataclasses


@dataclasses.dataclass(frozen=True)
class PresetDefinition:
    slug: str
    family_slug: str
    name_fa: str
    description_fa: str
    font: str
    radius: int
    button_radius: int
    button_style: str
    density: str
    motion: str
    type_scale: str
    card_shadow: str
    card_hover: str
    hero_style: str
    #: Paletteِ پیشنهادیِ این Preset (``appearance_registry.PALETTE_REGISTRY``)
    #: — مرچنت همچنان می‌تواند بعداً آزادانه از کلِ ۲۰ Palette موجود
    #: انتخابِ دیگری کند؛ Palette همیشه Global می‌ماند (تصمیمِ مالک).
    default_palette_slug: str
    #: --- فیلدهایِ اختیاری (دارایِ مقدارِ پیش‌فرض) — باید بعد از تمامِ
    #: فیلدهایِ الزامی بیایند (قاعده‌ی dataclass پایتون). ---
    #: تنظیماتِ مستقلِ تصویرِ کارتِ محصول — هر Preset می‌تواند پیش‌فرضِ
    #: خودش را داشته باشد؛ مرچنت بعداً می‌تواند آزادانه override کند.
    card_image_crossfade: bool = False
    card_image_zoom: bool = True
    #: چیدمانِ اولیه‌یِ پیشنهادیِ Sectionهایِ Homepage (فهرستِ section_key
    #: هایِ SECTION_REGISTRY موجود) — در این چک‌پوینت ثبت شده اما هنوز
    #: هیچ سرویسی آن را به‌طور خودکار اعمال نمی‌کند (فروشگاه‌هایِ موجود از
    #: Bootstrap Sections فعلی‌شان استفاده می‌کنند؛ اعمالِ خودکارِ این
    #: چیدمان برایِ Storeهایِ کاملاً تازه، به‌عمد به فازِ بعد موکول شد تا
    #: دامنه‌یِ همین چک‌پوینت کنترل‌شده بماند).
    default_section_layout: tuple = ()


PRESET_REGISTRY: dict[str, PresetDefinition] = {}


def register_preset(definition: PresetDefinition) -> None:
    PRESET_REGISTRY[definition.slug] = definition


def get_preset(slug: str | None) -> PresetDefinition | None:
    if not slug:
        return None
    return PRESET_REGISTRY.get(slug)


def list_presets_for_family(family_slug: str) -> list[PresetDefinition]:
    return [p for p in PRESET_REGISTRY.values() if p.family_slug == family_slug]


# --------------------------------------------------------------- پریست‌ها

register_preset(PresetDefinition(
    slug="modern_fashion_default",
    family_slug="modern_fashion",
    name_fa="مد امروز — پیش‌فرض",
    description_fa="فضای سفید، رادیوس بزرگ، حرکت ملایم؛ دقیقاً مطابق مرجع تحلیلی خانواده.",
    font="Vazirmatn", radius=16, button_radius=16, button_style="soft",
    density="normal", motion="subtle", type_scale="normal",
    card_shadow="soft", card_hover="zoom", hero_style="wide",
    default_palette_slug="amber",
    card_image_crossfade=True, card_image_zoom=False,
))

register_preset(PresetDefinition(
    slug="artisan_editorial_default",
    family_slug="artisan_editorial",
    name_fa="روایت هنر — پیش‌فرض",
    description_fa="فضای گرم، رادیوس کوچک، بدون حرکت اضافه؛ دقیقاً مطابق مرجع تحلیلی خانواده.",
    font="Vazirmatn", radius=12, button_radius=10, button_style="outline",
    density="relaxed", motion="none", type_scale="normal",
    card_shadow="none", card_hover="none", hero_style="tall",
    default_palette_slug="olive",
))

register_preset(PresetDefinition(
    slug="nordic_living_default",
    family_slug="nordic_living",
    name_fa="خانه آرام — پیش‌فرض",
    description_fa="رادیوس بسیار کوچک (Squared)، بدون سایه؛ دقیقاً مطابق مرجع تحلیلی خانواده.",
    font="Vazirmatn", radius=4, button_radius=4, button_style="filled",
    density="normal", motion="subtle", type_scale="normal",
    card_shadow="none", card_hover="none", hero_style="wide",
    default_palette_slug="navy",
    card_image_crossfade=True, card_image_zoom=False,
))

register_preset(PresetDefinition(
    slug="heritage_premium_default",
    family_slug="heritage_premium",
    name_fa="پرمیوم اصیل — پیش‌فرض",
    description_fa="فضای سفید فراوان، رادیوس کوچک، ریتم آرام؛ دقیقاً مطابق مرجع تحلیلی خانواده.",
    font="Vazirmatn", radius=8, button_radius=8, button_style="outline",
    density="relaxed", motion="subtle", type_scale="normal",
    card_shadow="none", card_hover="lift", hero_style="wide",
    default_palette_slug="forest",
))

register_preset(PresetDefinition(
    slug="vibrant_catalog_default",
    family_slug="vibrant_catalog",
    name_fa="کاتالوگ رنگی — پیش‌فرض",
    description_fa="رادیوس کوچک، تراکمِ زیاد، حرکتِ کوتاه؛ دقیقاً مطابق مرجع تحلیلی خانواده.",
    font="Vazirmatn", radius=10, button_radius=10, button_style="filled",
    density="compact", motion="subtle", type_scale="compact",
    card_shadow="soft", card_hover="lift", hero_style="wide",
    default_palette_slug="digired",
))


# ============================================================ شش Preset جدید (Phase 5)

register_preset(PresetDefinition(
    slug="atlas_catalog_default",
    family_slug="atlas_catalog",
    name_fa="اطلس — پیش‌فرض",
    description_fa="تراکم زیاد، رادیوس ۱۰، رنگ‌های پرانرژی.",
    font="Vazirmatn", radius=10, button_radius=10, button_style="filled",
    density="compact", motion="subtle", type_scale="compact",
    card_shadow="soft", card_hover="lift", hero_style="wide",
    default_palette_slug="coral",
))

register_preset(PresetDefinition(
    slug="ava_fashion_default",
    family_slug="ava_fashion",
    name_fa="آوا — پیش‌فرض",
    description_fa="فضای باز، رادیوس ۱۴، Story-first.",
    font="Vazirmatn", radius=14, button_radius=14, button_style="soft",
    density="normal", motion="subtle", type_scale="normal",
    card_shadow="soft", card_hover="zoom", hero_style="wide",
    default_palette_slug="amber",
    card_image_crossfade=True, card_image_zoom=False,
))

register_preset(PresetDefinition(
    slug="toranj_gifting_default",
    family_slug="toranj_gifting",
    name_fa="ترنج — پیش‌فرض",
    description_fa="فضای گرم، Pill buttons، رادیوس ۹۹.",
    font="Vazirmatn", radius=16, button_radius=99, button_style="filled",
    density="normal", motion="subtle", type_scale="normal",
    card_shadow="none", card_hover="lift", hero_style="wide",
    default_palette_slug="brown",
))

register_preset(PresetDefinition(
    slug="sarv_stock_default",
    family_slug="sarv_stock",
    name_fa="سرو — پیش‌فرض",
    description_fa="سبز تیره، رادیوس ۲۰، دکمه پر.",
    font="Vazirmatn", radius=20, button_radius=15, button_style="filled",
    density="compact", motion="subtle", type_scale="normal",
    card_shadow="soft", card_hover="lift", hero_style="wide",
    default_palette_slug="forest",
    card_image_crossfade=True, card_image_zoom=False,
))

register_preset(PresetDefinition(
    slug="sepidar_handmade_default",
    family_slug="sepidar_handmade",
    name_fa="سپیدار — پیش‌فرض",
    description_fa="کرم و نسکافه‌ای، رادیوس ۸، Editorial.",
    font="Vazirmatn", radius=8, button_radius=8, button_style="outline",
    density="relaxed", motion="none", type_scale="normal",
    card_shadow="none", card_hover="none", hero_style="tall",
    default_palette_slug="olive",
))

register_preset(PresetDefinition(
    slug="zarrin_jewelry_default",
    family_slug="zarrin_jewelry",
    name_fa="زرین — پیش‌فرض",
    description_fa="مینیمال، بژ و طلایی، رادیوس ۵.",
    font="Vazirmatn", radius=5, button_radius=5, button_style="outline",
    density="normal", motion="subtle", type_scale="normal",
    card_shadow="none", card_hover="none", hero_style="wide",
    default_palette_slug="gold",
    card_image_crossfade=True, card_image_zoom=False,
))
