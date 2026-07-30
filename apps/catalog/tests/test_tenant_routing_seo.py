"""Checkpoint 6 (ADR-83/90): adversarial tenant routing for the SEO surface and
inactive-store handling, plus the branded 403 page. Complements the existing
storefront isolation tests (home/list/detail/search) with sitemap/robots/state
coverage."""

from decimal import Decimal

from django.template.loader import render_to_string
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.catalog.models import Category, Product, Vendor
from apps.content.models import FooterSettings
from apps.core.models import ShopSettings
from apps.stores.models import Store, StoreDomain

HOST_A = "route-a.example.com"
HOST_B = "route-b.example.com"


def _verified_domain(store, hostname):
    return StoreDomain.objects.create(
        store=store, hostname=hostname, is_primary=True,
        verification_status=StoreDomain.VerificationStatus.VERIFIED, verified_at=timezone.now(),
    )


@override_settings(ALLOWED_HOSTS=[HOST_A, HOST_B, "testserver"])
class TenantRoutingSeoTests(TestCase):
    def setUp(self):
        self.store_a = Store.objects.get(slug="akhlaghi")
        self.store_b = Store.objects.create(name="Store B", slug="route-store-b", status=Store.Status.ACTIVE)
        _verified_domain(self.store_a, HOST_A)
        _verified_domain(self.store_b, HOST_B)
        ShopSettings.provision_for(self.store_b)
        FooterSettings.provision_for(self.store_b)

        self.vendor_a = Vendor.objects.create(store=self.store_a, name="VA", slug="v-route-a")
        self.cat_a = Category.objects.create(store=self.store_a, name="CatA", slug="cat-route-a", is_active=True)
        self.product_a = Product.objects.create(
            store=self.store_a, vendor=self.vendor_a, category=self.cat_a, name="Product A Only",
            slug="product-route-a", sku="SKU-RT-A", price=Decimal("100000"), status=Product.Status.ACTIVE,
        )
        self.vendor_b = Vendor.objects.create(store=self.store_b, name="VB", slug="v-route-b")
        self.cat_b = Category.objects.create(store=self.store_b, name="CatB", slug="cat-route-b", is_active=True)
        self.product_b = Product.objects.create(
            store=self.store_b, vendor=self.vendor_b, category=self.cat_b, name="Product B Only",
            slug="product-route-b", sku="SKU-RT-B", price=Decimal("200000"), status=Product.Status.ACTIVE,
        )

    def test_sitemap_is_store_scoped(self):
        body_a = self.client.get(reverse("sitemap-xml"), HTTP_HOST=HOST_A).content.decode("utf-8")
        self.assertIn("product-route-a", body_a)
        self.assertNotIn("product-route-b", body_a)
        body_b = self.client.get(reverse("sitemap-xml"), HTTP_HOST=HOST_B).content.decode("utf-8")
        self.assertIn("product-route-b", body_b)
        self.assertNotIn("product-route-a", body_b)

    def test_sitemap_uses_request_host_for_canonical_domain(self):
        body_a = self.client.get(reverse("sitemap-xml"), HTTP_HOST=HOST_A).content.decode("utf-8")
        self.assertIn(HOST_A, body_a)
        self.assertNotIn(HOST_B, body_a)

    def test_robots_links_same_host_sitemap(self):
        body_a = self.client.get(reverse("robots-txt"), HTTP_HOST=HOST_A).content.decode("utf-8")
        self.assertIn(f"Sitemap: http://{HOST_A}/sitemap.xml", body_a)

    def test_cross_store_product_detail_404(self):
        # Product B must not be reachable on Store A's host.
        resp = self.client.get(
            reverse("catalog:product-detail", args=["product-route-b"]), HTTP_HOST=HOST_A,
        )
        self.assertEqual(resp.status_code, 404)

    def test_inactive_store_storefront_404(self):
        # An inactive store's host must not resolve to a storefront.
        self.store_b.status = Store.Status.SUSPENDED
        self.store_b.save(update_fields=["status"])
        resp = self.client.get(reverse("catalog:home"), HTTP_HOST=HOST_B)
        self.assertEqual(resp.status_code, 404)

    def test_403_template_renders_branded(self):
        request = self.client.get(reverse("catalog:home"), HTTP_HOST=HOST_A).wsgi_request
        html = render_to_string("403.html", request=request)
        self.assertIn("۴۰۳", html)
        self.assertIn("noindex", html)
