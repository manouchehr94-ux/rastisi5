from decimal import ROUND_HALF_UP, Decimal

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from apps.core.models import TimeStampedModel


class Vendor(TimeStampedModel):
    """فروشنده / فروشگاه — پایه‌ی چند فروشنده‌ای (Multi-Vendor Ready)."""

    name = models.CharField("نام فروشنده", max_length=150)
    slug = models.SlugField("اسلاگ", max_length=170, unique=True, allow_unicode=True)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="مالک",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="vendors",
    )
    logo = models.ImageField("لوگو", upload_to="vendors/logos/", null=True, blank=True)
    description = models.TextField("توضیحات", blank=True)
    is_active = models.BooleanField("فعال", default=True)

    class Meta:
        verbose_name = "فروشنده"
        verbose_name_plural = "فروشندگان"
        ordering = ["name"]

    def __str__(self):
        return self.name


class Category(TimeStampedModel):
    """دسته‌بندی درختی، خودارجاع (حداقل دو سطح)."""

    name = models.CharField("نام", max_length=120)
    slug = models.SlugField("اسلاگ", max_length=140, unique=True, allow_unicode=True)
    icon = models.CharField("آیکون", max_length=20, blank=True)
    parent = models.ForeignKey(
        "self",
        verbose_name="دسته‌ی والد",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="children",
    )
    order = models.PositiveIntegerField("ترتیب", default=0)
    is_active = models.BooleanField("فعال", default=True)

    class Meta:
        verbose_name = "دسته‌بندی"
        verbose_name_plural = "دسته‌بندی‌ها"
        ordering = ["order", "name"]

    def __str__(self):
        return self.name


class Brand(TimeStampedModel):
    name = models.CharField("نام برند", max_length=120)
    slug = models.SlugField("اسلاگ", max_length=140, unique=True, allow_unicode=True)
    logo = models.ImageField("لوگو", upload_to="brands/logos/", null=True, blank=True)

    class Meta:
        verbose_name = "برند"
        verbose_name_plural = "برندها"
        ordering = ["name"]

    def __str__(self):
        return self.name


class Product(TimeStampedModel):
    class Status(models.TextChoices):
        ACTIVE = "active", "فعال"
        INACTIVE = "inactive", "غیرفعال"
        DRAFT = "draft", "پیش‌نویس"

    class Tag(models.TextChoices):
        NEW = "new", "جدید"
        HOT = "hot", "پرفروش"
        SALE = "sale", "حراج"

    class ProductType(models.TextChoices):
        SIMPLE = "simple", "کالای ساده"
        VARIABLE = "variable", "کالای دارای تنوع"

    vendor = models.ForeignKey(Vendor, verbose_name="فروشنده", on_delete=models.CASCADE, related_name="products")
    category = models.ForeignKey(Category, verbose_name="دسته‌بندی", on_delete=models.PROTECT, related_name="products")
    brand = models.ForeignKey(
        Brand, verbose_name="برند", on_delete=models.SET_NULL, null=True, blank=True, related_name="products"
    )

    name = models.CharField("نام کالا", max_length=220)
    slug = models.SlugField("اسلاگ", max_length=240, unique=True, allow_unicode=True)
    sku = models.CharField("کد کالا (SKU)", max_length=40, unique=True)
    description = models.TextField("توضیحات", blank=True)

    price = models.DecimalField("قیمت پایه (تومان)", max_digits=12, decimal_places=0)
    discount_percent = models.PositiveSmallIntegerField(
        "درصد تخفیف", default=0, validators=[MinValueValidator(0), MaxValueValidator(100)]
    )

    stock = models.PositiveIntegerField("موجودی انبار", default=0)
    status = models.CharField("وضعیت", max_length=10, choices=Status.choices, default=Status.ACTIVE)
    product_type = models.CharField(
        "نوع کالا", max_length=10, choices=ProductType.choices, default=ProductType.SIMPLE
    )

    rating = models.DecimalField(
        "میانگین امتیاز", max_digits=3, decimal_places=2, default=0,
        validators=[MinValueValidator(0), MaxValueValidator(5)],
    )
    reviews_count = models.PositiveIntegerField("تعداد نظرات", default=0)
    sold_count = models.PositiveIntegerField("تعداد فروش", default=0)
    views_count = models.PositiveIntegerField("تعداد بازدید", default=0)

    tag = models.CharField("برچسب", max_length=10, choices=Tag.choices, blank=True)
    icon = models.CharField("آیکون/اموجی", max_length=20, blank=True)
    tint = models.CharField("رنگ پس‌زمینه کارت", max_length=20, blank=True)

    class Meta:
        verbose_name = "کالا"
        verbose_name_plural = "کالاها"
        ordering = ["-created_at"]

    def __str__(self):
        return self.name

    @property
    def final_price(self):
        """قیمت نهایی = price * (1 - discount_percent/100)، گرد شده."""
        factor = (Decimal(100) - self.discount_percent) / Decimal(100)
        return (self.price * factor).quantize(Decimal("1"), rounding=ROUND_HALF_UP)

    @property
    def is_variable(self):
        return self.product_type == self.ProductType.VARIABLE

    @property
    def cover_image(self):
        """تصویر کاور کالا برای کارت محصول — از cache مربوط به prefetch_related('images') استفاده می‌کند تا N+1 پیش نیاید."""
        images = list(self.images.all())
        if not images:
            return None
        for img in images:
            if img.is_cover:
                return img
        return images[0]


