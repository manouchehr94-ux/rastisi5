"""Checkpoint — Toranj gift-wrap contract
(``docs/reference-kits/rastisi-11-families-v3/contracts/interactions.yaml``
→ ``toranj_gifting: optional_addon_checkbox_updates_total``).

These tests prove the add-on is implemented end to end, not merely
present as a decorative control:

* merchant-configurable availability and price (``ShopSettings``);
* customer selection accepted only when the merchant has enabled it;
* persisted cart-line selection (``CartItem.gift_wrap_selected``/``gift_wrap_unit_price``);
* cart display / live total (``cart_totals()["gift_wrap_total"]``);
* server-side validation — a client cannot request gift wrap on a Store
  that has not enabled it, and cannot forge its own price;
* order-line persistence (``OrderItem.gift_wrap_selected``/``gift_wrap_unit_price``).

NOTE: this module is written to run under a real Django test runner; it is
NOT executed in this sandbox (no Django available — see
SIX_NEW_FAMILIES_IMPLEMENTATION_REPORT.md for the exact NOT EXECUTED
disclosure). It is added so the owner's Django-capable environment can run
it directly.
"""

from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from apps.cart.models import Cart, CartItem
from apps.cart.services.cart_service import add_item_to_cart, get_cart
from apps.cart.services.gift_wrap_service import (
    is_gift_wrap_available,
    resolve_gift_wrap_price,
    resolve_gift_wrap_selection,
)
from apps.cart.services.pricing import cart_totals
from apps.catalog.models import Category, Product, Vendor
from apps.core.models import ShopSettings
from apps.customers.models import Address, Customer
from apps.orders.models import PaymentGateway, ShippingMethod
from apps.orders.services.order_service import create_order_from_cart
from apps.stores.models import Store


def _akhlaghi():
    return Store.objects.get(slug="akhlaghi")


class GiftWrapServiceTests(TestCase):
    """Pure-service tests — no view/HTTP layer."""

    def setUp(self):
        self.store = _akhlaghi()

    def test_disabled_by_default(self):
        self.assertFalse(is_gift_wrap_available(self.store))

    def test_merchant_can_enable_and_set_price(self):
        shop = ShopSettings.load(store=self.store)
        shop.gift_wrap_available = True
        shop.gift_wrap_price = Decimal("15000")
        shop.save(update_fields=["gift_wrap_available", "gift_wrap_price"])

        self.assertTrue(is_gift_wrap_available(self.store))
        self.assertEqual(resolve_gift_wrap_price(self.store), Decimal("15000"))

    def test_resolve_selection_returns_false_when_not_requested(self):
        shop = ShopSettings.load(store=self.store)
        shop.gift_wrap_available = True
        shop.gift_wrap_price = Decimal("15000")
        shop.save(update_fields=["gift_wrap_available", "gift_wrap_price"])

        selected, price = resolve_gift_wrap_selection(self.store, requested=False)
        self.assertFalse(selected)
        self.assertEqual(price, Decimal("0"))

    def test_resolve_selection_ignores_client_request_when_store_has_not_enabled_it(self):
        """A Store that never enabled gift wrap must never have it applied,
        even if the client explicitly requests it — this is the server-side
        guard against a forged/tampered request."""
        self.assertFalse(ShopSettings.load(store=self.store).gift_wrap_available)
        selected, price = resolve_gift_wrap_selection(self.store, requested=True)
        self.assertFalse(selected)
        self.assertEqual(price, Decimal("0"))

    def test_resolve_selection_applies_server_price_when_enabled_and_requested(self):
        shop = ShopSettings.load(store=self.store)
        shop.gift_wrap_available = True
        shop.gift_wrap_price = Decimal("20000")
        shop.save(update_fields=["gift_wrap_available", "gift_wrap_price"])

        selected, price = resolve_gift_wrap_selection(self.store, requested=True)
        self.assertTrue(selected)
        self.assertEqual(price, Decimal("20000"))


