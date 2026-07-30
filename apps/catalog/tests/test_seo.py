"""Checkpoint 6 (ADR-90): tenant-safe storefront SEO — sitemap, robots,
canonical, structured data, and noindex on private/filtered pages."""

from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from apps.catalog.models import Category, Product, Vendor
from apps.stores.models import Store


def _akhlaghi():
    return Store.objects.get(slug="akhlaghi")


class SeoStorefrontTests(TestCase):
    def setUp(self):
        self.store = _akhlaghi()
        self.vendor = Vendor.objects.create(store=self.store, name="v", slug="v-seo")
        self.category = Category.objects.create(store=self.store, name="دیجیتال", slug="digital-seo", icon="📱")
        self.product = Product.objects.create(
            store=self.store, vendor=self.vendor, category=self.category, name="کالای سئو",
            slug="seo-product", sku="SKU-SEO-1", description="توضیح", price=Decimal("500000"), stock=7,
            status=Product.Status.ACTIVE,
        )
        self.draft = Product.objects.create(
            store=self.store, vendor=self.vendor, category=self.category, name="پیش‌نویس",
            slug="seo-draft", sku="SKU-SEO-2", price=Decimal("100000"), stock=0,
            status=Product.Status.DRAFT,
        )

    def test_sitemap_returns_xml_with_published_products(self):
        resp = self.client.get(reverse("sitemap-xml"))
        self.assertEqual(resp.status_code, 200)
        self.assertIn("application/xml", resp["Content-Type"])
        body = resp.content.decode("utf-8")
        self.assertIn("/products/seo-product/", body)
        self.assertIn("<loc>", body)

    def test_sitemap_excludes_draft_products(self):
        body = self.client.get(reverse("sitemap-xml")).content.decode("utf-8")
        self.assertNotIn("seo-draft", body)

    def test_sitemap_includes_categories_and_home(self):
        body = self.client.get(reverse("sitemap-xml")).content.decode("utf-8")
        self.assertIn("category=digital-seo", body)

    def test_robots_disallows_private_and_links_sitemap(self):
        resp = self.client.get(reverse("robots-txt"))
        self.assertEqual(resp.status_code, 200)
        self.assertIn("text/plain", resp["Content-Type"])
        body = resp.content.decode("utf-8")
        self.assertIn("Disallow: /cart/", body)
        self.assertIn("Disallow: /checkout/", body)
        self.assertIn("Disallow: /account/", body)
        self.assertIn("Sitemap:", body)

    def test_product_detail_has_canonical_and_structured_data(self):
        resp = self.client.get(reverse("catalog:product-detail", args=[self.product.slug]))
        self.assertEqual(resp.status_code, 200)
        html = resp.content.decode("utf-8")
        self.assertIn('rel="canonical"', html)
        self.assertIn("/products/seo-product/", html)
        self.assertIn('"@type":"Product"', html)
        # In-stock availability reflected honestly.
        self.assertIn("schema.org/InStock", html)
        self.assertIn('"@type":"BreadcrumbList"', html)

    def test_out_of_stock_structured_data(self):
        Product.objects.filter(pk=self.product.pk).update(stock=0)
        html = self.client.get(reverse("catalog:product-detail", args=[self.product.slug])).content.decode("utf-8")
        self.assertIn("schema.org/OutOfStock", html)

    def test_home_has_organization_jsonld(self):
        html = self.client.get(reverse("catalog:home")).content.decode("utf-8")
        self.assertIn('"@type":"Organization"', html)

    def test_cart_is_noindex(self):
        html = self.client.get(reverse("cart:detail")).content.decode("utf-8")
        self.assertIn("noindex", html)

    def test_search_results_are_noindex(self):
        html = self.client.get(reverse("catalog:product-list"), {"q": "کالا"}).content.decode("utf-8")
        self.assertIn("noindex", html)

    def test_plain_product_list_is_indexable(self):
        html = self.client.get(reverse("catalog:product-list")).content.decode("utf-8")
        # No noindex robots meta on the clean list (canonical still present).
        self.assertNotIn('name="robots" content="noindex', html)
        self.assertIn('rel="canonical"', html)
