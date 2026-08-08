"""Site Appearance Registry — الگویِ دقیقاً مشابهِ ``section_registry.py``:
یک دیکشنریِ ثابتِ پایتونی، پلتفرم‌محور، نسخه‌بندی‌نشده در دیتابیس. انتخابِ
مرچنت (کدام Template/Palette فعال است) در ``StorefrontLayoutVersion.appearance_config``
ذخیره می‌شود (Store-owned، Draft/Publish-aware)؛ خودِ تعریفِ هر Template/Palette
اینجا Store-agnostic و مشترکِ کلِ پلتفرم است — دقیقاً همان تفکیکِ مسئولیتی
که ``SECTION_REGISTRY`` بینِ «کدام نوع section وجود دارد» (اینجا) و
«کدام نمونه در این صفحه است» (دیتابیس) دارد.

چرا یک دیکشنریِ کد به‌جایِ یک مدلِ دیتابیسی: Templateها/Paletteها محتوایِ
طراحی‌شده و مرورشده‌ی خودِ تیمِ پلتفرم‌اند (نه چیزی که مرچنت بسازد) — دقیقاً
مثلِ SECTION_REGISTRY، نسخه‌بندی/بازبینیِ آن‌ها با Code Review و git history
اتفاق می‌افتد، نه با یک migration/admin UI جداگانه. اضافه‌کردنِ Templateی
جدید یعنی یک ورودیِ جدید اینجا (تک‌تکِ فروشگاه‌ها بدونِ migration بلافاصله
می‌توانند آن را انتخاب کنند)."""

from __future__ import annotations

import dataclasses

DENSITY_CHOICES = ("compact", "normal", "relaxed")
MOTION_CHOICES = ("none", "subtle", "dynamic")
BUTTON_STYLE_CHOICES = ("filled", "soft", "outline")

#: فونت‌هایِ مجاز — مجموعه‌ی کوچک و کیوریت‌شده، هرکدام واقعاً برایِ
#: فارسی/RTL مناسب (نه هر فونتِ دلخواه؛ طبقِ الزامِ صریحِ کار: «مرچنت فونت
#: را با نام انتخاب کند، نه CSS خام آپلود کند»).
FONT_CHOICES = ("Vazirmatn", "Tahoma", "Arial", "Georgia")


@dataclasses.dataclass(frozen=True)
class PaletteDefinition:
    slug: str
    name_fa: str
    group_fa: str
    colors: dict[str, str]  # هر ۸ کلیدِ APPEARANCE_COLOR_KEYS


@dataclasses.dataclass(frozen=True)
class TemplateDefinition:
    slug: str
    name_fa: str
    group_fa: str
    description_fa: str
    #: مقادیرِ پیشنهادیِ Templateهای appearance — مرچنت می‌تواند این‌ها را
    #: در appearance_config.color_overrides/font/... دستی override کند؛
    #: این‌ها فقط پیش‌فرضِ اعمال‌شده هنگامِ انتخابِ Template‌اند، نه یک
    #: محدودیتِ اجباری.
    font: str
    radius: int
    button_radius: int
    button_style: str
    density: str
    motion: str
    #: نمونه‌رنگ‌هایِ گالری (برایِ mini-preview) — لزوماً همان پالتِ فعلیِ
    #: مرچنت نیست؛ فقط برایِ نمایشِ کارتِ گالری.
    swatch: list[str]


# ---------------------------------------------------------------- پالت‌ها

PALETTE_REGISTRY: dict[str, PaletteDefinition] = {}
TEMPLATE_REGISTRY: dict[str, TemplateDefinition] = {}


def register_palette(definition: PaletteDefinition) -> None:
    PALETTE_REGISTRY[definition.slug] = definition


def register_template(definition: TemplateDefinition) -> None:
    TEMPLATE_REGISTRY[definition.slug] = definition


def get_palette(slug: str) -> PaletteDefinition | None:
    return PALETTE_REGISTRY.get(slug)


def get_template(slug: str) -> TemplateDefinition | None:
    return TEMPLATE_REGISTRY.get(slug)


def list_palettes() -> list[PaletteDefinition]:
    return list(PALETTE_REGISTRY.values())


def list_templates() -> list[TemplateDefinition]:
    return list(TEMPLATE_REGISTRY.values())


#: پایه‌یِ رنگ وقتی ``palette_slug`` انتخاب نشده (None) — دقیقاً همان
#: مقادیرِ پیش‌فرضِ فعلیِ ``ShopSettings`` (بخشِ «هویت بصری»،
#: ``apps/core/models.py``) به‌علاوه‌یِ ``border``ی معادلِ فرمولِ derived
#: فعلی (``mix_hex(text, surface, 0.12)`` با این دو رنگ) — یعنی
#: فروشگاهی که هنوز هیچ Palette انتخاب نکرده، دقیقاً همان چیزی را
#: می‌بیند که امروز می‌بیند.
DEFAULT_COLORS = {
    "primary": "#6D28D9", "secondary": "#7C3AED", "accent": "#FF4D77",
    "background": "#F7F5FC", "surface": "#FFFFFF", "text": "#241C3A",
    "muted": "#8B86A3", "border": "#ECE8F6",
}


def resolve_colors(appearance_config: dict) -> dict:
    """رنگ‌هایِ نهاییِ اثرگذار: پالتِ پایه (اگر انتخاب شده) + override هایِ
    دستیِ مرچنت رویِ آن — دقیقاً معماریِ «base palette + merchant overrides»
    که گزارشِ ممیزی توصیه کرده بود (نه flatten مخربِ پرست در override).
    اگر مرچنت پالتی انتخاب نکرده (``palette_slug=None``)، پایه همان
    ``DEFAULT_COLORS`` است — یعنی ``color_overrides`` عملاً تمامِ رنگ‌هایِ
    فعلیِ آن فروشگاه را حمل می‌کند (دقیقاً همان چیزی که ``bootstrap_service``
    برایِ مهاجرتِ فروشگاه‌هایِ موجود انجام می‌دهد)."""
    palette_slug = appearance_config.get("palette_slug")
    palette = get_palette(palette_slug) if palette_slug else None
    base = dict(palette.colors) if palette is not None else dict(DEFAULT_COLORS)
    overrides = appearance_config.get("color_overrides") or {}
    return {**base, **overrides}


# قالبِ پایه — همیشه باید وجود داشته باشد چون
# ``APPEARANCE_CONFIG_DEFAULTS["template_slug"]`` (models.py) به آن اشاره
# می‌کند؛ سایرِ قالب‌ها در چکپوینتِ Template Architecture اضافه می‌شوند.
register_template(TemplateDefinition(
    slug="modern", name_fa="فروشگاه مدرن", group_fa="فروشگاهی",
    description_fa="هدر تمیز، کارت‌های شناور و چیدمان متعادل — قالب پیش‌فرض.",
    font="Vazirmatn", radius=18, button_radius=12, button_style="filled",
    density="normal", motion="subtle", swatch=["#6D28D9", "#FF4D77", "#FFFFFF"],
))
