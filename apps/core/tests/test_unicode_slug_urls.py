"""رگرسیون: اسلاگ‌های فارسی (allow_unicode=True) باید در URL هم قابل تطبیق باشند.

باگ واقعی: مبدل داخلی Django `<slug:...>` فقط ASCII را می‌پذیرد در حالی
که همه‌ی SlugField های پروژه با allow_unicode=True ساخته می‌شوند — نتیجه
NoReverseMatch/404 برای هر کالا/دسته‌ای که نامش به فارسی اسلاگ شود. رفع
شده با مبدل سفارشی UnicodeSlugConverter (apps/core/converters.py) و
`<uslug:...>` در urls.py های catalog/cart/customers.
"""

from decimal import Decimal
from urllib.parse import unquote

from django.test import TestCase
from django.urls import resolve, reverse

from apps.catalog.models import Category, Product, Vendor

PERSIAN_SLUG = "پکیج-ایران-رادیاتور-m24"


class UnicodeSlugUrlTests(TestCase):
    def setUp(self):
        self.vendor = Vendor.objects.create(name="فروشنده", slug="vendor-uslug")
        self.category = Category.objects.create(name="دسته", slug="cat-uslug")
        self.product = Product.objects.create(
            vendor=self.vendor, category=self.category, name="پکیج ایران رادیاتور M24",
            slug=PERSIAN_SLUG, sku="SKU-USLUG-1", price=Decimal("1000000"),
        )

    def test_reverse_product_detail_with_persian_slug(self):
        url = reverse("catalog:product-detail", args=[self.product.slug])
        self.assertIn(self.product.slug, unquote(url))

    def test_resolve_product_detail_with_persian_slug(self):
        url = reverse("catalog:product-detail", args=[self.product.slug])
        match = resolve(unquote(url))
        self.assertEqual(match.kwargs["slug"], self.product.slug)

    def test_product_detail_page_loads(self):
        url = reverse("catalog:product-detail", args=[self.product.slug])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

    def test_home_page_with_persian_slug_product_does_not_raise(self):
        """قبل از رفع باگ، همین درخواست با NoReverseMatch در home.html شکست می‌خورد."""
        response = self.client.get(reverse("catalog:home"))
        self.assertEqual(response.status_code, 200)

    def test_cart_add_with_persian_slug(self):
        url = reverse("cart:add", args=[self.product.slug])
        response = self.client.post(url, {"quantity": 1})
        self.assertIn(response.status_code, (200, 204))

    def test_ascii_slug_still_resolves(self):
        """مبدل جدید نباید اسلاگ‌های ASCII قدیمی را بشکند."""
        ascii_product = Product.objects.create(
            vendor=self.vendor, category=self.category, name="Ascii Product",
            slug="ascii-product-1", sku="SKU-USLUG-2", price=Decimal("500000"),
        )
        url = reverse("catalog:product-detail", args=[ascii_product.slug])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
