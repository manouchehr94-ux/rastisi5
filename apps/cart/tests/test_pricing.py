from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from apps.catalog.models import Category, Product, Vendor
from apps.cart.models import Cart, CartItem, Coupon
from apps.cart.services.pricing import cart_totals, coupon_is_applicable, product_final_price
from apps.core.models import ShopSettings
from apps.orders.models import ShippingMethod
from apps.stores.models import Store


def _akhlaghi():
    return Store.objects.get(slug="akhlaghi")


class PricingServiceTests(TestCase):
    def setUp(self):
        self.store = _akhlaghi()
        self.vendor = Vendor.objects.create(store=self.store, name="فروشگاه", slug="shop-p")
        self.category = Category.objects.create(store=self.store, name="پوشاک", slug="clothing-p")
        self.shipping = ShippingMethod.objects.create(store=self.store, name="پست پیشتاز", slug="post-p", cost=Decimal("45000"))
        self.cart = Cart.objects.create(session_key="guest-p")

    def _add_item(self, price, discount_percent=0, quantity=1, sku="SKU-P"):
        product = Product.objects.create(
            store=self.store, vendor=self.vendor, category=self.category, name="کالای نمونه",
            slug=f"{sku}-slug", sku=sku, price=Decimal(price), discount_percent=discount_percent,
        )
        return CartItem.objects.create(
            cart=self.cart, product=product, quantity=quantity, unit_price=product.final_price
        )

    def test_product_final_price_delegates_to_model_property(self):
        product = Product.objects.create(
            store=self.store, vendor=self.vendor, category=self.category, name="کالا", slug="p-final",
            sku="SKU-FINAL", price=Decimal("200000"), discount_percent=25,
        )
        self.assertEqual(product_final_price(product), Decimal("150000"))

    def test_cart_totals_empty_cart_without_shipping_method_is_zero(self):
        totals = cart_totals(self.cart, store=self.store)
        self.assertEqual(totals["items_total"], Decimal("0"))
        self.assertEqual(totals["grand_total"], Decimal("0"))
        self.assertFalse(totals["free_shipping"])

    def test_cart_totals_empty_cart_still_charges_shipping(self):
        # سبد خالی زیر آستانه‌ی ارسال رایگان است؛ اگر روش ارسال انتخاب شده باشد هزینه‌اش لحاظ می‌شود
        totals = cart_totals(self.cart, store=self.store, shipping_method=self.shipping)
        self.assertEqual(totals["items_total"], Decimal("0"))
        self.assertEqual(totals["shipping_cost"], Decimal("45000"))
        self.assertEqual(totals["grand_total"], Decimal("45000"))

    def test_cart_totals_no_discount_no_coupon_below_threshold(self):
        self._add_item(price=100_000, quantity=2)  # 200,000 total, below threshold
        totals = cart_totals(self.cart, store=self.store, shipping_method=self.shipping)
        self.assertEqual(totals["items_total"], Decimal("200000"))
        self.assertEqual(totals["product_discount"], Decimal("0"))
        self.assertEqual(totals["coupon_discount"], Decimal("0"))
        self.assertFalse(totals["free_shipping"])
        self.assertEqual(totals["shipping_cost"], Decimal("45000"))
        self.assertEqual(totals["tax"], Decimal("18000"))  # 9% of 200,000
        self.assertEqual(totals["grand_total"], Decimal("263000"))

    def test_cart_totals_product_discount_calculated(self):
        self._add_item(price=200_000, discount_percent=10, quantity=1)  # final 180,000
        totals = cart_totals(self.cart, store=self.store, shipping_method=self.shipping)
        self.assertEqual(totals["items_total"], Decimal("180000"))
        self.assertEqual(totals["product_discount"], Decimal("20000"))

    def test_cart_totals_free_shipping_over_threshold(self):
        self._add_item(price=600_000, quantity=1)
        totals = cart_totals(self.cart, store=self.store, shipping_method=self.shipping)
        self.assertTrue(totals["free_shipping"])
        self.assertEqual(totals["shipping_cost"], Decimal("0"))

    def test_cart_totals_percent_coupon(self):
        self._add_item(price=100_000, quantity=2)  # items_total 200,000
        coupon = Coupon.objects.create(code="STYLE20", type=Coupon.Type.PERCENT, value=20)
        totals = cart_totals(self.cart, store=self.store, coupon=coupon, shipping_method=self.shipping)
        self.assertTrue(totals["coupon_applied"])
        self.assertEqual(totals["coupon_discount"], Decimal("40000"))

    def test_cart_totals_fixed_coupon_capped_at_items_total(self):
        self._add_item(price=100_000, quantity=1)  # items_total 100,000
        coupon = Coupon.objects.create(code="DIGI50", type=Coupon.Type.FIXED, value=500_000)
        totals = cart_totals(self.cart, store=self.store, coupon=coupon, shipping_method=self.shipping)
        self.assertEqual(totals["coupon_discount"], Decimal("100000"))
        self.assertEqual(totals["tax"], Decimal("0"))  # after_coupon == 0
        # fixed coupon does not force free shipping; items_total is below threshold
        self.assertFalse(totals["free_shipping"])
        self.assertEqual(totals["shipping_cost"], Decimal("45000"))
        self.assertEqual(totals["grand_total"], Decimal("45000"))

    def test_cart_totals_free_ship_coupon_forces_zero_shipping(self):
        self._add_item(price=100_000, quantity=1)  # below threshold
        coupon = Coupon.objects.create(code="FREESHIP", type=Coupon.Type.FREE_SHIP, value=0)
        totals = cart_totals(self.cart, store=self.store, coupon=coupon, shipping_method=self.shipping)
        self.assertTrue(totals["free_shipping"])
        self.assertEqual(totals["shipping_cost"], Decimal("0"))

    def test_coupon_not_applicable_when_inactive(self):
        self._add_item(price=100_000, quantity=1)
        coupon = Coupon.objects.create(code="OFF10", type=Coupon.Type.PERCENT, value=10, is_active=False)
        totals = cart_totals(self.cart, store=self.store, coupon=coupon, shipping_method=self.shipping)
        self.assertFalse(totals["coupon_applied"])
        self.assertEqual(totals["coupon_discount"], Decimal("0"))

    def test_coupon_not_applicable_when_expired(self):
        self._add_item(price=100_000, quantity=1)
        coupon = Coupon.objects.create(
            code="OLD10", type=Coupon.Type.PERCENT, value=10,
            expires_at=timezone.now() - timezone.timedelta(days=1),
        )
        self.assertFalse(coupon_is_applicable(coupon, Decimal("100000")))

    def test_coupon_not_applicable_below_min_order(self):
        self._add_item(price=50_000, quantity=1)
        coupon = Coupon.objects.create(code="BIG100", type=Coupon.Type.FIXED, value=100_000, min_order=200_000)
        totals = cart_totals(self.cart, store=self.store, coupon=coupon, shipping_method=self.shipping)
        self.assertFalse(totals["coupon_applied"])

    def test_coupon_not_applicable_when_usage_limit_reached(self):
        self._add_item(price=100_000, quantity=1)
        coupon = Coupon.objects.create(
            code="LIMIT1", type=Coupon.Type.PERCENT, value=10, usage_limit=1, used_count=1
        )
        self.assertFalse(coupon_is_applicable(coupon, Decimal("100000")))

    def test_tax_and_threshold_are_configurable_via_shop_settings(self):
        """نرخ مالیات و آستانه‌ی ارسال رایگان از همان ShopSettings خوانده می‌شوند که پنل مدیریت ویرایش می‌کند."""
        shop = ShopSettings.load(store=self.store)
        shop.tax_percent = Decimal("5")
        shop.free_shipping_threshold = Decimal("1000000")
        shop.save()

        self._add_item(price=100_000, quantity=1)
        totals = cart_totals(self.cart, store=self.store, shipping_method=self.shipping)
        self.assertEqual(totals["tax"], Decimal("5000"))
        self.assertFalse(totals["free_shipping"])


