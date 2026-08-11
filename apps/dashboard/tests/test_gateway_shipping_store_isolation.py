"""PaymentGateway/ShippingMethod cross-Store adversarial tests (PR23).

Both models now have a direct, required Store FK (previously global,
platform-wide config with no ownership at all). These tests prove:
dashboard settings only lists/toggles the current Store's own
gateways/shipping methods, and a crafted storefront checkout POST can never
select another Store's shipping method or payment gateway.
"""

from decimal import Decimal

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.catalog.models import Category, Product, Vendor
from apps.content.models import FooterSettings
from apps.core.models import ShopSettings
from apps.orders.models import PaymentGateway, ShippingMethod
from apps.orders.services import checkout_service
from apps.stores.models import Store, StoreDomain, StoreMembership

User = get_user_model()

HOST_A = f"dgs-a.{settings.RASTISI_ADMIN_DOMAIN_SUFFIX}"
HOST_B = f"dgs-b.{settings.RASTISI_ADMIN_DOMAIN_SUFFIX}"


def _verified_domain(store, hostname):
    return StoreDomain.objects.create(
        store=store, hostname=hostname, is_primary=True,
        verification_status=StoreDomain.VerificationStatus.VERIFIED, verified_at=timezone.now(),
    )


@override_settings(ALLOWED_HOSTS=[HOST_A, HOST_B, "testserver"])
class DashboardGatewayShippingTwoStoreIsolationTests(TestCase):
    def setUp(self):
        self.store_a = Store.objects.get(slug="akhlaghi")
        self.store_b = Store.objects.create(
            name="Store B", slug="dgs-store-b", status=Store.Status.ACTIVE,
            admin_subdomain=HOST_B.split(".")[0],
        )
        _verified_domain(self.store_a, HOST_A)
        _verified_domain(self.store_b, HOST_B)
        ShopSettings.provision_for(self.store_b)
        FooterSettings.provision_for(self.store_b)

        self.staff = User.objects.create_user(username="dgs-staff", password="pass12345", is_staff=True)
        StoreMembership.objects.create(
            store=self.store_b, user=self.staff, role=StoreMembership.Role.OWNER,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )
        self.client.login(username="dgs-staff", password="pass12345")

        self.gateway_a = PaymentGateway.objects.create(store=self.store_a, name="درگاه A", slug="gw-dgs-a", is_active=True)
        self.gateway_b = PaymentGateway.objects.create(store=self.store_b, name="درگاه B", slug="gw-dgs-b", is_active=True)
        self.shipping_a = ShippingMethod.objects.create(store=self.store_a, name="پست A", slug="post-dgs-a", cost=Decimal("10000"), is_active=True)
        self.shipping_b = ShippingMethod.objects.create(store=self.store_b, name="پست B", slug="post-dgs-b", cost=Decimal("20000"), is_active=True)

    def test_settings_page_lists_only_own_store_gateways(self):
        response = self.client.get(reverse("dashboard:settings"), {"section": "delivery-payment"}, HTTP_HOST=HOST_B)
        self.assertContains(response, "درگاه B")
        self.assertNotContains(response, "درگاه A")

    def test_settings_page_lists_only_own_store_shipping_methods(self):
        response = self.client.get(reverse("dashboard:settings"), {"section": "delivery-payment"}, HTTP_HOST=HOST_B)
        self.assertContains(response, "پست B")
        self.assertNotContains(response, "پست A")

    def test_cannot_toggle_other_stores_gateway(self):
        response = self.client.post(
            reverse("dashboard:settings-gateway-toggle", args=[self.gateway_a.pk]), HTTP_HOST=HOST_B
        )
        self.assertEqual(response.status_code, 404)
        self.gateway_a.refresh_from_db()
        self.assertTrue(self.gateway_a.is_active)

    def test_cannot_toggle_other_stores_shipping_method(self):
        response = self.client.post(
            reverse("dashboard:settings-shipping-toggle", args=[self.shipping_a.pk]), HTTP_HOST=HOST_B
        )
        self.assertEqual(response.status_code, 404)
        self.shipping_a.refresh_from_db()
        self.assertTrue(self.shipping_a.is_active)

    def test_can_toggle_own_stores_gateway(self):
        response = self.client.post(
            reverse("dashboard:settings-gateway-toggle", args=[self.gateway_b.pk]), HTTP_HOST=HOST_B
        )
        self.assertEqual(response.status_code, 204)
        self.gateway_b.refresh_from_db()
        self.assertFalse(self.gateway_b.is_active)


