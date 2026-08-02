import json
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.cart.models import Cart, CartItem
from apps.catalog.models import Category, Product, Vendor
from apps.customers.models import Customer
from apps.stores.models import Store

User = get_user_model()


class CartAddViewTests(TestCase):
    def setUp(self):
        store = Store.objects.get(slug="akhlaghi")
        vendor = Vendor.objects.create(store=store, name="فروشگاه", slug="shop-cav")
        category = Category.objects.create(store=store, name="دیجیتال", slug="digital-cav")
        self.product = Product.objects.create(
            store=store, vendor=vendor, category=category, name="کالای نمونه", slug="sample-cav",
            sku="SKU-CAV1", price=Decimal("300000"), stock=10,
        )

    def test_add_to_cart_as_guest_creates_session_cart_item(self):
        response = self.client.post(reverse("cart:add", args=[self.product.slug]), {"quantity": 2})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(CartItem.objects.count(), 1)
        item = CartItem.objects.first()
        self.assertEqual(item.quantity, 2)
        self.assertIsNone(item.cart.customer)

    def test_add_to_cart_response_updates_header_badge_via_oob(self):
        response = self.client.post(reverse("cart:add", args=[self.product.slug]), {"quantity": 1})
        self.assertContains(response, 'id="cart-count"')
        self.assertContains(response, "hx-swap-oob")

    def test_add_to_cart_triggers_toast(self):
        response = self.client.post(reverse("cart:add", args=[self.product.slug]), {"quantity": 1})
        self.assertIn("HX-Trigger", response.headers)
        trigger = json.loads(response.headers["HX-Trigger"])
        self.assertIn(self.product.name, trigger["toast"]["message"])

    def test_add_to_cart_as_logged_in_customer_uses_customer_cart(self):
        user = User.objects.create_user(username="cart_view_user", password="pass12345")
        customer = Customer.objects.create(user=user, full_name="مشتری تست", phone="09121110021")
        self.client.login(username="cart_view_user", password="pass12345")
        self.client.post(reverse("cart:add", args=[self.product.slug]), {"quantity": 1})
        cart = Cart.objects.get(customer=customer)
        self.assertEqual(cart.items.count(), 1)

    def test_add_to_cart_get_not_allowed(self):
        response = self.client.get(reverse("cart:add", args=[self.product.slug]))
        self.assertEqual(response.status_code, 405)

    def test_add_invalid_quantity_defaults_to_one(self):
        response = self.client.post(reverse("cart:add", args=[self.product.slug]), {"quantity": "not-a-number"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(CartItem.objects.first().quantity, 1)


class CartDetailViewTests(TestCase):
    def setUp(self):
        store = Store.objects.get(slug="akhlaghi")
        vendor = Vendor.objects.create(store=store, name="فروشگاه", slug="shop-cdv")
        category = Category.objects.create(store=store, name="دیجیتال", slug="digital-cdv")
        self.product = Product.objects.create(
            store=store, vendor=vendor, category=category, name="کالای نمونه", slug="sample-cdv",
            sku="SKU-CDV1", price=Decimal("400000"), discount_percent=25, stock=10,
        )

    def test_empty_cart_shows_empty_state(self):
        response = self.client.get(reverse("cart:detail"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "سبد خرید شما خالی است")

    def test_cart_with_items_shows_totals_from_pricing_service(self):
        self.client.post(reverse("cart:add", args=[self.product.slug]), {"quantity": 2})
        response = self.client.get(reverse("cart:detail"))
        self.assertContains(response, self.product.name)
        totals = response.context["totals"]
        self.assertEqual(totals["items_total"], Decimal("600000"))
        self.assertEqual(totals["product_discount"], Decimal("200000"))

    def test_cart_with_items_links_continue_button_to_checkout(self):
        self.client.post(reverse("cart:add", args=[self.product.slug]), {"quantity": 1})
        response = self.client.get(reverse("cart:detail"))
        self.assertContains(response, reverse("orders:checkout-step1"))


class CartItemUpdateRemoveTests(TestCase):
    def setUp(self):
        store = Store.objects.get(slug="akhlaghi")
        vendor = Vendor.objects.create(store=store, name="فروشگاه", slug="shop-ciu")
        category = Category.objects.create(store=store, name="دیجیتال", slug="digital-ciu")
        self.product = Product.objects.create(
            store=store, vendor=vendor, category=category, name="کالای نمونه", slug="sample-ciu",
            sku="SKU-CIU1", price=Decimal("100000"), stock=5,
        )
        self.client.post(reverse("cart:add", args=[self.product.slug]), {"quantity": 1})
        self.item = CartItem.objects.first()

    def test_update_quantity_changes_item(self):
        response = self.client.post(reverse("cart:item-update", args=[self.item.id]), {"quantity": 3})
        self.assertEqual(response.status_code, 200)
        self.item.refresh_from_db()
        self.assertEqual(self.item.quantity, 3)

    def test_update_quantity_clamped_to_available_stock(self):
        self.client.post(reverse("cart:item-update", args=[self.item.id]), {"quantity": 999})
        self.item.refresh_from_db()
        self.assertEqual(self.item.quantity, 5)

    def test_update_quantity_never_goes_below_one(self):
        self.client.post(reverse("cart:item-update", args=[self.item.id]), {"quantity": 0})
        self.item.refresh_from_db()
        self.assertEqual(self.item.quantity, 1)

    def test_remove_item_deletes_it(self):
        response = self.client.post(reverse("cart:item-remove", args=[self.item.id]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(CartItem.objects.count(), 0)
        self.assertContains(response, "سبد خرید شما خالی است")

    def test_cannot_update_another_sessions_item(self):
        self.client.cookies.pop("sessionid", None)
        response = self.client.post(reverse("cart:item-update", args=[self.item.id]), {"quantity": 2})
        self.assertEqual(response.status_code, 404)

    def test_quantity_clamped_to_variant_stock_not_product_stock(self):
        """کالای مادر ۵ عدد موجودی دارد، اما تنوعِ انتخاب‌شده فقط ۲ عدد —
        سقفِ تعداد باید موجودیِ همان تنوع باشد، نه کالای مادر."""
        from apps.catalog.models import ProductVariant

        variant = ProductVariant.objects.create(
            product=self.product, attribute="رنگ", value="قرمز", stock=2, is_active=True,
        )
        self.client.post(
            reverse("cart:add", args=[self.product.slug]), {"variant_id": variant.pk, "quantity": 1}
        )
        variant_item = CartItem.objects.get(variant=variant)
        response = self.client.post(reverse("cart:item-update", args=[variant_item.id]), {"quantity": 999})
        self.assertEqual(response.status_code, 200)
        variant_item.refresh_from_db()
        self.assertEqual(variant_item.quantity, 2)
