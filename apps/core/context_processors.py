from apps.content.models import SocialLink
from apps.core.color_utils import darken_hex, foreground_for, mix_hex, safe_hex
from apps.core.models import ShopSettings, ShopSettingsNotProvisionedError
from apps.stores.resolution import StoreResolutionError


def _versioned_colors(request):
    """اگر همین request توسطِ یک ویوِ سازنده بصری (Preview یا صفحه‌ی
    عمومیِ حالتِ Visual Layout) مشخصاً روی ``request.storefront_appearance_version``
    ست شده باشد، رنگ‌های نهایی از همان نسخه (Draft یا Published) حل
    می‌شوند — نه از ``ShopSettings`` زنده.

    این تنها هوکِ صریحی است که دو مسیرِ متفاوت (Builder-aware در برابرِ
    هر صفحه‌ی دیگر — پرداخت، جزئیاتِ کالا، ...) را از هم جدا می‌کند:
    این context processor خودش هرگز حدس نمی‌زند کدام View در حالِ اجراست
    (بر اساسِ URL/pattern-matching)، فقط یک attribute صریح را می‌خواند
    که همان View از قبل تنظیم کرده — دقیقاً همان دلیلی که گزارشِ ممیزی
    این را «ریسک‌دارترین بخشِ این تغییر» نامیده بود: حدس‌زدن بر اساسِ URL
    شکننده است، یک attribute صریح نیست.

    هر صفحه‌ی دیگر (که این attribute را ست نمی‌کند) دقیقاً مثلِ قبل رفتار
    می‌کند — رنگِ زنده‌ی ``ShopSettings``، بدونِ هیچ مفهومِ Draft."""
    version = getattr(request, "storefront_appearance_version", None)
    if version is None:
        return None

    from apps.storefront_builder import appearance_registry

    colors = appearance_registry.resolve_colors(version.effective_appearance_config())
    return colors


def shop_settings(request):
    """هویت و تنظیمات فروشگاهِ Store جاری — از همان رکورد ShopSettings که پنل مدیریت › تنظیمات ویرایش می‌کند.

    Store از ``request.store`` (که middleware مرحله‌ی تحلیل میزبان تنظیم
    کرده) خوانده می‌شود. اگر هنوز میزبان درخواست به هیچ Store‌ای resolve
    نشده باشد (``request.store is None``)، ``ShopSettings.load()`` بدون
    آرگومان به حالت سازگاریِ موقت (تک‌فروشگاهی Akhlaghi) برمی‌گردد و در غیر
    آن صورت fail-closed می‌شود — هرگز تنظیمات یک Store دیگر را برنمی‌گرداند.

    یک Host ناشناخته/غیرمجاز (نه در ``STORES_DEVELOPMENT_HOST_ALLOWLIST``، نه
    ``StoreDomain`` تأییدشده) وقتی بیش از یک Store در دیتابیس وجود دارد، به
    ``StoreResolutionError`` می‌رسد — این context processor روی **هر**
    template (از جمله صفحه‌ی خطای ۴۰۴ خودِ Django) اجرا می‌شود، پس این حالت
    باید امن مدیریت شود، نه این‌که رندر صفحه‌ی خطا را خودش با یک ۵۰۰ جدید
    خراب کند. یک دیکشنری خالی برمی‌گرداند — تمپلیت‌ها با فیلتر ``|default``
    از قبل برای نبود این متغیرها آماده‌اند.

    رنگ‌ها (فقط رنگ‌ها) ممکن است به‌جایِ ``ShopSettings`` زنده، از نسخه‌ی
    Draft/Published سازنده بصری بیایند — نگاه کنید به ``_versioned_colors``.
    """
    try:
        shop = ShopSettings.load(store=getattr(request, "store", None))
    except (StoreResolutionError, ShopSettingsNotProvisionedError):
        return {}

    versioned = _versioned_colors(request)
    if versioned is not None:
        primary = safe_hex(versioned.get("primary"), "#6D28D9")
        accent = safe_hex(versioned.get("accent"), "#FF4D77")
        secondary = safe_hex(versioned.get("secondary"), "#7C3AED")
        background = safe_hex(versioned.get("background"), "#F7F5FC")
        surface = safe_hex(versioned.get("surface"), "#FFFFFF")
        text = safe_hex(versioned.get("text"), "#241C3A")
        muted = safe_hex(versioned.get("muted"), "#8B86A3")
        border = safe_hex(versioned.get("border"), mix_hex(text, surface, 0.12))
    else:
        primary = safe_hex(shop.primary_color, "#6D28D9")
        accent = safe_hex(shop.accent_color, "#FF4D77")
        secondary = safe_hex(shop.secondary_color, "#7C3AED")
        background = safe_hex(shop.background_color, "#F7F5FC")
        surface = safe_hex(shop.surface_color, "#FFFFFF")
        text = safe_hex(shop.text_color, "#241C3A")
        muted = safe_hex(shop.muted_text_color, "#8B86A3")
        border = mix_hex(text, surface, 0.12)

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
        "SHOP_BORDER_COLOR": border,
        # شبکه‌های اجتماعی — store_id (نه shop.store) تا از یک query اضافی برای واکشی خودِ Store پرهیز شود
        "SOCIAL_LINKS_FOOTER": SocialLink.objects.filter(
            is_active=True, show_in_footer=True, store_id=shop.store_id,
        ).order_by("display_order", "id"),
        "SOCIAL_LINKS_HEADER": SocialLink.objects.filter(
            is_active=True, show_in_header=True, store_id=shop.store_id,
        ).order_by("display_order", "id"),
    }
