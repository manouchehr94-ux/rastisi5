from dataclasses import dataclass


@dataclass(frozen=True)
class ThemePreset:
    key: str
    label: str
    primary: str
    secondary: str
    accent: str
    background: str


THEME_PRESETS: list[ThemePreset] = [
    ThemePreset("digital-purple", "بنفش دیجیتال", "#6D28D9", "#7C3AED", "#FF4D77", "#F7F5FC"),
    ThemePreset("rose-pink", "رز صورتی", "#DB2777", "#EC4899", "#F97316", "#FDF2F8"),
    ThemePreset("emerald-green", "سبز زمردی", "#047857", "#10B981", "#F59E0B", "#F0FDF4"),
    ThemePreset("honey-amber", "عسلی کهربایی", "#B45309", "#D97706", "#7C3AED", "#FFFBEB"),
    ThemePreset("turquoise", "فیروزه‌ای", "#0E7490", "#06B6D4", "#F97316", "#ECFEFF"),
    ThemePreset("crimson-red", "زرشکی قرمز", "#991B1B", "#DC2626", "#F59E0B", "#FEF2F2"),
]

THEME_PRESETS_BY_KEY: dict[str, ThemePreset] = {preset.key: preset for preset in THEME_PRESETS}


def matching_preset_key(*, primary: str, secondary: str, accent: str, background: str) -> str:
    """اگر مقادیر فعلی دقیقاً با یکی از پیش‌فرض‌ها یکسان باشد، کلید آن را برمی‌گرداند؛ در غیر این صورت خالی."""
    current = (primary.upper(), secondary.upper(), accent.upper(), background.upper())
    for preset in THEME_PRESETS:
        if (preset.primary.upper(), preset.secondary.upper(), preset.accent.upper(), preset.background.upper()) == current:
            return preset.key
    return ""
