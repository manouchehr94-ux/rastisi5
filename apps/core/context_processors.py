from apps.core.models import ShopSettings


def shop_settings(request):
    """هویت و تنظیمات عمومی پلتفرم — از همان رکورد ShopSettings که پنل مدیریت › تنظیمات ویرایش می‌کند."""
    shop = ShopSettings.load()
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
        "SHOP_PRIMARY_COLOR": shop.primary_color or "#6D28D9",
        "SHOP_ACCENT_COLOR": shop.accent_color or "#FF4D77",
    }