class ProductImage(TimeStampedModel):
    product = models.ForeignKey(Product, verbose_name="کالا", on_delete=models.CASCADE, related_name="images")
    image = models.ImageField("تصویر", upload_to="products/gallery/")
    thumbnail = models.ImageField("تصویر بندانگشتی", upload_to="products/thumbnails/", null=True, blank=True)
    alt = models.CharField("متن جایگزین", max_length=200, blank=True)
    order = models.PositiveIntegerField("ترتیب", default=0)
    is_cover = models.BooleanField("تصویر اصلی (کاور)", default=False)

    class Meta:
        verbose_name = "تصویر کالا"
        verbose_name_plural = "گالری تصاویر کالا"
        ordering = ["order", "id"]

    def __str__(self):
        return f"{self.product.name} — تصویر {self.order}"


class VariantMutationError(Exception):
    """تلاش برای تغییر فیلدهای حساس به نرمال‌سازی از مسیری که نرمال‌سازی را دور می‌زند."""


def _normalize_variant_fields(instance: "ProductVariant") -> None:
    """attribute/value/sku یک نمونه‌ی ProductVariant را نرمال و فیلدهای normalized_* را از روی آن‌ها محاسبه می‌کند.

    هم ``ProductVariant.save()`` و هم ``ProductVariantQuerySet.bulk_create()`` از همین
    تابع استفاده می‌کنند تا نرمال‌سازی هرگز در دو جا تکرار/ناهم‌سو نشود.
    """
    from apps.core.utils import normalization_key, normalize_digits

    instance.attribute = (instance.attribute or "").strip()
    instance.value = (instance.value or "").strip()
    instance.normalized_attribute = normalization_key(instance.attribute)
    instance.normalized_value = normalization_key(instance.value)
    instance.sku = normalize_digits(instance.sku or "").strip()


