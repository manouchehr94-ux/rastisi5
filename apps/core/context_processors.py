from django.conf import settings


def shop_settings(request):
    """هویت و تنظیمات عمومی پلتفرم — در همه‌ی تمپلیت‌ها بدون پاس‌دادن دستی در دسترس است."""
    return {
        "SHOP_NAME": getattr(settings, "SHOP_NAME", "فروشگاه اینترنتی"),
        "SHOP_TAGLINE": getattr(settings, "SHOP_TAGLINE", ""),
        "SHOP_CONTACT_PHONE": getattr(settings, "SHOP_CONTACT_PHONE", ""),
        "SHOP_CONTACT_EMAIL": getattr(settings, "SHOP_CONTACT_EMAIL", ""),
        "SHOP_CONTACT_ADDRESS": getattr(settings, "SHOP_CONTACT_ADDRESS", ""),
        "SHOP_FREE_SHIPPING_THRESHOLD": getattr(settings, "SHOP_FREE_SHIPPING_THRESHOLD", 0),
    }
