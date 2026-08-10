"""سرویسِ کادوپیچی — افزونه‌ی اختیاریِ سطحِ قلمِ سبد (toranj_gifting:
``optional_addon_checkbox_updates_total``).

قیمت/در دسترس‌بودن همیشه از ``ShopSettings`` (سمتِ سرور) خوانده می‌شود —
هیچ view/تمپلیتی هرگز مستقیماً به یک قیمتِ ارسال‌شده‌ی کلاینت برای این
افزونه اعتماد نمی‌کند. این ماژول تنها منبعِ حقیقتِ «آیا کادوپیچی برایِ این
Store در دسترس است؟» و «هزینه‌ی آن چقدر است؟» است — هم سبد و هم صفحه‌ی
محصول (برای پیش‌نمایشِ زنده‌ی جمعِ کل در toranj_gifting) باید از همین
تابع‌ها استفاده کنند.
"""

from decimal import Decimal

from apps.core.models import ShopSettings


def is_gift_wrap_available(store) -> bool:
    """آیا مدیرِ این Store کادوپیچی را فعال کرده — مستقل از خانواده‌ی بصری؛
    هر Storeای با هر خانواده می‌تواند این را روشن/خاموش کند."""
    settings_row = ShopSettings.load(store=store)
    return settings_row.gift_wrap_available


def resolve_gift_wrap_price(store) -> Decimal:
    """هزینه‌ی کادوپیچیِ هر قلم — همیشه از ``ShopSettings``، هرگز از کلاینت."""
    settings_row = ShopSettings.load(store=store)
    return settings_row.gift_wrap_price


def resolve_gift_wrap_selection(store, *, requested: bool) -> tuple[bool, Decimal]:
    """درخواستِ کلاینت (``requested``: آیا چک‌باکسِ کادوپیچی تیک خورده) را با
    پیکربندیِ واقعیِ Store تطبیق می‌دهد.

    اگر کادوپیچی برایِ این Store در دسترس نباشد، همیشه ``(False, 0)``
    برمی‌گرداند — صرف‌نظر از این‌که کلاینت چه چیزی درخواست کرده — تا هیچ
    قیمتِ کادوپیچی‌ای هرگز روی یک Storeِ بدونِ فعال‌سازیِ صریح اعمال نشود.
    """
    if not requested:
        return False, Decimal("0")
    if not is_gift_wrap_available(store):
        return False, Decimal("0")
    return True, resolve_gift_wrap_price(store)
