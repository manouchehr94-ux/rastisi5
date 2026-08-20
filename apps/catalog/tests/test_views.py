from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from apps.catalog.models import Brand, Category, Product
from apps.stores.models import Store


def _akhlaghi():
    return Store.objects.get(slug="akhlaghi")


class HomeViewTests(TestCase):
    def setUp(self):
        self.store = _akhlaghi()
        self.vendor_category = Category.objects.create(store=self.store, name="لوازم خانگی", slug="home-hv", icon="🏠")
        self.sub_category = Category.objects.create(
            store=self.store, name="آشپزخانه", slug="kitchen-hv", icon="🍳", parent=self.vendor_category
        )
        from apps.catalog.models import Vendor

        self.vendor = Vendor.objects.create(store=self.store, name="فروشگاه", slug="shop-hv")
        self.brand = Brand.objects.create(store=self.store, name="برند", slug="brand-hv")
        self.sold_product = Product.objects.create(
            store=self.store, vendor=self.vendor, category=self.sub_category, brand=self.brand,
            name="محصول پرفروش", slug="best-seller-hv", sku="SKU-HV1",
            price=Decimal("100000"), sold_count=500, views_count=10, discount_percent=0,
        )
        self.discounted_product = Product.objects.create(
            store=self.store, vendor=self.vendor, category=self.sub_category, name="محصول تخفیف‌دار",
            slug="discounted-hv", sku="SKU-HV2", price=Decimal("200000"), discount_percent=30,
            sold_count=1, views_count=999,
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

    def test_highlight_product_reuses_discounted_products_result_no_duplicate_query(self):
        """Phase 2 — ``highlight_product`` used to be
        ``discounted_products.first()``, a *separate* lazy evaluation of
        the queryset (its own SQL query, plus its own prefetch_related
        query for images) distinct from the queryset later iterated by the
        template — up to 4 duplicate queries for the same 6 rows on every
        homepage view. Fixed by evaluating ``discounted_products`` once
        into a list and taking its first element. Proven here by object
        identity, not a fragile raw-SQL query count: if the old bug
        reappeared, ``highlight_product`` would be a different Python
        object than ``discounted_products[0]`` even though equal in value."""
        response = self.client.get(reverse("catalog:home"))
        discounted = response.context["discounted_products"]
        self.assertIsInstance(discounted, list)
        self.assertGreater(len(discounted), 0)
        self.assertIs(response.context["highlight_product"], discounted[0])
