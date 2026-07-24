"""مدل‌های پایه‌ی محتوای مدیریت‌شده — مقصد امن برای لینک‌های فروشگاه.

این ماژول زیرساخت اشتراکی «مقصد امن» را فراهم می‌کند. هر مدلی که بخواهد به یک
صفحه‌ی داخلی (محصول، دسته‌بندی، برند) یا یک آدرس خارجی لینک بدهد، از این
مدل انتزاعی ارث‌بری می‌کند.

تصمیمات معماری:
- GenericForeignKey استفاده نشد (عدم ایمنی ارجاعی)
- مسیرهای خام داخلی ذخیره نمی‌شود (شکنندگی URL)
- هر رکورد دقیقاً یک مقصد معتبر دارد (اعتبارسنجی در سطح مدل)
- حذف مقصد داخلی: SET_NULL → resolver بازمی‌گرداند None
- طرح‌های URL خطرناک (javascript:, data:, //) رد می‌شوند
"""

import re

from django.core.exceptions import ValidationError
from django.core.validators import URLValidator
from django.db import models

from apps.core.models import TimeStampedModel

# طرح‌های مجاز برای لینک خارجی
ALLOWED_SCHEMES = ["https", "http", "mailto", "tel"]

# الگوی تشخیص URL نسبی پروتکل (protocol-relative)
PROTOCOL_RELATIVE_RE = re.compile(r"^//")

# طرح‌های خطرناک
DANGEROUS_SCHEME_RE = re.compile(r"^(javascript|data|vbscript):", re.IGNORECASE)


def validate_external_url(value: str) -> None:
    """اعتبارسنجی URL خارجی: فقط طرح‌های مجاز، بدون URL خطرناک."""
    value = value.strip()

    if not value:
        raise ValidationError("آدرس لینک خارجی الزامی است")

    if DANGEROUS_SCHEME_RE.match(value):
        raise ValidationError("طرح URL غیرمجاز است (javascript/data)")

    if PROTOCOL_RELATIVE_RE.match(value):
        raise ValidationError("آدرس نسبی پروتکل (//...) مجاز نیست")

    # اعتبارسنجی با طرح‌های مجاز
    validator = URLValidator(schemes=ALLOWED_SCHEMES)
    try:
        validator(value)
    except ValidationError:
        # mailto و tel ممکن است URLValidator استاندارد پشتیبانی نکند
        if value.startswith("mailto:") or value.startswith("tel:"):
            return  # مجاز
        raise ValidationError("آدرس URL معتبر نیست")


class DestinationType(models.TextChoices):
    """انواع مقصد ممکن برای لینک‌های مدیریت‌شده‌ی فروشگاه."""
    NONE = "none", "بدون مقصد"
    CATEGORY = "category", "دسته‌بندی"
    PRODUCT = "product", "محصول"
    BRAND = "brand", "برند"
    EXTERNAL = "external", "لینک خارجی"


class DestinationMixin(models.Model):
    """مدل انتزاعی مقصد امن — هر مدل محتوایی که نیاز به لینک دارد از این ارث‌بری می‌کند.

    اعتبارسنجی تضمین می‌کند:
    - دقیقاً یک مقصد بر اساس نوع انتخاب‌شده تنظیم شده
    - هیچ ترکیب متناقضی از مقاصد وجود ندارد
    - URL خارجی فقط طرح‌های امن را می‌پذیرد
    """

    destination_type = models.CharField(
        "نوع مقصد", max_length=20,
        choices=DestinationType.choices, default=DestinationType.NONE,
    )
    destination_category = models.ForeignKey(
        "catalog.Category", verbose_name="دسته‌بندی مقصد",
        on_delete=models.SET_NULL, null=True, blank=True,
        related_name="+",
    )
    destination_product = models.ForeignKey(
        "catalog.Product", verbose_name="محصول مقصد",
        on_delete=models.SET_NULL, null=True, blank=True,
        related_name="+",
    )
    destination_brand = models.ForeignKey(
        "catalog.Brand", verbose_name="برند مقصد",
        on_delete=models.SET_NULL, null=True, blank=True,
        related_name="+",
    )
    destination_external_url = models.CharField(
        "آدرس لینک خارجی", max_length=500, blank=True,
    )
    open_in_new_tab = models.BooleanField("باز شدن در تب جدید", default=False)

    class Meta:
        abstract = True

    def clean(self):
        super().clean()
        self._validate_destination_coherence()

    def _validate_destination_coherence(self):
        """اعتبارسنجی انسجام مقصد: دقیقاً یک مقصد مطابق نوع انتخاب‌شده."""
        dtype = self.destination_type
        cat = self.destination_category_id
        prod = self.destination_product_id
        brand = self.destination_brand_id
        ext = (self.destination_external_url or "").strip()

        internal_set = [f for f in [cat, prod, brand] if f]
        has_ext = bool(ext)

        if dtype == DestinationType.NONE:
            if internal_set or has_ext:
                raise ValidationError("وقتی نوع مقصد «بدون مقصد» است، نباید مقصدی انتخاب شود")

        elif dtype == DestinationType.CATEGORY:
            if not cat:
                raise ValidationError("دسته‌بندی مقصد باید انتخاب شود")
            if prod or brand or has_ext:
                raise ValidationError("فقط دسته‌بندی باید انتخاب شود")

        elif dtype == DestinationType.PRODUCT:
            if not prod:
                raise ValidationError("محصول مقصد باید انتخاب شود")
            if cat or brand or has_ext:
                raise ValidationError("فقط محصول باید انتخاب شود")

        elif dtype == DestinationType.BRAND:
            if not brand:
                raise ValidationError("برند مقصد باید انتخاب شود")
            if cat or prod or has_ext:
                raise ValidationError("فقط برند باید انتخاب شود")

        elif dtype == DestinationType.EXTERNAL:
            if not has_ext:
                raise ValidationError("آدرس لینک خارجی الزامی است")
            if internal_set:
                raise ValidationError("وقتی مقصد خارجی است، نباید مقصد داخلی انتخاب شود")
            validate_external_url(ext)

    def save(self, *args, **kwargs):
        # نرمال‌سازی URL خارجی
        if self.destination_external_url:
            self.destination_external_url = self.destination_external_url.strip()
        super().save(*args, **kwargs)
