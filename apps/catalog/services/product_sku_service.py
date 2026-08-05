"""تولیدِ خودکارِ کدِ کالا (SKU) در سطحِ محصول — دکمه‌ی «تولید» در تبِ
«اطلاعات پایه»یِ فرمِ کالا.

قالب: ``PRD-XXXXXX`` — شش نویسه‌ی تصادفیِ حروفِ بزرگ/عدد، بدونِ نویسه‌های
مبهم (0/O/1/I) که ممکن است در چاپِ برچسب یا خواندنِ چشمی اشتباه گرفته
شوند. یکتاییِ آن فقط در محدوده‌ی همان Store بررسی می‌شود (دقیقاً همان
قراردادِ ``uniq_product_sku_per_store``) — نه یکتاییِ سراسری.

عمداً از یک پسوندِ تصادفی با بررسی/تلاشِ دوباره (به‌جایِ شمارنده‌ی
افزایشیِ max+1) استفاده می‌شود تا زیرِ بارِ هم‌زمان چند درخواستِ ساختِ
کالا هیچ نیازی به قفلِ سطرهای دیتابیس (select_for_update) یا وضعیتِ
مشترکِ قابلِ‌رقابت نداشته باشد — دقیقاً همان الگویِ «بساز → بررسیِ
یکتایی → تلاشِ دوباره» که ``attribute_service._unique_code`` و
``variant_service.generate_variant_sku`` از قبل در همین پایگاه‌کد
استفاده می‌کنند."""

from django.utils.crypto import get_random_string

from apps.catalog.models import Product

#: بدونِ ۰/O/1/I — برایِ پرهیز از ابهامِ چاپی/چشمی.
_SKU_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
_SKU_SUFFIX_LENGTH = 6
_MAX_ATTEMPTS = 10


class ProductSkuGenerationError(Exception):
    """پس از چند تلاش هم نتوانست کدِ یکتا بسازد — عملاً هرگز نباید رخ دهد."""


def generate_product_sku(store) -> str:
    """یک کدِ کالایِ ``PRD-XXXXXX`` یکتا در محدوده‌ی ``store`` برمی‌گرداند.

    فقط پیشنهاد می‌دهد — مقدارِ ورودیِ فیلدِ SKU همچنان توسطِ مدیرِ فروشگاه
    قابلِ‌ویرایش می‌ماند و یکتاییِ نهایی باز هم توسطِ
    ``ProductForm.clean_sku`` هنگامِ ذخیره بررسی می‌شود."""
    for _ in range(_MAX_ATTEMPTS):
        candidate = f"PRD-{get_random_string(_SKU_SUFFIX_LENGTH, allowed_chars=_SKU_ALPHABET)}"
        if not Product.objects.filter(store=store, sku=candidate).exists():
            return candidate
    raise ProductSkuGenerationError("پس از چند تلاش نتوانستیم کدِ کالایِ یکتا بسازیم؛ دوباره تلاش کنید.")
