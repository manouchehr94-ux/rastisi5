import re

HEX_COLOR_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")


def is_valid_hex(value: str) -> bool:
    return bool(value) and bool(HEX_COLOR_RE.match(value))


def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    hex_color = hex_color.lstrip("#")
    return int(hex_color[0:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16)


def _rgb_to_hex(r: float, g: float, b: float) -> str:
    def clamp(c):
        return max(0, min(255, round(c)))

    return f"#{clamp(r):02X}{clamp(g):02X}{clamp(b):02X}"


def relative_luminance(hex_color: str) -> float:
    """محاسبه‌ی روشنایی نسبی رنگ (WCAG 2.1)."""
    r, g, b = (c / 255 for c in _hex_to_rgb(hex_color))

    def linearize(c):
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    return 0.2126 * linearize(r) + 0.7152 * linearize(g) + 0.0722 * linearize(b)


def contrast_ratio(hex_a: str, hex_b: str) -> float:
    """نسبت کنتراست WCAG بین دو رنگ (از ۱ تا ۲۱)."""
    lum_a, lum_b = relative_luminance(hex_a), relative_luminance(hex_b)
    lighter, darker = max(lum_a, lum_b), min(lum_a, lum_b)
    return (lighter + 0.05) / (darker + 0.05)


def foreground_for(bg_hex: str) -> str:
    """رنگ پیش‌زمینه‌ی امن (سفید یا سیاه) بر اساس روشنایی پس‌زمینه."""
    try:
        return "#FFFFFF" if relative_luminance(bg_hex) < 0.179 else "#000000"
    except (ValueError, IndexError):
        return "#FFFFFF"


def mix_hex(hex_a: str, hex_b: str, ratio: float) -> str:
    """ترکیب خطی دو رنگ در فضای RGB؛ ratio سهم hex_a است (بین ۰ و ۱)."""
    ratio = max(0.0, min(1.0, ratio))
    ra, ga, ba = _hex_to_rgb(hex_a)
    rb, gb, bb = _hex_to_rgb(hex_b)
    return _rgb_to_hex(
        ra * ratio + rb * (1 - ratio),
        ga * ratio + gb * (1 - ratio),
        ba * ratio + bb * (1 - ratio),
    )


def darken_hex(hex_color: str, amount: float = 0.12) -> str:
    """تیره‌کردن رنگ با ترکیب با سیاه — برای حالت hover دکمه‌های اصلی."""
    return mix_hex("#000000", hex_color, amount)


def safe_hex(value: str, default: str) -> str:
    """بازگشت رنگ هگز معتبر یا مقدار پیش‌فرض — هرگز مقدار خام نامعتبر به CSS نمی‌رسد."""
    return value if is_valid_hex(value) else default