class PricingTwoStoreIsolationTests(TestCase):
    """اثبات این‌که ``cart_totals`` مقدار مالیات/ارسال رایگان Store دیگر را
    هرگز برنمی‌گرداند — با دو Store واقعی و دو ShopSettings واقعاً متفاوت،
    نه فقط mock کردن ``ShopSettings.load()``."""

    def setUp(self):
        self.store_a = _akhlaghi()
        self.store_b = Store.objects.create(name="Store B", slug="store-b", status=Store.Status.ACTIVE)

        shop_a = ShopSettings.load(store=self.store_a)
        shop_a.tax_percent = Decimal("9")
        shop_a.free_shipping_threshold = Decimal("500000")
        shop_a.save()

        shop_b = ShopSettings.provision_for(self.store_b)
        shop_b.tax_percent = Decimal("20")
        shop_b.free_shipping_threshold = Decimal("100000")
        shop_b.save()

        self.vendor_a = Vendor.objects.create(store=self.store_a, name="فروشگاه", slug="shop-two-store-a")
        self.category_a = Category.objects.create(store=self.store_a, name="پوشاک", slug="clothing-two-store-a")
        self.vendor_b = Vendor.objects.create(store=self.store_b, name="فروشگاه B", slug="shop-two-store-b")
        self.category_b = Category.objects.create(store=self.store_b, name="پوشاک B", slug="clothing-two-store-b")
        self.cart_a = Cart.objects.create(session_key="guest-a")
        self.cart_b = Cart.objects.create(session_key="guest-b")

    def _add_item(self, cart, price, sku, *, store):
        vendor = self.vendor_a if store == self.store_a else self.vendor_b
        category = self.category_a if store == self.store_a else self.category_b
        product = Product.objects.create(
            store=store, vendor=vendor, category=category, name="کالای نمونه",
            slug=f"{sku}-slug", sku=sku, price=Decimal(price),
        )
        CartItem.objects.create(cart=cart, product=product, quantity=1, unit_price=product.final_price)

    def test_store_a_pricing_uses_store_a_settings(self):
        self._add_item(self.cart_a, 200_000, "TWO-A", store=self.store_a)
        totals = cart_totals(self.cart_a, store=self.store_a)
        self.assertEqual(totals["tax"], Decimal("18000"))  # 9% of 200,000
        self.assertFalse(totals["free_shipping"])  # below 500,000 threshold

    def test_store_b_pricing_uses_store_b_settings(self):
        self._add_item(self.cart_b, 200_000, "TWO-B", store=self.store_b)
        totals = cart_totals(self.cart_b, store=self.store_b)
        self.assertEqual(totals["tax"], Decimal("40000"))  # 20% of 200,000
        self.assertTrue(totals["free_shipping"])  # above 100,000 threshold

    def test_distinct_tax_and_shipping_produce_distinct_results(self):
        self._add_item(self.cart_a, 200_000, "TWO-C", store=self.store_a)
        self._add_item(self.cart_b, 200_000, "TWO-D", store=self.store_b)
        totals_a = cart_totals(self.cart_a, store=self.store_a)
        totals_b = cart_totals(self.cart_b, store=self.store_b)
        self.assertNotEqual(totals_a["tax"], totals_b["tax"])
        self.assertNotEqual(totals_a["free_shipping"], totals_b["free_shipping"])

    def test_store_b_never_receives_store_a_settings(self):
        self._add_item(self.cart_b, 200_000, "TWO-E", store=self.store_b)
        totals = cart_totals(self.cart_b, store=self.store_b)
        # If Store A's settings had leaked in, tax would be 18000 (9%), not 40000 (20%).
        self.assertEqual(totals["tax"], Decimal("40000"))

    def test_explicit_store_none_is_rejected_not_silently_defaulted(self):
        self._add_item(self.cart_a, 200_000, "TWO-F", store=self.store_a)
        with self.assertRaises(ValueError):
            cart_totals(self.cart_a, store=None)

    def test_second_store_does_not_break_store_b_explicit_pricing(self):
        """با وجود دو Store (که حالت سازگاری موقت را غیرفعال می‌کند)، مسیر
        Store صریح باید همچنان کار کند — قطع سازگاری موقت نباید مسیر معتبر
        Store B را هم بشکند."""
        self._add_item(self.cart_b, 200_000, "TWO-G", store=self.store_b)
        totals = cart_totals(self.cart_b, store=self.store_b)
        self.assertTrue(totals["free_shipping"])
