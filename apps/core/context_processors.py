from apps.content.models import SocialLink
from apps.core.color_utils import darken_hex, foreground_for, mix_hex, safe_hex
from apps.core.models import ShopSettings


def shop_settings(request):
    """هویت و تنظیمات فروشگاهِ Store جاری — از همان رکورد ShopSettings که پنل مدیریت › تنظیمات ویرایش می‌کند.

    Store از ``request.store`` (که middleware مرحله‌ی تحلیل میزبان تنظیم
    کرده) خوانده می‌شود. اگر هنوز میزبان درخواست به هیچ Store‌ای resolve
    نشده باشد (``request.store is None``)، ``ShopSettings.load()`` بدون
    آرگومان به حالت سازگاریِ موقت (تک‌فروشگاهی Akhlaghi) برمی‌گردد و در غیر
    آن صورت fail-closed می‌شود — هرگز تنظیمات یک Store دیگر را برنمی‌گرداند.
    """
    shop = ShopSettings.load(store=getattr(request, "store", None))

    primary = safe_hex(shop.primary_color, "#6D28D9")
    accent = safe_hex(shop.accent_color, "#FF4D77")
    secondary = safe_hex(shop.secondary_color, "#7C3AED")
    background = safe_hex(shop.background_color, "#F7F5FC")
    surface = safe_hex(shop.surface_color, "#FFFFFF")
    text = safe_hex(shop.text_color, "#241C3A")
    muted = safe_hex(shop.muted_text_color, "#8B86A3")

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
        "SHOP_SECONDARY_COLOR": secondary,
        "SHOP_BACKGROUND_COLOR": background,
        "SHOP_SURFACE_COLOR": surface,
        "SHOP_TEXT_COLOR": text,
        "SHOP_MUTED_TEXT_COLOR": muted,
        "SHOP_PRIMARY_FG": foreground_for(primary),
        "SHOP_ACCENT_FG": foreground_for(accent),
        "SHOP_SECONDARY_FG": foreground_for(secondary),
        "SHOP_PRIMARY_HOVER": darken_hex(primary),
        "SHOP_BORDER_COLOR": mix_hex(text, surface, 0.12),
        # شبکه‌های اجتماعی
        "SOCIAL_LINKS_FOOTER": SocialLink.objects.filter(is_active=True, show_in_footer=True).order_by("display_order", "id"),
        "SOCIAL_LINKS_HEADER": SocialLink.objects.filter(is_active=True, show_in_header=True).order_by("display_order", "id"),
    }