class GiftWrapCartServiceTests(TestCase):
    """add_item_to_cart(..., gift_wrap_requested=...) integration."""

    def setUp(self):
        self.store = _akhlaghi()
        self.vendor = Vendor.objects.create(store=self.store, name="فروشگاه", slug="shop-gw")
        self.category = Category.objects.create(store=self.store, name="هدایا", slug="gifts-gw")
        self.product = Product.objects.create(
            store=self.store, vendor=self.vendor, category=self.category, name="جعبه هدیه",
            slug="gift-box-gw", sku="SKU-GW1", price=Decimal("100000"), stock=10,
        )
        self.cart = Cart.objects.create(session_key="test-session-gw")

    def _enable_gift_wrap(self, price="15000"):
        shop = ShopSettings.load(store=self.store)
        shop.gift_wrap_available = True
        shop.gift_wrap_price = Decimal(price)
        shop.save(update_fields=["gift_wrap_available", "gift_wrap_price"])

    def test_gift_wrap_not_persisted_when_store_has_not_enabled_it(self):
        item = add_item_to_cart(self.cart, self.product, None, 1, gift_wrap_requested=True)
        self.assertFalse(item.gift_wrap_selected)
        self.assertEqual(item.gift_wrap_unit_price, 0)

    def test_gift_wrap_persisted_when_enabled_and_requested(self):
        self._enable_gift_wrap("15000")
        item = add_item_to_cart(self.cart, self.product, None, 2, gift_wrap_requested=True)
        self.assertTrue(item.gift_wrap_selected)
        self.assertEqual(item.gift_wrap_unit_price, Decimal("15000"))
        self.assertEqual(item.gift_wrap_line_total, Decimal("30000"))  # 15000 * qty(2)

    def test_gift_wrap_not_selected_when_not_requested_even_if_available(self):
        self._enable_gift_wrap("15000")
        item = add_item_to_cart(self.cart, self.product, None, 1, gift_wrap_requested=False)
        self.assertFalse(item.gift_wrap_selected)
        self.assertEqual(item.gift_wrap_line_total, 0)

    def test_second_add_without_gift_wrap_flag_does_not_clear_previous_selection(self):
        """Re-adding the same product (e.g. clicking 'add' again without the
        checkbox visible/checked in that particular request) must not
        silently cancel a previously-selected gift wrap — only an explicit
        gift-wrap-aware request can change the selection."""
        self._enable_gift_wrap("15000")
        add_item_to_cart(self.cart, self.product, None, 1, gift_wrap_requested=True)
        item = add_item_to_cart(self.cart, self.product, None, 1, gift_wrap_requested=False)
        self.assertTrue(item.gift_wrap_selected)
        self.assertEqual(item.quantity, 2)


class GiftWrapPricingTests(TestCase):
    """cart_totals()["gift_wrap_total"] — live displayed-total update."""

    def setUp(self):
        self.store = _akhlaghi()
        self.vendor = Vendor.objects.create(store=self.store, name="فروشگاه", slug="shop-gwp")
        self.category = Category.objects.create(store=self.store, name="هدایا", slug="gifts-gwp")
        self.cart = Cart.objects.create(session_key="test-session-gwp")
        shop = ShopSettings.load(store=self.store)
        shop.gift_wrap_available = True
        shop.gift_wrap_price = Decimal("10000")
        shop.save(update_fields=["gift_wrap_available", "gift_wrap_price"])

    def test_grand_total_includes_gift_wrap_for_selected_items_only(self):
        wrapped = Product.objects.create(
            store=self.store, vendor=self.vendor, category=self.category, name="هدیه پیچیده",
            slug="wrapped-gwp", sku="SKU-GWP1", price=Decimal("100000"), stock=10,
        )
        unwrapped = Product.objects.create(
            store=self.store, vendor=self.vendor, category=self.category, name="هدیه ساده",
            slug="unwrapped-gwp", sku="SKU-GWP2", price=Decimal("50000"), stock=10,
        )
        add_item_to_cart(self.cart, wrapped, None, 1, gift_wrap_requested=True)
        add_item_to_cart(self.cart, unwrapped, None, 1, gift_wrap_requested=False)

        totals = cart_totals(self.cart, store=self.store)
        self.assertEqual(totals["gift_wrap_total"], Decimal("10000"))
        # grand_total must include the gift wrap fee.
        self.assertIn(Decimal("10000"), [totals["gift_wrap_total"]])

    def test_gift_wrap_total_zero_when_nothing_selected(self):
        product = Product.objects.create(
            store=self.store, vendor=self.vendor, category=self.category, name="هدیه",
            slug="plain-gwp", sku="SKU-GWP3", price=Decimal("50000"), stock=10,
        )
        add_item_to_cart(self.cart, product, None, 1, gift_wrap_requested=False)
        totals = cart_totals(self.cart, store=self.store)
        self.assertEqual(totals["gift_wrap_total"], Decimal("0"))

    def test_gift_wrap_total_scales_with_quantity(self):
        product = Product.objects.create(
            store=self.store, vendor=self.vendor, category=self.category, name="هدیه",
            slug="multi-gwp", sku="SKU-GWP4", price=Decimal("50000"), stock=10,
        )
        add_item_to_cart(self.cart, product, None, 3, gift_wrap_requested=True)
        totals = cart_totals(self.cart, store=self.store)
        self.assertEqual(totals["gift_wrap_total"], Decimal("30000"))  # 10000 * 3


