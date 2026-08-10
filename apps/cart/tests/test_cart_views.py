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

    def test_add_invalid_quantity_is_rejected_not_added(self):
        """Checkpoint (server-side stock enforcement): a non-numeric quantity
        must be rejected outright — it must NOT silently default to 1 and
        succeed, since that would hide a tampered/malformed request behind
        an apparently successful add."""
        response = self.client.post(reverse("cart:add", args=[self.product.slug]), {"quantity": "not-a-number"})
        self.assertEqual(response.status_code, 200)  # htmx error convention: 200 + err toast, no body swap
        self.assertEqual(CartItem.objects.count(), 0)
        trigger = json.loads(response.headers["HX-Trigger"])
        self.assertEqual(trigger["toast"]["type"], "err")

    def test_add_zero_quantity_is_rejected_not_added(self):
        response = self.client.post(reverse("cart:add", args=[self.product.slug]), {"quantity": 0})
        self.assertEqual(CartItem.objects.count(), 0)
        trigger = json.loads(response.headers["HX-Trigger"])
        self.assertEqual(trigger["toast"]["type"], "err")

    def test_add_negative_quantity_is_rejected_not_added(self):
        response = self.client.post(reverse("cart:add", args=[self.product.slug]), {"quantity": -5})
        self.assertEqual(CartItem.objects.count(), 0)
        trigger = json.loads(response.headers["HX-Trigger"])
        self.assertEqual(trigger["toast"]["type"], "err")

    def test_add_zero_stock_product_is_rejected(self):
        zero_stock = Product.objects.create(
            store=Store.objects.get(slug="akhlaghi"), vendor=self.product.vendor, category=self.product.category,
            name="کالای بدون موجودی", slug="sample-cav-zero", sku="SKU-CAV-ZERO",
            price=Decimal("100000"), stock=0,
        )
        response = self.client.post(reverse("cart:add", args=[zero_stock.slug]), {"quantity": 1})
        self.assertEqual(CartItem.objects.count(), 0)
        trigger = json.loads(response.headers["HX-Trigger"])
        self.assertEqual(trigger["toast"]["type"], "err")

    def test_add_quantity_exceeding_stock_is_rejected(self):
        response = self.client.post(reverse("cart:add", args=[self.product.slug]), {"quantity": 999})
        self.assertEqual(CartItem.objects.count(), 0)
        trigger = json.loads(response.headers["HX-Trigger"])
        self.assertEqual(trigger["toast"]["type"], "err")

    def test_add_zero_stock_variant_is_rejected(self):
        from apps.catalog.models import ProductVariant

        variant = ProductVariant.objects.create(
            product=self.product, attribute="رنگ", value="قرمز", stock=0, is_active=True,
        )
        response = self.client.post(
            reverse("cart:add", args=[self.product.slug]), {"variant_id": variant.pk, "quantity": 1}
        )
        self.assertEqual(CartItem.objects.count(), 0)
        trigger = json.loads(response.headers["HX-Trigger"])
        self.assertEqual(trigger["toast"]["type"], "err")

    def test_existing_cart_quantity_counted_toward_stock_limit(self):
        """Adding a second time must count the quantity already in the cart
        against available stock, not just the newly-requested quantity."""
        self.client.post(reverse("cart:add", args=[self.product.slug]), {"quantity": 8})
        self.assertEqual(CartItem.objects.get().quantity, 8)
        # Stock is 10; 8 already in cart + 5 more would be 13 > 10 → rejected.
        response = self.client.post(reverse("cart:add", args=[self.product.slug]), {"quantity": 5})
        trigger = json.loads(response.headers["HX-Trigger"])
        self.assertEqual(trigger["toast"]["type"], "err")
        self.assertEqual(CartItem.objects.get().quantity, 8)  # unchanged — not partially bumped

    def test_add_within_remaining_stock_after_existing_cart_quantity_succeeds(self):
        self.client.post(reverse("cart:add", args=[self.product.slug]), {"quantity": 8})
        response = self.client.post(reverse("cart:add", args=[self.product.slug]), {"quantity": 2})
        trigger = json.loads(response.headers["HX-Trigger"])
        self.assertEqual(trigger["toast"]["type"], "ok")
        self.assertEqual(CartItem.objects.get().quantity, 10)


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

    def test_cart_page_displays_variants_absolute_price_not_product_base_price(self):
        """رگرسیونِ صفحه‌ی سبد — قبل از این وصله، این صفحه همیشه
        product.final_price نمایش می‌داد، حتی وقتی تنوعِ انتخاب‌شده قیمتِ
        مستقلِ کاملاً متفاوتی داشت (مثلاً قیچیِ ایتالیایی)."""
        from apps.catalog.models import ProductVariant

        store = Store.objects.get(slug="akhlaghi")
        vendor = Vendor.objects.create(store=store, name="فروشگاه", slug="shop-cwv")
        category = Category.objects.create(store=store, name="ابزار", slug="tools-cwv")
        scissors = Product.objects.create(
            store=store, vendor=vendor, category=category,
            name="قیچی", slug="scissors-cwv", sku="SKU-SCISSORS-CWV", price=Decimal("1"),
            product_type=Product.ProductType.VARIABLE,
        )
        italian = ProductVariant.objects.create(
            product=scissors, attribute="کشور سازنده", value="ایتالیایی", price=Decimal("800000"), stock=5,
        )
        self.client.post(
            reverse("cart:add", args=[scissors.slug]), {"variant_id": italian.pk, "quantity": 1}
        )
        response = self.client.get(reverse("cart:detail"))
        self.assertContains(response, "۸۰۰٬۰۰۰")
        self.assertNotContains(response, "۱ تومان")

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
