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

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import URLValidator
from django.db import models

from apps.core.models import TimeStampedModel

# ---------------------------------------------------------------- محدودیت حجم تصویر

HOMEPAGE_MEDIA_MAX_UPLOAD_BYTES = 5 * 1024 * 1024  # 5 MiB


def validate_image_size(value):
    """اعتبارسنجی حجم فایل تصویر — حداکثر ۵ مگابایت."""
    if value and hasattr(value, 'size') and value.size > HOMEPAGE_MEDIA_MAX_UPLOAD_BYTES:
        limit_mb = HOMEPAGE_MEDIA_MAX_UPLOAD_BYTES / (1024 * 1024)
        raise ValidationError(
            f"حجم تصویر نباید بیشتر از {limit_mb:.0f} مگابایت باشد. "
            f"حجم فعلی: {value.size / (1024 * 1024):.1f} مگابایت."
        )

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



# ---------------------------------------------------------------- صفحات محتوا

RESERVED_SLUGS = frozenset([
    "admin", "admin-panel", "products", "cart", "checkout", "account",
    "pages", "media", "static", "api", "blog", "home",
])


class ContentPage(TimeStampedModel):
    """صفحه‌ی محتوایی مدیریت‌شده — حریم خصوصی، قوانین، درباره ما و..."""

    class Status(models.TextChoices):
        DRAFT = "draft", "پیش‌نویس"
        PUBLISHED = "published", "منتشرشده"

    class FooterColumn(models.TextChoices):
        QUICK_ACCESS = "quick_access", "دسترسی سریع"
        CUSTOMER_SERVICE = "customer_service", "خدمات مشتریان"

    title = models.CharField("عنوان", max_length=200)
    slug = models.SlugField("اسلاگ", max_length=220, unique=True, allow_unicode=True)
    body = models.TextField("متن صفحه", blank=True)
    summary = models.CharField("خلاصه", max_length=300, blank=True)

    status = models.CharField(
        "وضعیت", max_length=10, choices=Status.choices, default=Status.DRAFT
    )
    published_at = models.DateTimeField("تاریخ انتشار", null=True, blank=True)
    published_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name="منتشرکننده",
        on_delete=models.SET_NULL, null=True, blank=True,
        related_name="published_pages",
    )

    seo_title = models.CharField("عنوان SEO", max_length=200, blank=True)
    seo_description = models.CharField("توضیحات SEO", max_length=300, blank=True)

    show_in_footer = models.BooleanField("نمایش در فوتر", default=False)
    footer_column = models.CharField(
        "ستون فوتر", max_length=20, choices=FooterColumn.choices,
        blank=True, default="",
    )
    display_order = models.PositiveIntegerField("ترتیب نمایش", default=0)

    class Meta:
        verbose_name = "صفحه‌ی محتوایی"
        verbose_name_plural = "صفحات محتوایی"
        ordering = ["display_order", "title"]
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(status="draft")
                    | models.Q(status="published", published_at__isnull=False)
                ),
                name="content_page_published_requires_timestamp",
            ),
        ]

    def __str__(self):
        return self.title

    @property
    def effective_seo_title(self):
        return self.seo_title or self.title

    @property
    def effective_seo_description(self):
        return self.seo_description or self.summary or ""

    def clean(self):
        super().clean()
        if self.slug and self.slug.lower() in RESERVED_SLUGS:
            raise ValidationError({"slug": "این اسلاگ رزرو شده و قابل استفاده نیست"})

    def get_absolute_url(self):
        from django.urls import reverse
        return reverse("content:page-detail", args=[self.slug])



# ---------------------------------------------------------------- محتوای صفحه اصلی


class HeroSlide(TimeStampedModel, DestinationMixin):
    """اسلاید اصلی صفحه اول — تصویر + متن + دکمه‌ی CTA."""

    title = models.CharField("عنوان", max_length=200, blank=True)
    subtitle = models.CharField("زیرعنوان", max_length=300, blank=True)
    desktop_image = models.ImageField("تصویر دسکتاپ", upload_to="homepage/hero/", validators=[validate_image_size])
    mobile_image = models.ImageField("تصویر موبایل", upload_to="homepage/hero/", blank=True, validators=[validate_image_size])
    button_label = models.CharField("متن دکمه", max_length=60, blank=True)
    show_button = models.BooleanField("نمایش دکمه", default=False)
    is_active = models.BooleanField("فعال", default=True)
    display_order = models.PositiveIntegerField("ترتیب نمایش", default=0)

    class Meta:
        verbose_name = "اسلاید اصلی"
        verbose_name_plural = "اسلایدهای اصلی"
        ordering = ["display_order", "id"]

    def __str__(self):
        return self.title or f"اسلاید #{self.pk}"

    def clean(self):
        super().clean()
        if self.show_button and not self.button_label:
            raise ValidationError({"button_label": "وقتی دکمه فعال است، متن دکمه الزامی است"})
        if self.show_button and self.destination_type == DestinationType.NONE:
            raise ValidationError({"destination_type": "وقتی دکمه فعال است، مقصد باید انتخاب شود"})


class PromotionalBanner(TimeStampedModel, DestinationMixin):
    """بنر تبلیغاتی صفحه اصلی."""

    title = models.CharField("عنوان", max_length=200, blank=True)
    description = models.CharField("توضیحات", max_length=500, blank=True)
    desktop_image = models.ImageField("تصویر دسکتاپ", upload_to="homepage/banners/", validators=[validate_image_size])
    mobile_image = models.ImageField("تصویر موبایل", upload_to="homepage/banners/", blank=True, validators=[validate_image_size])
    button_label = models.CharField("متن دکمه", max_length=60, blank=True)
    show_button = models.BooleanField("نمایش دکمه", default=False)
    is_active = models.BooleanField("فعال", default=True)
    display_order = models.PositiveIntegerField("ترتیب نمایش", default=0)

    class Meta:
        verbose_name = "بنر تبلیغاتی"
        verbose_name_plural = "بنرهای تبلیغاتی"
        ordering = ["display_order", "id"]

    def __str__(self):
        return self.title or f"بنر #{self.pk}"

    def clean(self):
        super().clean()
        if self.show_button and not self.button_label:
            raise ValidationError({"button_label": "وقتی دکمه فعال است، متن دکمه الزامی است"})
        if self.show_button and self.destination_type == DestinationType.NONE:
            raise ValidationError({"destination_type": "وقتی دکمه فعال است، مقصد باید انتخاب شود"})