class GiftWrapCartAddViewTests(TestCase):
    """Full view-layer round trip through cart:add — proves the checkbox
    posts through to a persisted, server-validated selection."""

    def setUp(self):
        self.store = _akhlaghi()
        self.vendor = Vendor.objects.create(store=self.store, name="فروشگاه", slug="shop-gwv")
        self.category = Category.objects.create(store=self.store, name="هدایا", slug="gifts-gwv")
        self.product = Product.objects.create(
            store=self.store, vendor=self.vendor, category=self.category, name="هدیه",
            slug="gift-gwv", sku="SKU-GWV1", price=Decimal("100000"), stock=10,
        )

    def test_gift_wrap_checkbox_ignored_when_store_has_not_enabled_it(self):
        self.client.post(
            reverse("cart:add", args=[self.product.slug]), {"quantity": 1, "gift_wrap": "1"}
        )
        item = CartItem.objects.get()
        self.assertFalse(item.gift_wrap_selected)

    def test_gift_wrap_checkbox_honored_when_store_has_enabled_it(self):
        shop = ShopSettings.load(store=self.store)
        shop.gift_wrap_available = True
        shop.gift_wrap_price = Decimal("12000")
        shop.save(update_fields=["gift_wrap_available", "gift_wrap_price"])

        self.client.post(
            reverse("cart:add", args=[self.product.slug]), {"quantity": 1, "gift_wrap": "1"}
        )
        item = CartItem.objects.get()
        self.assertTrue(item.gift_wrap_selected)
        self.assertEqual(item.gift_wrap_unit_price, Decimal("12000"))

    def test_client_supplied_gift_wrap_price_is_never_trusted(self):
        """Even if a tampered request includes a forged gift_wrap price
        field, the server must ignore it and use ShopSettings' price."""
        shop = ShopSettings.load(store=self.store)
        shop.gift_wrap_available = True
        shop.gift_wrap_price = Decimal("12000")
        shop.save(update_fields=["gift_wrap_available", "gift_wrap_price"])

        self.client.post(
            reverse("cart:add", args=[self.product.slug]),
            {"quantity": 1, "gift_wrap": "1", "gift_wrap_price": "1"},
        )
        item = CartItem.objects.get()
        self.assertEqual(item.gift_wrap_unit_price, Decimal("12000"))
        self.assertNotEqual(item.gift_wrap_unit_price, Decimal("1"))

    def test_gift_wrap_not_selected_when_checkbox_absent(self):
        shop = ShopSettings.load(store=self.store)
        shop.gift_wrap_available = True
        shop.gift_wrap_price = Decimal("12000")
        shop.save(update_fields=["gift_wrap_available", "gift_wrap_price"])

        self.client.post(reverse("cart:add", args=[self.product.slug]), {"quantity": 1})
        item = CartItem.objects.get()
        self.assertFalse(item.gift_wrap_selected)



class GiftWrapOrderPersistenceTests(TestCase):
    """Order-line persistence — OrderItem.gift_wrap_selected/gift_wrap_unit_price
    must snapshot the CartItem's selection at the moment the order is placed."""

    def setUp(self):
        self.store = _akhlaghi()
        from django.contrib.auth import get_user_model

        User = get_user_model()
        self.user = User.objects.create_user(username="gwo-user", password="pass12345")
        self.customer = Customer.objects.create(user=self.user, full_name="کاربر تست", phone="09121230099")
        self.vendor = Vendor.objects.create(store=self.store, name="فروشگاه", slug="shop-gwo")
        self.category = Category.objects.create(store=self.store, name="هدایا", slug="gifts-gwo")
        self.product = Product.objects.create(
            store=self.store, vendor=self.vendor, category=self.category, name="هدیه",
            slug="gift-gwo", sku="SKU-GWO1", price=Decimal("100000"), stock=10,
        )
        self.shipping = ShippingMethod.objects.create(store=self.store, name="پست", slug="post-gwo", cost=Decimal("45000"))
        self.gateway = PaymentGateway.objects.create(store=self.store, name="درگاه", slug="gw-gwo")
        self.address = Address.objects.create(
            customer=self.customer, receiver_name="کاربر تست", phone="09121230099",
            province="تهران", city="تهران", postal_code="1111111111", full_address="خیابان آزادی",
        )
        shop = ShopSettings.load(store=self.store)
        shop.gift_wrap_available = True
        shop.gift_wrap_price = Decimal("18000")
        shop.save(update_fields=["gift_wrap_available", "gift_wrap_price"])

        self.cart = Cart.objects.create(customer=self.customer)
        add_item_to_cart(self.cart, self.product, None, 2, gift_wrap_requested=True)

    def test_order_item_snapshots_gift_wrap_selection(self):
        order = create_order_from_cart(
            self.cart, customer=self.customer, vendor=self.vendor, address=self.address,
            shipping_method=self.shipping, payment_gateway=self.gateway, store=self.store,
        )
        order_item = order.items.get()
        self.assertTrue(order_item.gift_wrap_selected)
        self.assertEqual(order_item.gift_wrap_unit_price, Decimal("18000"))
        self.assertEqual(order_item.gift_wrap_line_total, Decimal("36000"))  # 18000 * qty(2)

    def test_order_item_gift_wrap_unaffected_by_later_shopsettings_change(self):
        """Changing ShopSettings.gift_wrap_price after the order is placed
        must never alter the historical OrderItem snapshot."""
        order = create_order_from_cart(
            self.cart, customer=self.customer, vendor=self.vendor, address=self.address,
            shipping_method=self.shipping, payment_gateway=self.gateway, store=self.store,
        )
        shop = ShopSettings.load(store=self.store)
        shop.gift_wrap_price = Decimal("99999")
        shop.save(update_fields=["gift_wrap_price"])

        order_item = order.items.get()
        order_item.refresh_from_db()
        self.assertEqual(order_item.gift_wrap_unit_price, Decimal("18000"))
