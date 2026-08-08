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


# ---------------------------------------------------------------- ۲۰ پالتِ آماده

#: هر ۸ کلید حاضر است — دقیقاً همان audit شده‌یِ ``APPEARANCE_COLOR_KEYS``
#: (``models.py``)؛ گروه‌بندی (``group_fa``) فقط برایِ فیلترِ گالری است،
#: هیچ اثرِ رفتاری ندارد.
_PALETTE_DATA = [
    ("violet-pop", "بنفش مدرن", "مدرن", "#6C3DF0", "#F34F74", "#FFB020", "#FFFFFF", "#F7F7FB", "#1F2430", "#747B8A", "#E5E7EF"),
    ("digired", "قرمز فروشگاهی", "پرفروش", "#E82C4C", "#FF6B6B", "#FFB300", "#FFFFFF", "#F7F7F8", "#202124", "#71717A", "#E5E7EB"),
    ("ocean", "آبی حرفه‌ای", "سرد", "#1769E0", "#00A8E8", "#FFB703", "#F8FBFF", "#FFFFFF", "#14213D", "#667085", "#DDE7F2"),
    ("forest", "سبز طبیعی", "طبیعی", "#167A5B", "#62A87C", "#D99B2B", "#FAFCF8", "#FFFFFF", "#17352B", "#6C7B73", "#DDE8E1"),
    ("luxury-black", "مشکی لوکس", "لوکس", "#171717", "#C9A227", "#C9A227", "#F8F6F1", "#FFFFFF", "#111111", "#777064", "#DED8CC"),
    ("rose", "رز بوتیک", "گرم", "#B84A6B", "#E9A6B8", "#C58B48", "#FFF8FA", "#FFFFFF", "#3A2630", "#8E747E", "#F0DCE3"),
    ("terracotta", "تراکوتا", "گرم", "#B55239", "#E69A75", "#D3A13B", "#FFF9F5", "#FFFFFF", "#3B2923", "#8A6F64", "#EEDFD8"),
    ("amber", "کهربایی", "گرم", "#C47A00", "#F1B83B", "#DC4C3F", "#FFFBF2", "#FFFFFF", "#33260D", "#7F7257", "#EEE3C7"),
    ("mint", "نعنایی", "طبیعی", "#128C7E", "#5ED6C5", "#FF8A5B", "#F3FCFA", "#FFFFFF", "#143B37", "#66817D", "#D7EBE7"),
    ("olive", "زیتونی", "طبیعی", "#657A33", "#A8B96B", "#D09A32", "#FBFCF5", "#FFFFFF", "#2D3420", "#78806A", "#E4E8D7"),
    ("navy", "سرمه‌ای", "سرد", "#1D3557", "#457B9D", "#E9A23B", "#F7FAFC", "#FFFFFF", "#142033", "#677486", "#DCE3EA"),
    ("cyan", "فیروزه‌ای", "سرد", "#007C91", "#36C2D0", "#FF8D4D", "#F3FBFC", "#FFFFFF", "#15363C", "#668087", "#D6E9EC"),
    ("lavender", "یاسی آرام", "نرم", "#7565D6", "#C4B5FD", "#EE8A9A", "#FAF9FF", "#FFFFFF", "#292540", "#7E7896", "#E7E3F3"),
    ("peach", "هلویی نرم", "نرم", "#D86F52", "#F7B89C", "#B89442", "#FFF9F6", "#FFFFFF", "#402A24", "#8B756E", "#F0DED6"),
    ("sage", "سیج مینیمال", "نرم", "#6E8572", "#AFC0B1", "#C38B5F", "#F8FAF7", "#FFFFFF", "#28332A", "#778079", "#E0E6E0"),
    ("mono", "سیاه و سفید", "مینیمال", "#111111", "#525252", "#111111", "#FFFFFF", "#FAFAFA", "#111111", "#737373", "#E5E5E5"),
    ("slate", "خاکستری حرفه‌ای", "مینیمال", "#334155", "#64748B", "#2563EB", "#F8FAFC", "#FFFFFF", "#0F172A", "#64748B", "#E2E8F0"),
    ("royal", "آبی سلطنتی", "لوکس", "#273C75", "#7186C7", "#D4AF37", "#F8F9FD", "#FFFFFF", "#17213B", "#6E7690", "#DEE2EE"),
    ("plum", "آلویی", "لوکس", "#6D315F", "#A76591", "#C29B55", "#FFF8FD", "#FFFFFF", "#35222F", "#806A79", "#ECDCE7"),
    ("sunset", "غروب", "شاد", "#F05A47", "#8B5CF6", "#F4B740", "#FFF9F4", "#FFFFFF", "#312529", "#817175", "#F0DFDA"),
]

for _slug, _name, _group, _primary, _secondary, _accent, _background, _surface, _text, _muted, _border in _PALETTE_DATA:
    register_palette(PaletteDefinition(
        slug=_slug, name_fa=_name, group_fa=_group,
        colors={
            "primary": _primary, "secondary": _secondary, "accent": _accent,
            "background": _background, "surface": _surface, "text": _text,
            "muted": _muted, "border": _border,
        },
    ))
del _slug, _name, _group, _primary, _secondary, _accent, _background, _surface, _text, _muted, _border


# قالبِ پایه — همیشه باید وجود داشته باشد چون
# ``APPEARANCE_CONFIG_DEFAULTS["template_slug"]`` (models.py) به آن اشاره
# می‌کند؛ سایرِ قالب‌ها در چکپوینتِ Template Architecture اضافه می‌شوند.
register_template(TemplateDefinition(
    slug="modern", name_fa="فروشگاه مدرن", group_fa="فروشگاهی",
    description_fa="هدر تمیز، کارت‌های شناور و چیدمان متعادل — قالب پیش‌فرض.",
    font="Vazirmatn", radius=18, button_radius=12, button_style="filled",
    density="normal", motion="subtle", swatch=["#6D28D9", "#FF4D77", "#FFFFFF"],
))