class ProductVariantQuerySet(models.QuerySet):
    """کوئری‌ست اختصاصی ProductVariant — مسیرهای فله‌ای دور زننده‌ی ``save()`` را کنترل می‌کند.

    ``bulk_create()`` قبل از درج، هر نمونه را نرمال می‌کند (چون Django هرگز
    ``save()``/``clean()`` را برای bulk_create صدا نمی‌زند). ``update()`` و
    ``bulk_update()`` تغییر مستقیم فیلدهای حساس به نرمال‌سازی را رد می‌کنند، چون
    یک SQL UPDATE ساده نمی‌تواند normalized_attribute/normalized_value را هم‌زمان
    و درست بازمحاسبه کند؛ برای این فیلدها باید از ``instance.save()`` یا
    ``apps.catalog.services.variant_service`` استفاده شود.
    """

    NORMALIZATION_SENSITIVE_FIELDS = frozenset(
        {"attribute", "value", "sku", "normalized_attribute", "normalized_value"}
    )

    def bulk_create(self, objs, *args, **kwargs):
        objs = list(objs)
        for obj in objs:
            _normalize_variant_fields(obj)
        return super().bulk_create(objs, *args, **kwargs)

    def bulk_update(self, objs, fields, *args, **kwargs):
        blocked = self.NORMALIZATION_SENSITIVE_FIELDS.intersection(fields)
        if blocked:
            raise VariantMutationError(
                "فیلدهای {} را نمی‌توان با bulk_update تغییر داد؛ از instance.save() یا "
                "apps.catalog.services.variant_service استفاده کنید.".format("، ".join(sorted(blocked)))
            )
        return super().bulk_update(objs, fields, *args, **kwargs)

    def update(self, **kwargs):
        blocked = self.NORMALIZATION_SENSITIVE_FIELDS.intersection(kwargs)
        if blocked:
            raise VariantMutationError(
                "فیلدهای {} را نمی‌توان مستقیماً با update() تغییر داد؛ از instance.save() یا "
                "apps.catalog.services.variant_service استفاده کنید.".format("، ".join(sorted(blocked)))
            )
        return super().update(**kwargs)


ProductVariantManager = models.Manager.from_queryset(ProductVariantQuerySet)


class ProductVariant(TimeStampedModel):
    """تنوع جنریک محصول (رنگ، سایز، وزن و...) از طریق attribute/value.

    ``attribute`` نام تنوعی است که فروشنده تعریف می‌کند (مثل «طول» یا «رایحه»)
    و در کد هاردکد نمی‌شود. ``normalized_attribute``/``normalized_value`` فقط
    برای جلوگیری از ثبت مقدار تکراری (با اختلاف فاصله/ارقام فارسی-لاتین)
    محاسبه و نگه‌داری می‌شوند و مستقیماً توسط کاربر ویرایش نمی‌شوند.
    """

    objects = ProductVariantManager()

    product = models.ForeignKey(Product, verbose_name="کالا", on_delete=models.CASCADE, related_name="variants")
    attribute = models.CharField("نام تنوع", max_length=60)
    value = models.CharField("مقدار تنوع", max_length=60)
    normalized_attribute = models.CharField(max_length=80, editable=False, blank=True, default="")
    normalized_value = models.CharField(max_length=80, editable=False, blank=True, default="")
    value_hex = models.CharField("کد رنگ (Hex)", max_length=9, blank=True)
    sku = models.CharField("کد کالا (SKU)", max_length=64, blank=True, default="")
    stock = models.PositiveIntegerField("موجودی", default=0)
    extra_price = models.DecimalField("تغییر قیمت (تومان)", max_digits=12, decimal_places=0, default=0)
    is_active = models.BooleanField("فعال", default=True)
    display_order = models.PositiveIntegerField("ترتیب نمایش", default=0)

    class Meta:
        verbose_name = "تنوع کالا"
        verbose_name_plural = "تنوع‌های کالا"
        ordering = ["display_order", "attribute", "value"]
        constraints = [
            models.UniqueConstraint(
                fields=["product", "normalized_attribute", "normalized_value"],
                condition=models.Q(is_active=True),
                name="uniq_active_variant_value_per_product",
            ),
            models.UniqueConstraint(
                fields=["sku"],
                condition=~models.Q(sku=""),
                name="uniq_variant_sku_when_set",
            ),
        ]

    def __str__(self):
        return f"{self.product.name} — {self.attribute}: {self.value}"

    def clean(self):
        from django.core.exceptions import ValidationError

        errors = {}
        attribute = (self.attribute or "").strip()
        value = (self.value or "").strip()
        if not attribute:
            errors["attribute"] = "نام تنوع نمی‌تواند خالی باشد."
        if not value:
            errors["value"] = "مقدار تنوع نمی‌تواند خالی باشد."
        if errors:
            raise ValidationError(errors)
        self.attribute = attribute
        self.value = value

    def save(self, *args, **kwargs):
        _normalize_variant_fields(self)
        super().save(*args, **kwargs)


