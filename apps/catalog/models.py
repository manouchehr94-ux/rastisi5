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


class ProductImage(TimeStampedModel):
    product = models.ForeignKey(Product, verbose_name="کالا", on_delete=models.CASCADE, related_name="images")
    image = models.ImageField("تصویر", upload_to="products/gallery/")
    alt = models.CharField("متن جایگزین", max_length=200, blank=True)
    order = models.PositiveIntegerField("ترتیب", default=0)

    class Meta:
        verbose_name = "تصویر کالا"
        verbose_name_plural = "گالری تصاویر کالا"
        ordering = ["order", "id"]

    def __str__(self):
        return f"{self.product.name} — تصویر {self.order}"


class ProductVariant(TimeStampedModel):
    """تنوع جنریک محصول (رنگ، سایز، وزن و...) از طریق attribute/value."""

    product = models.ForeignKey(Product, verbose_name="کالا", on_delete=models.CASCADE, related_name="variants")
    attribute = models.CharField("ویژگی", max_length=60)
    value = models.CharField("مقدار", max_length=60)
    value_hex = models.CharField("کد رنگ (Hex)", max_length=9, blank=True)
    stock = models.PositiveIntegerField("موجودی", default=0)
    extra_price = models.DecimalField("مبلغ اضافه (تومان)", max_digits=12, decimal_places=0, default=0)

    class Meta:
        verbose_name = "تنوع کالا"
        verbose_name_plural = "تنوع‌های کالا"
        ordering = ["attribute", "value"]

    def __str__(self):
        return f"{self.product.name} — {self.attribute}: {self.value}"


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
