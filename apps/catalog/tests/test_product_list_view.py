from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from apps.catalog.models import Brand, Category, Product


class ProductListViewTests(TestCase):
    def setUp(self):
        self.top_category = Category.objects.create(name="لوازم خانگی", slug="home-plp", icon="🏠")
        self.sub_category = Category.objects.create(
            name="آشپزخانه", slug="kitchen-plp", icon="🍳", parent=self.top_category
        )
        self.other_top = Category.objects.create(name="دیجیتال", slug="digital-plp", icon="📱")
        self.other_sub = Category.objects.create(
            name="موبایل", slug="mobile-plp", icon="📱", parent=self.other_top
        )

        self.vendor = self._make_vendor()
        self.brand_a = Brand.objects.create(name="پارس خزر", slug="pars-khazar-plp")
        self.brand_b = Brand.objects.create(name="شیائومی", slug="xiaomi-plp")

        self.rice_cooker = Product.objects.create(
            vendor=self.vendor, category=self.sub_category, brand=self.brand_a,
            name="پلوپز پارس خزر", slug="rice-cooker-plp", sku="SKU-PLP1",
            price=Decimal("3000000"), discount_percent=0, sold_count=10, rating=Decimal("4.0"),
        )
        self.phone = Product.objects.create(
            vendor=self.vendor, category=self.other_sub, brand=self.brand_b,
            name="گوشی شیائومی", slug="phone-plp", sku="SKU-PLP2",
            price=Decimal("10000000"), discount_percent=15, sold_count=50, rating=Decimal("4.8"),
        )
        self.cheap_pen = Product.objects.create(
            vendor=self.vendor, category=self.sub_category, brand=None,
            name="خودکار ارزان", slug="pen-plp", sku="SKU-PLP3",
            price=Decimal("50000"), discount_percent=0, sold_count=1, rating=Decimal("3.0"),
        )

    def _make_vendor(self):
        from apps.catalog.models import Vendor

        return Vendor.objects.create(name="فروشگاه", slug="shop-plp")

    def test_list_returns_all_active_products_by_default(self):
        response = self.client.get(reverse("catalog:product-list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "پلوپز پارس خزر")
        self.assertContains(response, "گوشی شیائومی")
        self.assertContains(response, "خودکار ارزان")

    def test_filter_by_subcategory(self):
        response = self.client.get(reverse("catalog:product-list"), {"category": "kitchen-plp"})
        self.assertContains(response, "پلوپز پارس خزر")
        self.assertNotContains(response, "گوشی شیائومی")

    def test_filter_by_top_level_category_includes_children(self):
        response = self.client.get(reverse("catalog:product-list"), {"category": "home-plp"})
        self.assertContains(response, "پلوپز پارس خزر")
        self.assertContains(response, "خودکار ارزان")
        self.assertNotContains(response, "گوشی شیائومی")

    def test_filter_by_brand(self):
        response = self.client.get(reverse("catalog:product-list"), {"brand": "xiaomi-plp"})
        self.assertContains(response, "گوشی شیائومی")
        self.assertNotContains(response, "پلوپز پارس خزر")

    def test_filter_by_price_range(self):
        response = self.client.get(reverse("catalog:product-list"), {"min_price": "1000000", "max_price": "5000000"})
        self.assertContains(response, "پلوپز پارس خزر")
        self.assertNotContains(response, "گوشی شیائومی")
        self.assertNotContains(response, "خودکار ارزان")

    def test_filter_discounted_only(self):
        response = self.client.get(reverse("catalog:product-list"), {"discounted": "1"})
        self.assertContains(response, "گوشی شیائومی")
        self.assertNotContains(response, "پلوپز پارس خزر")

    def test_search_matches_product_name(self):
        response = self.client.get(reverse("catalog:product-list"), {"q": "پلوپز"})
        self.assertContains(response, "پلوپز پارس خزر")
        self.assertNotContains(response, "گوشی شیائومی")

    def test_search_matches_brand_name(self):
        response = self.client.get(reverse("catalog:product-list"), {"q": "شیائومی"})
        self.assertContains(response, "گوشی شیائومی")
        self.assertNotContains(response, "پلوپز پارس خزر")

    def test_search_matches_category_name(self):
        response = self.client.get(reverse("catalog:product-list"), {"q": "آشپزخانه"})
        self.assertContains(response, "پلوپز پارس خزر")
        self.assertNotContains(response, "گوشی شیائومی")

    def test_sort_price_ascending(self):
        response = self.client.get(reverse("catalog:product-list"), {"sort": "price_asc"})
        content = response.content.decode()
        self.assertLess(content.index("خودکار ارزان"), content.index("پلوپز پارس خزر"))
        self.assertLess(content.index("پلوپز پارس خزر"), content.index("گوشی شیائومی"))

    def test_pagination_respects_page_size(self):
        vendor = self.vendor
        for i in range(15):
            Product.objects.create(
                vendor=vendor, category=self.sub_category, name=f"کالای اضافه {i}",
                slug=f"extra-plp-{i}", sku=f"SKU-EXTRA-{i}", price=Decimal("10000"),
            )
        response = self.client.get(reverse("catalog:product-list"))
        self.assertEqual(len(response.context["products"]), 12)
        self.assertTrue(response.context["page_obj"].has_next())

    def test_out_of_range_page_returns_last_page(self):
        response = self.client.get(reverse("catalog:product-list"), {"page": "999"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["page_obj"].number, response.context["page_obj"].paginator.num_pages)

    def test_no_results_shows_empty_state(self):
        response = self.client.get(reverse("catalog:product-list"), {"q": "چیزی-که-وجود-ندارد"})
        self.assertContains(response, "کالایی یافت نشد")

    def test_htmx_request_returns_partial_without_layout(self):
        response = self.client.get(reverse("catalog:product-list"), HTTP_HX_REQUEST="true")
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "<header")
        self.assertContains(response, "پلوپز پارس خزر")

    def test_normal_request_returns_full_layout(self):
        response = self.client.get(reverse("catalog:product-list"))
        self.assertContains(response, "<header")
        self.assertContains(response, "دسته‌بندی کالاها")