@override_settings(ALLOWED_HOSTS=[HOST_A, HOST_B, "testserver"])
class CheckoutRejectsOtherStoreShippingAndGatewayTests(TestCase):
    """A crafted POST to the storefront checkout must never select another
    Store's shipping method or payment gateway — the option pool itself is
    always filtered to the current Store, so an out-of-Store id is simply
    not found and ignored (same safe behavior as an unknown/inactive id)."""

    def setUp(self):
        self.store_a = Store.objects.get(slug="akhlaghi")
        self.store_b = Store.objects.create(name="Store B", slug="dgs-chk-store-b", status=Store.Status.ACTIVE)
        _verified_domain(self.store_a, HOST_A)
        _verified_domain(self.store_b, HOST_B)
        ShopSettings.provision_for(self.store_b)
        FooterSettings.provision_for(self.store_b)

        self.vendor_b = Vendor.objects.create(store=self.store_b, name="Vendor B", slug="vendor-dgschk-b")
        self.category_b = Category.objects.create(store=self.store_b, name="Cat B", slug="cat-dgschk-b")
        self.product_b = Product.objects.create(
            store=self.store_b, vendor=self.vendor_b, category=self.category_b,
            name="Product B", slug="product-dgschk-b", sku="SKU-DGSCHK-B",
            price=Decimal("100000"), stock=10, status=Product.Status.ACTIVE,
        )
        self.shipping_a = ShippingMethod.objects.create(store=self.store_a, name="پست A", slug="post-dgschk-a", cost=Decimal("10000"))
        self.gateway_a = PaymentGateway.objects.create(store=self.store_a, name="درگاه A", slug="gw-dgschk-a")
        self.shipping_b = ShippingMethod.objects.create(store=self.store_b, name="پست B", slug="post-dgschk-b", cost=Decimal("30000"))
        self.gateway_b = PaymentGateway.objects.create(store=self.store_b, name="درگاه B", slug="gw-dgschk-b")

    def test_set_shipping_method_ignores_other_stores_id(self):
        self.client.post(reverse("cart:add", args=[self.product_b.slug]), {"quantity": 1}, HTTP_HOST=HOST_B)
        self.client.post(
            reverse("orders:checkout-set-shipping", args=[self.shipping_a.pk]), HTTP_HOST=HOST_B
        )
        response = self.client.get(reverse("orders:checkout-step1"), HTTP_HOST=HOST_B)
        selected = response.context["totals"]
        # Store A's shipping is more expensive-labeled but the point is it
        # must never be attached — the still-selected method must be
        # Store B's own (its cost, not Store A's).
        self.assertEqual(selected["shipping_cost"], Decimal("30000"))

    def test_set_payment_gateway_ignores_other_stores_id(self):
        self.client.post(reverse("cart:add", args=[self.product_b.slug]), {"quantity": 1}, HTTP_HOST=HOST_B)
        self.client.post(
            reverse("orders:checkout-set-payment", args=[self.gateway_a.pk]), HTTP_HOST=HOST_B
        )
        response = self.client.get(reverse("orders:checkout-step1"), HTTP_HOST=HOST_B)
        selected_rows = [row for row in response.context["payment_rows"] if row["selected"]]
        self.assertEqual(len(selected_rows), 1)
        self.assertEqual(selected_rows[0]["gateway"], self.gateway_b)

    def test_active_shipping_methods_service_is_store_specific(self):
        self.assertEqual(
            list(checkout_service.active_shipping_methods(store=self.store_b)), [self.shipping_b]
        )

    def test_active_payment_gateways_service_is_store_specific(self):
        self.assertEqual(
            list(checkout_service.active_payment_gateways(store=self.store_b)), [self.gateway_b]
        )
