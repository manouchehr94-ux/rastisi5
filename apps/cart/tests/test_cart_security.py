"""Checkpoint 6 (ADR-85, §13/§30): server-side validation on Add-to-Cart —
cross-store product/variant ids, cross-product variant, inactive variant,
unpublished product, and forged POST price are all rejected or ignored."""

from decimal import Decimal

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.cart.models import CartItem
from apps.catalog.models import Category, Product, ProductVariant, Vendor
from apps.content.models import FooterSettings
from apps.core.models import ShopSettings
from apps.stores.models import Store, StoreDomain

HOST_A = "cartsec-a.example.com"
HOST_B = "cartsec-b.example.com"


def _verified_domain(store, hostname):
    return StoreDomain.objects.create(
        store=store, hostname=hostname, is_primary=True,
        verification_status=StoreDomain.VerificationStatus.VERIFIED, verified_at=timezone.now(),
    )


@override_settings(ALLOWED_HOSTS=[HOST_A, HOST_B, "testserver"])
class CartAddSecurityTests(TestCase):
    def setUp(self):
        self.store_a = Store.objects.get(slug="akhlaghi")
        self.store_b = Store.objects.create(name="B", slug="cartsec-b", status=Store.Status.ACTIVE)
        _verified_domain(self.store_a, HOST_A)
        _verified_domain(self.store_b, HOST_B)
        ShopSettings.provision_for(self.store_b)
        FooterSettings.provision_for(self.store_b)

        self.vendor_a = Vendor.objects.create(store=self.store_a, name="VA", slug="v-cs-a")
        self.cat_a = Category.objects.create(store=self.store_a, name="CA", slug="c-cs-a")
        self.product_a = Product.objects.create(
            store=self.store_a, vendor=self.vendor_a, category=self.cat_a, name="A Phone",
            slug="cs-a-phone", sku="SKU-CS-A", price=Decimal("1000000"), discount_percent=10, stock=20,
            status=Product.Status.ACTIVE,
        )
        self.other_product_a = Product.objects.create(
            store=self.store_a, vendor=self.vendor_a, category=self.cat_a, name="A Tablet",
            slug="cs-a-tablet", sku="SKU-CS-A2", price=Decimal("500000"), stock=5, status=Product.Status.ACTIVE,
        )
        self.active_variant = ProductVariant.objects.create(
            product=self.product_a, store=self.store_a, attribute="رنگ", value="مشکی", stock=5, is_active=True,
        )
        self.inactive_variant = ProductVariant.objects.create(
            product=self.product_a, store=self.store_a, attribute="رنگ", value="سفید", stock=5, is_active=False,
        )
        self.other_product_variant = ProductVariant.objects.create(
            product=self.other_product_a, store=self.store_a, attribute="رنگ", value="طلایی", stock=5,
        )
        self.draft_a = Product.objects.create(
            store=self.store_a, vendor=self.vendor_a, category=self.cat_a, name="Draft",
            slug="cs-a-draft", sku="SKU-CS-A3", price=Decimal("1"), stock=1, status=Product.Status.DRAFT,
        )
        # Store B product + variant (foreign).
        self.vendor_b = Vendor.objects.create(store=self.store_b, name="VB", slug="v-cs-b")
        self.cat_b = Category.objects.create(store=self.store_b, name="CB", slug="c-cs-b")
        self.product_b = Product.objects.create(
            store=self.store_b, vendor=self.vendor_b, category=self.cat_b, name="B Phone",
            slug="cs-b-phone", sku="SKU-CS-B", price=Decimal("2000000"), stock=5, status=Product.Status.ACTIVE,
        )
        self.variant_b = ProductVariant.objects.create(
            product=self.product_b, store=self.store_b, attribute="رنگ", value="آبی", stock=5,
        )

    def _add(self, slug, host=HOST_A, **post):
        return self.client.post(reverse("cart:add", args=[slug]), post, HTTP_HOST=host)

    def test_add_valid_variant_succeeds(self):
        resp = self._add("cs-a-phone", variant_id=self.active_variant.pk, quantity=2)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(CartItem.objects.count(), 1)

    def test_forged_price_is_ignored(self):
        self._add("cs-a-phone", variant_id=self.active_variant.pk, quantity=1, unit_price="1", price="1")
        item = CartItem.objects.get()
        # Server resolves price from the product (final_price after discount), never POST.
        self.assertEqual(item.unit_price, self.product_a.final_price)
        self.assertNotEqual(item.unit_price, Decimal("1"))

    def test_inactive_variant_rejected(self):
        resp = self._add("cs-a-phone", variant_id=self.inactive_variant.pk)
        self.assertEqual(resp.status_code, 404)
        self.assertEqual(CartItem.objects.count(), 0)

    def test_variant_of_another_product_rejected(self):
        resp = self._add("cs-a-phone", variant_id=self.other_product_variant.pk)
        self.assertEqual(resp.status_code, 404)

    def test_cross_store_variant_rejected(self):
        # Variant from Store B against Store A product must 404.
        resp = self._add("cs-a-phone", variant_id=self.variant_b.pk)
        self.assertEqual(resp.status_code, 404)

    def test_cross_store_product_rejected(self):
        # Store B product slug on Store A host must 404.
        resp = self._add("cs-b-phone", host=HOST_A)
        self.assertEqual(resp.status_code, 404)

    def test_unpublished_product_rejected(self):
        resp = self._add("cs-a-draft")
        self.assertEqual(resp.status_code, 404)

    def test_negative_quantity_clamped(self):
        self._add("cs-a-phone", variant_id=self.active_variant.pk, quantity=-5)
        item = CartItem.objects.get()
        self.assertGreaterEqual(item.quantity, 1)
