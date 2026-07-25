"""Cross-Store isolation for wishlist_toggle — found during PR21 self-review.

``apps.customers.views.wishlist_toggle`` looked up ``Product`` by slug with
no Store scoping, meaning a logged-in customer browsing Store A could add
Store B's product to their wishlist by slug. Fixed by scoping the lookup
through ``resolve_store_for_service(request)``, the same pattern already
used everywhere else in this codebase. This test uses two real Store rows
with real, verified StoreDomains and distinct Host headers — no
``request.store`` mocking.
"""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.catalog.models import Category, Product, Vendor
from apps.content.models import FooterSettings
from apps.core.models import ShopSettings
from apps.customers.models import Customer, Wishlist
from apps.stores.models import Store, StoreDomain

User = get_user_model()

HOST_A = "wish-a.example.com"
HOST_B = "wish-b.example.com"


def _verified_domain(store, hostname):
    return StoreDomain.objects.create(
        store=store,
        hostname=hostname,
        is_primary=True,
        verification_status=StoreDomain.VerificationStatus.VERIFIED,
        verified_at=timezone.now(),
    )


@override_settings(ALLOWED_HOSTS=[HOST_A, HOST_B, "testserver"])
class WishlistToggleCrossStoreTests(TestCase):
    def setUp(self):
        self.store_a = Store.objects.get(slug="akhlaghi")
        self.store_b = Store.objects.create(name="Store B", slug="wish-store-b", status=Store.Status.ACTIVE)
        _verified_domain(self.store_a, HOST_A)
        _verified_domain(self.store_b, HOST_B)
        ShopSettings.provision_for(self.store_b)
        FooterSettings.provision_for(self.store_b)

        vendor_a = Vendor.objects.create(store=self.store_a, name="Vendor A", slug="vendor-wish-a")
        category_a = Category.objects.create(store=self.store_a, name="Cat A", slug="cat-wish-a")
        self.product_a = Product.objects.create(
            store=self.store_a, vendor=vendor_a, category=category_a,
            name="Product A", slug="product-wish-a", sku="SKU-WISH-A",
            price=Decimal("100000"), status=Product.Status.ACTIVE,
        )

        vendor_b = Vendor.objects.create(store=self.store_b, name="Vendor B", slug="vendor-wish-b")
        category_b = Category.objects.create(store=self.store_b, name="Cat B", slug="cat-wish-b")
        self.product_b = Product.objects.create(
            store=self.store_b, vendor=vendor_b, category=category_b,
            name="Product B", slug="product-wish-b", sku="SKU-WISH-B",
            price=Decimal("200000"), status=Product.Status.ACTIVE,
        )

        user = User.objects.create_user(username="wish-user", password="pass12345")
        self.customer = Customer.objects.create(user=user, full_name="مشتری", phone="09121110088")
        self.client.login(username="wish-user", password="pass12345")

    def test_wishlist_toggle_own_store_product_succeeds(self):
        response = self.client.post(
            reverse("customers:wishlist-toggle", args=[self.product_a.slug]), HTTP_HOST=HOST_A
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(Wishlist.objects.filter(customer=self.customer, product=self.product_a).exists())

    def test_wishlist_toggle_other_stores_product_slug_returns_404(self):
        response = self.client.post(
            reverse("customers:wishlist-toggle", args=[self.product_b.slug]), HTTP_HOST=HOST_A
        )
        self.assertEqual(response.status_code, 404)
        self.assertEqual(Wishlist.objects.count(), 0)

    def test_wishlist_toggle_other_stores_product_slug_returns_404_reverse_direction(self):
        response = self.client.post(
            reverse("customers:wishlist-toggle", args=[self.product_a.slug]), HTTP_HOST=HOST_B
        )
        self.assertEqual(response.status_code, 404)
        self.assertEqual(Wishlist.objects.count(), 0)