class Specification(TimeStampedModel):
    """مشخصه‌ی فنی توصیفی کالا (برچسب/مقدار) — انتخابی مشتری نیست، فقط اطلاعاتی."""

    product = models.ForeignKey(
        Product, verbose_name="کالا", on_delete=models.CASCADE, related_name="specifications"
    )
    label = models.CharField("عنوان مشخصه", max_length=100)
    value = models.CharField("مقدار", max_length=300, blank=True)
    order = models.PositiveIntegerField("ترتیب نمایش", default=0)

    class Meta:
        verbose_name = "مشخصه فنی"
        verbose_name_plural = "مشخصات فنی"
        ordering = ["order", "id"]

    def __str__(self):
        return f"{self.product.name} — {self.label}"

    def clean(self):
        from django.core.exceptions import ValidationError

        label = (self.label or "").strip()
        if not label:
            raise ValidationError({"label": "عنوان مشخصه نمی‌تواند خالی باشد."})
        self.label = label
        self.value = (self.value or "").strip()

    def save(self, *args, **kwargs):
        self.label = (self.label or "").strip()
        self.value = (self.value or "").strip()
        super().save(*args, **kwargs)


class SpecificationTemplate(TimeStampedModel):
    """قالب مشخصات قابل‌استفاده‌ی مجدد — فهرستی از عنوان‌های پیشنهادی، نه یک اسکیمای پیچیده."""

    name = models.CharField("نام قالب", max_length=100, unique=True)
    category = models.ForeignKey(
        Category, verbose_name="دسته‌بندی مرتبط", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="specification_templates",
    )

    class Meta:
        verbose_name = "قالب مشخصات"
        verbose_name_plural = "قالب‌های مشخصات"
        ordering = ["name"]

    def __str__(self):
        return self.name


class SpecificationTemplateField(TimeStampedModel):
    template = models.ForeignKey(
        SpecificationTemplate, verbose_name="قالب", on_delete=models.CASCADE, related_name="fields"
    )
    label = models.CharField("عنوان مشخصه", max_length=100)
    order = models.PositiveIntegerField("ترتیب نمایش", default=0)

    class Meta:
        verbose_name = "فیلد قالب مشخصات"
        verbose_name_plural = "فیلدهای قالب مشخصات"
        ordering = ["order", "id"]
        constraints = [
            models.UniqueConstraint(fields=["template", "label"], name="uniq_template_field_label"),
        ]

    def __str__(self):
        return f"{self.template.name} — {self.label}"

    def clean(self):
        from django.core.exceptions import ValidationError

        label = (self.label or "").strip()
        if not label:
            raise ValidationError({"label": "عنوان فیلد نمی‌تواند خالی باشد."})
        self.label = label

    def save(self, *args, **kwargs):
        self.label = (self.label or "").strip()
        super().save(*args, **kwargs)


class Review(TimeStampedModel):
    product = models.ForeignKey(Product, verbose_name="کالا", on_delete=models.CASCADE, related_name="reviews")
    customer = models.ForeignKey(
        "customers.Customer", verbose_name="مشتری", on_delete=models.CASCADE, related_name="reviews"
    )
    rating = models.PositiveSmallIntegerField("امتیاز", validators=[MinValueValidator(1), MaxValueValidator(5)])
    text = models.TextField("متن نظر")
    is_approved = models.BooleanField("تأییدشده", default=False)

    class Meta:
        verbose_name = "نظر"
        verbose_name_plural = "نظرات"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.customer} — {self.product.name} ({self.rating}★)"
