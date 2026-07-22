from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from apps.catalog.models import Brand, Category, Product


class HomeViewTests(TestCase):
    def setUp(self):
        self.vendor_category = Category.objects.create(name="لوازم خانگی", slug="home-hv", icon="🏠")
        self.sub_category = Category.objects.create(
            name="آشپزخانه", slug="kitchen-hv", icon="🍳", parent=self.vendor_category
        )
        from apps.catalog.models import Vendor

        self.vendor = Vendor.objects.create(name="فروشگاه", slug="shop-hv")
        self.brand = Brand.objects.create(name="برند", slug="brand-hv")
        self.sold_product = Product.objects.create(
            vendor=self.vendor, category=self.sub_category, brand=self.brand,
            name="محصول پرفروش", slug="best-seller-hv", sku="SKU-HV1",
            price=Decimal("100000"), sold_count=500, views_count=10, discount_percent=0,
        )
        self.discounted_product = Product.objects.create(
            vendor=self.vendor, category=self.sub_category, name="محصول تخفیف‌دار", slug="discounted-hv",
            sku="SKU-HV2", price=Decimal("200000"), discount_percent=30, sold_count=1, views_count=999,
        )

    def test_home_page_loads(self):
        response = self.client.get(reverse("catalog:home"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "محصول پرفروش")
        self.assertContains(response, "آشپزخانه")

    def test_home_best_products_defaults_to_sold_count(self):
        response = self.client.get(reverse("catalog:home"))
        content = response.content.decode()
        self.assertLess(content.index("محصول پرفروش"), content.index("محصول تخفیف‌دار"))

    def test_home_best_products_partial_sorts_by_discount(self):
        url = reverse("catalog:home-best-products")
        response = self.client.get(url, {"sort": "disc"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "محصول تخفیف‌دار")
        self.assertNotContains(response, "محصول پرفروش")

    def test_home_best_products_invalid_sort_falls_back_to_default(self):
        url = reverse("catalog:home-best-products")
        response = self.client.get(url, {"sort": "not-a-real-sort"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "محصول پرفروش")
