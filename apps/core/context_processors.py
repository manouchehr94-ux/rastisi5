from apps.core.models import ShopSettings


def _relative_luminance(hex_color: str) -> float:
    """محاسبه‌ی روشنایی نسبی رنگ برای تعیین متن خوانا (WCAG 2.1)."""
    hex_color = hex_color.lstrip("#")
    r, g, b = int(hex_color[0:2], 16) / 255, int(hex_color[2:4], 16) / 255, int(hex_color[4:6], 16) / 255

    def linearize(c):
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    return 0.2126 * linearize(r) + 0.7152 * linearize(g) + 0.0722 * linearize(b)


def _foreground_color(bg_hex: str) -> str:
    """بازگشت رنگ پیش‌زمینه امن (سفید یا سیاه) بر اساس کنتراست."""
    try:
        lum = _relative_luminance(bg_hex)
        return "#FFFFFF" if lum < 0.179 else "#000000"
    except (ValueError, IndexError):
        return "#FFFFFF"


def _safe_hex(value: str, default: str) -> str:
    """بازگشت رنگ هگز معتبر یا مقدار پیش‌فرض — هرگز مقدار خام نامعتبر."""
    import re
    if value and re.match(r"^#[0-9A-Fa-f]{6}$", value):
        return value
    return default


def shop_settings(request):
    """هویت و تنظیمات عمومی پلتفرم — از همان رکورد ShopSettings که پنل مدیریت › تنظیمات ویرایش می‌کند."""
    shop = ShopSettings.load()

    primary = _safe_hex(shop.primary_color, "#6D28D9")
    accent = _safe_hex(shop.accent_color, "#FF4D77")

    return {
        "SHOP_NAME": shop.name,
        "SHOP_TAGLINE": shop.tagline,
        "SHOP_CONTACT_PHONE": shop.contact_phone,
        "SHOP_CONTACT_EMAIL": shop.contact_email,
        "SHOP_CONTACT_ADDRESS": shop.contact_address,
        "SHOP_DESCRIPTION": shop.description,
        "SHOP_FREE_SHIPPING_THRESHOLD": shop.free_shipping_threshold,
        "SHOP_TAX_PERCENT": shop.tax_percent,
        # هویت بصری
        "SHOP_LOGO": shop.logo if shop.logo else None,
        "SHOP_FAVICON": shop.favicon if shop.favicon else None,
        "SHOP_PRIMARY_COLOR": primary,
        "SHOP_ACCENT_COLOR": accent,
        "SHOP_PRIMARY_FG": _foreground_color(primary),
        "SHOP_ACCENT_FG": _foreground_color(accent),
    }
