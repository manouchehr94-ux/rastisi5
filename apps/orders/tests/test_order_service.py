import threading
from decimal import Decimal
from unittest import skipUnless

from django.contrib.auth import get_user_model
from django.db import connection, transaction
from django.test import TestCase, TransactionTestCase

from apps.cart.models import Cart, CartItem, Coupon
from apps.catalog.models import Category, Product, ProductVariant, StockMovement, Vendor
from apps.core.models import ShopSettings
from apps.customers.models import Address, Customer
from apps.orders.models import Order, OrderStatusHistory, PaymentGateway, ShippingMethod
from apps.orders.services.order_service import change_order_status, create_order_from_cart
from apps.sms.models import SmsLog, SmsTemplate
from apps.stores.models import Store

User = get_user_model()


def _akhlaghi():
    return Store.objects.get(slug="akhlaghi")


class CreateOrderFromCartTests(TestCase):
    def setUp(self):
        self.store = _akhlaghi()
        self.user = User.objects.create_user(username="hasan", password="pass12345")
        self.customer = Customer.objects.create(user=self.user, full_name="حسن کریمی", phone="09121230000")
        self.vendor = Vendor.objects.create(store=self.store, name="فروشگاه", slug="shop-os")
        self.category = Category.objects.create(store=self.store, name="دیجیتال", slug="digital-os")
        self.product = Product.objects.create(
            store=self.store, vendor=self.vendor, category=self.category, name="هدفون", slug="headphone-os",
            sku="SKU-OS1", price=Decimal("1000000"), discount_percent=10, stock=10,
        )
        self.shipping = ShippingMethod.objects.create(store=self.store, name="پست", slug="post-os", cost=Decimal("45000"))
        self.gateway = PaymentGateway.objects.create(store=self.store, name="زرین‌پال", slug="zarin-os")
        self.address = Address.objects.create(
            customer=self.customer, receiver_name="حسن کریمی", phone="09121230000",
            province="تهران", city="تهران", postal_code="1111111111", full_address="خیابان آزادی",
        )
        self.cart = Cart.objects.create(customer=self.customer)
        CartItem.objects.create(
            cart=self.cart, product=self.product, quantity=2, unit_price=self.product.final_price
        )

    def _create(self, coupon=None):
        return create_order_from_cart(
            self.cart, customer=self.customer, vendor=self.vendor, address=self.address,
            shipping_method=self.shipping, payment_gateway=self.gateway, coupon=coupon,
            store=self.store,
        )

    def test_create_order_snapshots_amounts_and_items(self):
        order = self._create()
        self.assertEqual(order.items_total, Decimal("1800000"))  # 900,000 * 2
        self.assertEqual(order.product_discount, Decimal("200000"))  # 100,000 * 2
        self.assertEqual(order.status, Order.Status.PENDING)
        self.assertEqual(order.payment_status, Order.PaymentStatus.PENDING)
        self.assertEqual(order.address["city"], "تهران")

        self.assertEqual(order.items.count(), 1)
        item = order.items.first()
        self.assertEqual(item.product_name, "هدفون")
        self.assertEqual(item.quantity, 2)
        self.assertEqual(item.unit_price, Decimal("900000"))
        self.assertEqual(item.line_total, Decimal("1800000"))

    def test_create_order_records_initial_status_history(self):
        order = self._create()
        history = order.status_history.all()
        self.assertEqual(history.count(), 1)
        self.assertEqual(history.first().from_status, "")
        self.assertEqual(history.first().to_status, Order.Status.PENDING)

    def test_create_order_from_empty_cart_raises(self):
        empty_cart = Cart.objects.create(customer=self.customer)
        with self.assertRaises(ValueError):
            create_order_from_cart(
                empty_cart, customer=self.customer, vendor=self.vendor, address=self.address,
                shipping_method=self.shipping, payment_gateway=self.gateway, store=self.store,
            )

    def test_create_order_increments_coupon_used_count_when_applied(self):
        coupon = Coupon.objects.create(store=self.store, code="STYLE20", type=Coupon.Type.PERCENT, value=20)
        self._create(coupon=coupon)
        coupon.refresh_from_db()
        self.assertEqual(coupon.used_count, 1)

    def test_create_order_does_not_increment_coupon_used_count_when_not_applicable(self):
        coupon = Coupon.objects.create(
            store=self.store, code="BIG500", type=Coupon.Type.FIXED, value=100_000, min_order=Decimal("5000000")
        )
        order = self._create(coupon=coupon)
        coupon.refresh_from_db()
        self.assertEqual(coupon.used_count, 0)
        self.assertEqual(order.coupon_discount, Decimal("0"))

    def test_order_placed_sms_sent_after_commit(self):
        SmsTemplate.ensure_defaults()
        with self.captureOnCommitCallbacks(execute=True):
            order = self._create()
        log = SmsLog.objects.filter(event_key="order_placed", recipient=self.customer.phone).first()
        self.assertIsNotNone(log)
        self.assertIn(order.code, log.message)

    def test_order_placed_sms_not_sent_if_transaction_rolls_back(self):
        """on_commit یعنی اگر تراکنش رول‌بک شود، پیامک هم نباید ارسال شود."""
        SmsTemplate.ensure_defaults()
        try:
            with self.captureOnCommitCallbacks(execute=True):
                with transaction.atomic():
                    self._create()
                    raise ValueError("خطای عمدی برای رول‌بک")
        except ValueError:
            pass
        self.assertFalse(SmsLog.objects.filter(event_key="order_placed").exists())

    def test_create_order_decrements_product_stock_and_records_ledger(self):
        self._create()
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 8)
        movement = StockMovement.objects.get(product=self.product)
        self.assertEqual(movement.delta, -2)
        self.assertEqual(movement.stock_before, 10)
        self.assertEqual(movement.stock_after, 8)
        self.assertEqual(movement.reason, StockMovement.Reason.ORDER_PLACED)
        self.assertEqual(movement.variant, None)


class CouponConcurrencySafetyTests(TestCase):
    """CB-1 regression coverage for the ``select_for_update()`` fix in
    ``order_service._lock_coupon`` — deterministic, DB-engine-agnostic
    (SQLite and PostgreSQL both prove these correctness properties). The
    genuine multi-writer race reproduction, which SQLite cannot validate,
    lives in ``CouponRedemptionRaceConditionTests`` below."""

    def setUp(self):
        self.store = _akhlaghi()
        self.user = User.objects.create_user(username="coupon-user", password="pass12345")
        self.customer = Customer.objects.create(user=self.user, full_name="سارا احمدی", phone="09121230099")
        self.vendor = Vendor.objects.create(store=self.store, name="فروشگاه کوپن", slug="shop-coupon")
        self.category = Category.objects.create(store=self.store, name="دیجیتال کوپن", slug="digital-coupon")
        self.product = Product.objects.create(
            store=self.store, vendor=self.vendor, category=self.category, name="کیبورد", slug="keyboard-coupon",
            sku="SKU-CPN1", price=Decimal("1000000"), discount_percent=0, stock=100,
        )
        self.shipping = ShippingMethod.objects.create(store=self.store, name="پست", slug="post-coupon", cost=Decimal("45000"))
        self.gateway = PaymentGateway.objects.create(store=self.store, name="زرین‌پال", slug="zarin-coupon")
        self.address = Address.objects.create(
            customer=self.customer, receiver_name="سارا احمدی", phone="09121230099",
            province="تهران", city="تهران", postal_code="1111111111", full_address="خیابان ولیعصر",
        )

    def _cart(self, quantity=1):
        cart = Cart.objects.create(customer=self.customer)
        CartItem.objects.create(
            cart=cart, product=self.product, quantity=quantity, unit_price=self.product.final_price
        )
        return cart

    def _create(self, cart, coupon=None):
        return create_order_from_cart(
            cart, customer=self.customer, vendor=self.vendor, address=self.address,
            shipping_method=self.shipping, payment_gateway=self.gateway, coupon=coupon,
            store=self.store,
        )

    def test_single_redemption_still_applies_discount_and_increments_once(self):
        coupon = Coupon.objects.create(
            store=self.store, code="ONCE10", type=Coupon.Type.PERCENT, value=10, usage_limit=5
        )
        order = self._create(self._cart(), coupon=coupon)
        coupon.refresh_from_db()
        self.assertEqual(coupon.used_count, 1)
        self.assertGreater(order.coupon_discount, Decimal("0"))

    def test_exhausted_coupon_is_rejected_no_discount_no_further_increment(self):
        coupon = Coupon.objects.create(
            store=self.store, code="MAXED", type=Coupon.Type.PERCENT, value=10,
            usage_limit=1, used_count=1,
        )
        order = self._create(self._cart(), coupon=coupon)
        coupon.refresh_from_db()
        self.assertEqual(coupon.used_count, 1)  # بدون تغییر — همچنان دقیقاً روی سقف
        self.assertEqual(order.coupon_discount, Decimal("0"))

    def test_unlimited_coupon_keeps_incrementing_without_being_rejected(self):
        coupon = Coupon.objects.create(
            store=self.store, code="UNLIM", type=Coupon.Type.PERCENT, value=5, usage_limit=None
        )
        for expected in (1, 2, 3):
            order = self._create(self._cart(), coupon=coupon)
            coupon.refresh_from_db()
            self.assertEqual(coupon.used_count, expected)
            self.assertGreater(order.coupon_discount, Decimal("0"))

    def test_store_isolation_rejects_coupon_from_other_store_and_leaves_it_untouched(self):
        other_store = Store.objects.create(name="فروشگاه دیگر", slug="coupon-other-store", status=Store.Status.ACTIVE)
        foreign_coupon = Coupon.objects.create(store=other_store, code="FOREIGN", type=Coupon.Type.PERCENT, value=10)
        with self.assertRaises(ValueError):
            self._create(self._cart(), coupon=foreign_coupon)
        foreign_coupon.refresh_from_db()
        self.assertEqual(foreign_coupon.used_count, 0)

    def test_two_stores_with_same_coupon_code_track_usage_independently(self):
        other_store = Store.objects.create(name="فروشگاه دو", slug="coupon-store-two", status=Store.Status.ACTIVE)
        ShopSettings.provision_for(other_store)
        other_vendor = Vendor.objects.create(store=other_store, name="فروشنده دو", slug="vendor-coupon-two")
        other_category = Category.objects.create(store=other_store, name="دسته دو", slug="cat-coupon-two")
        other_product = Product.objects.create(
            store=other_store, vendor=other_vendor, category=other_category, name="ماوس", slug="mouse-coupon-two",
            sku="SKU-CPN2", price=Decimal("500000"), stock=50,
        )
        other_shipping = ShippingMethod.objects.create(store=other_store, name="پست دو", slug="post-coupon-two", cost=Decimal("20000"))
        other_gateway = PaymentGateway.objects.create(store=other_store, name="درگاه دو", slug="gateway-coupon-two")
        other_user = User.objects.create_user(username="coupon-user-two", password="pass12345")
        other_customer = Customer.objects.create(user=other_user, full_name="نگار محمدی", phone="09121230098")
        other_address = Address.objects.create(
            customer=other_customer, receiver_name="نگار محمدی", phone="09121230098",
            province="تهران", city="تهران", postal_code="1111111112", full_address="خیابان کریمخان",
        )
        other_cart = Cart.objects.create(customer=other_customer)
        CartItem.objects.create(
            cart=other_cart, product=other_product, quantity=1, unit_price=other_product.final_price
        )

        coupon_a = Coupon.objects.create(store=self.store, code="SHARED", type=Coupon.Type.PERCENT, value=10)
        coupon_b = Coupon.objects.create(store=other_store, code="SHARED", type=Coupon.Type.PERCENT, value=10)

        self._create(self._cart(), coupon=coupon_a)
        create_order_from_cart(
            other_cart, customer=other_customer, vendor=other_vendor, address=other_address,
            shipping_method=other_shipping, payment_gateway=other_gateway, coupon=coupon_b,
            store=other_store,
        )

        coupon_a.refresh_from_db()
        coupon_b.refresh_from_db()
        self.assertEqual(coupon_a.used_count, 1)
        self.assertEqual(coupon_b.used_count, 1)

    def test_rollback_after_coupon_lock_does_not_consume_usage(self):
        coupon = Coupon.objects.create(
            store=self.store, code="ROLLBACK1", type=Coupon.Type.PERCENT, value=10, usage_limit=1
        )
        try:
            with transaction.atomic():
                self._create(self._cart(), coupon=coupon)
                raise ValueError("خطای عمدی برای رول‌بک")
        except ValueError:
            pass
        coupon.refresh_from_db()
        self.assertEqual(coupon.used_count, 0)

        # کوپن هنوز کاملاً قابل استفاده است — رول‌بک واقعاً استفاده را مصرف نکرده.
        order = self._create(self._cart(), coupon=coupon)
        coupon.refresh_from_db()
        self.assertEqual(coupon.used_count, 1)
        self.assertGreater(order.coupon_discount, Decimal("0"))


@skipUnless(
    connection.vendor == "postgresql",
    "True parallel-writer contention over the same Coupon row needs real "
    "row-level locking (select_for_update); SQLite serializes writers at "
    "the database-file level, so the specific lost-update/over-redemption "
    "race this fix closes is not observable there. Deterministic, "
    "engine-agnostic coverage of the fix's correctness lives in "
    "CouponConcurrencySafetyTests above. This is the "
    "LOCAL_POSTGRESQL_CONCURRENCY_VALIDATION evidence for CB-1.",
)
class CouponRedemptionRaceConditionTests(TransactionTestCase):
    """Real concurrent writers, real PostgreSQL row locks — proves
    ``_lock_coupon``'s ``select_for_update()`` actually prevents
    over-redemption of a limited-use coupon, not just a sequential-call
    simulation. Each worker thread independently re-reads the Coupon row
    (unlocked) before calling ``create_order_from_cart``, exactly mirroring
    how ``checkout_service.get_applied_coupon`` resolves it in a real
    request — a ``threading.Barrier`` forces all workers to perform that
    unlocked read at the same instant, reproducing the pre-fix race window
    where every worker could observe the same stale ``used_count``."""

    def setUp(self):
        # ``TransactionTestCase`` truncates all tables between tests (real
        # commits, no per-test rollback), so the ``akhlaghi`` Store seeded
        # by a data migration is not guaranteed to survive across test
        # methods here — a fresh Store is created explicitly instead,
        # mirroring the same choice already made by
        # ``NumberingConcurrencyTests`` in
        # apps/billing/tests/test_invoice_lines_numbering.py.
        self.store = Store.objects.create(name="فروشگاه رقابت کوپن", slug="coupon-race-store", status=Store.Status.ACTIVE)
        ShopSettings.provision_for(self.store)
        self.vendor = Vendor.objects.create(store=self.store, name="فروشگاه رقابت", slug="shop-race")
        self.category = Category.objects.create(store=self.store, name="دیجیتال رقابت", slug="digital-race")
        self.product = Product.objects.create(
            store=self.store, vendor=self.vendor, category=self.category, name="اسپیکر", slug="speaker-race",
            sku="SKU-RACE1", price=Decimal("1000000"), discount_percent=0, stock=1000,
        )
        self.shipping = ShippingMethod.objects.create(store=self.store, name="پست رقابت", slug="post-race", cost=Decimal("45000"))
        self.gateway = PaymentGateway.objects.create(store=self.store, name="درگاه رقابت", slug="gateway-race")
        self.usage_limit = 3
        self.coupon = Coupon.objects.create(
            store=self.store, code="RACE10", type=Coupon.Type.PERCENT, value=10, usage_limit=self.usage_limit,
        )

    def _customer_context(self, index):
        user = User.objects.create_user(username=f"racer{index}", password="pass12345")
        customer = Customer.objects.create(
            user=user, full_name=f"مشتری رقابت {index}", phone=f"0912000{index:04d}"
        )
        address = Address.objects.create(
            customer=customer, receiver_name=f"مشتری رقابت {index}", phone=f"0912000{index:04d}",
            province="تهران", city="تهران", postal_code="1111111111", full_address="خیابان انقلاب",
        )
        cart = Cart.objects.create(customer=customer)
        CartItem.objects.create(cart=cart, product=self.product, quantity=1, unit_price=self.product.final_price)
        return customer, address, cart

    def test_concurrent_redemptions_never_exceed_usage_limit(self):
        thread_count = 8
        contexts = [self._customer_context(i) for i in range(thread_count)]
        start_barrier = threading.Barrier(thread_count)
        discount_applied = []
        errors = []
        results_lock = threading.Lock()

        def worker(customer, address, cart):
            try:
                start_barrier.wait(timeout=10)
                # اسنپ‌شاتِ عمداً *بدون* قفل — دقیقاً همان کاری که
                # checkout_service.get_applied_coupon پیش از فراخوانیِ
                # create_order_from_cart انجام می‌دهد؛ اصلاح واقعی باید
                # داخلِ خودِ create_order_from_cart (_lock_coupon) اتفاق
                # بیفتد، نه این‌جا.
                unlocked_coupon = Coupon.objects.get(pk=self.coupon.pk)
                order = create_order_from_cart(
                    cart, customer=customer, vendor=self.vendor, address=address,
                    shipping_method=self.shipping, payment_gateway=self.gateway,
                    coupon=unlocked_coupon, store=self.store,
                )
                with results_lock:
                    discount_applied.append(order.coupon_discount > 0)
            except Exception as exc:  # noqa: BLE001 — captured for assertion, not swallowed
                with results_lock:
                    errors.append(exc)
            finally:
                connection.close()

        threads = [threading.Thread(target=worker, args=ctx) for ctx in contexts]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(errors, [])
        self.coupon.refresh_from_db()
        # هستهٔ CB-1: بدون قفل، هر ۸ ردهٔ رقابتی می‌توانستند used_count را
        # از رویِ همان اسنپ‌شاتِ قدیمی بخوانند و مستقل از هم افزایش دهند —
        # با _lock_coupon، هرگز نباید از سقفِ واقعیِ کوپن فراتر برود.
        self.assertLessEqual(self.coupon.used_count, self.usage_limit)
        self.assertEqual(self.coupon.used_count, sum(discount_applied))
        self.assertEqual(sum(discount_applied), self.usage_limit)


class CreateOrderFromCartWithVariantTests(TestCase):
    """نگاه کنید به ADR-31 — قبل از این PR، برای اقلامِ دارای تنوع،
    Product.stock به‌جای ProductVariant.stock کم می‌شد."""

    def setUp(self):
        self.store = _akhlaghi()
        self.user = User.objects.create_user(username="parisa", password="pass12345")
        self.customer = Customer.objects.create(user=self.user, full_name="پریسا احمدی", phone="09121230099")
        self.vendor = Vendor.objects.create(store=self.store, name="فروشگاه", slug="shop-osv")
        self.category = Category.objects.create(store=self.store, name="پوشاک", slug="clothing-osv")
        self.product = Product.objects.create(
            store=self.store, vendor=self.vendor, category=self.category, name="تی‌شرت", slug="tshirt-osv",
            sku="SKU-OSV1", price=Decimal("500000"), stock=0, product_type=Product.ProductType.VARIABLE,
        )
        self.variant = ProductVariant.objects.create(
            product=self.product, store=self.store, attribute="سایز", value="بزرگ", stock=5,
        )
        self.shipping = ShippingMethod.objects.create(store=self.store, name="پست", slug="post-osv", cost=Decimal("45000"))
        self.gateway = PaymentGateway.objects.create(store=self.store, name="زرین‌پال", slug="zarin-osv")
        self.address = Address.objects.create(
            customer=self.customer, receiver_name="پریسا احمدی", phone="09121230099",
            province="تهران", city="تهران", postal_code="1111111111", full_address="خیابان ولیعصر",
        )
        self.cart = Cart.objects.create(customer=self.customer)
        CartItem.objects.create(
            cart=self.cart, product=self.product, variant=self.variant, quantity=2,
            unit_price=self.product.final_price,
        )

    def _create(self):
        return create_order_from_cart(
            self.cart, customer=self.customer, vendor=self.vendor, address=self.address,
            shipping_method=self.shipping, payment_gateway=self.gateway, store=self.store,
        )

    def test_decrements_variant_stock_not_product_stock(self):
        self._create()
        self.variant.refresh_from_db()
        self.product.refresh_from_db()
        self.assertEqual(self.variant.stock, 3)
        self.assertEqual(self.product.stock, 0)  # unchanged — product itself was never the target

    def test_records_ledger_entry_against_variant(self):
        self._create()
        movement = StockMovement.objects.get(variant=self.variant)
        self.assertEqual(movement.delta, -2)
        self.assertEqual(movement.stock_before, 5)
        self.assertEqual(movement.stock_after, 3)
        self.assertEqual(movement.product_id, self.product.pk)

    def test_insufficient_variant_stock_rejected_even_though_product_stock_would_allow_it(self):
        self.product.stock = 100
        self.product.save(update_fields=["stock"])
        CartItem.objects.filter(cart=self.cart).update(quantity=999)
        with self.assertRaises(ValueError):
            self._create()
        self.variant.refresh_from_db()
        self.assertEqual(self.variant.stock, 5)  # unchanged

    def test_order_item_charges_the_variants_absolute_price_not_the_products_base_price(self):
        """قیچیِ ایرانی/ایتالیایی: OrderItem.unit_price باید قیمتِ مستقلِ
        تنوعِ انتخاب‌شده باشد — قبل از این وصله، همیشه product.final_price
        نوشته می‌شد و قیمتِ تنوع کاملاً نادیده گرفته می‌شد."""
        scissors = Product.objects.create(
            store=self.store, vendor=self.vendor, category=self.category, name="قیچی",
            slug="scissors-osv", sku="SKU-SCISSORS-OSV", price=Decimal("1"),
            product_type=Product.ProductType.VARIABLE, stock=0,
        )
        italian = ProductVariant.objects.create(
            product=scissors, store=self.store, attribute="کشور سازنده", value="ایتالیایی",
            price=Decimal("800000"), stock=4,
        )
        cart = Cart.objects.create(customer=self.customer)
        CartItem.objects.create(
            cart=cart, product=scissors, variant=italian, quantity=1, unit_price=Decimal("800000"),
        )
        order = create_order_from_cart(
            cart, customer=self.customer, vendor=self.vendor, address=self.address,
            shipping_method=self.shipping, payment_gateway=self.gateway, store=self.store,
        )
        order_item = order.items.get(variant=italian)
        self.assertEqual(order_item.unit_price, Decimal("800000"))
        self.assertEqual(order_item.line_total, Decimal("800000"))


class CancelOrderRestocksInventoryTests(TestCase):
    """نگاه کنید به ADR-31 — قبل از این PR، لغو سفارش هرگز موجودی را
    بازنمی‌گرداند."""

    def setUp(self):
        self.store = _akhlaghi()
        self.user = User.objects.create_user(username="reza", password="pass12345")
        self.staff = User.objects.create_user(username="admin-cr", password="pass12345", is_staff=True)
        self.customer = Customer.objects.create(user=self.user, full_name="رضا نوری", phone="09121230088")
        self.vendor = Vendor.objects.create(store=self.store, name="فروشگاه", slug="shop-cr")
        self.category = Category.objects.create(store=self.store, name="دیجیتال", slug="digital-cr")
        self.product = Product.objects.create(
            store=self.store, vendor=self.vendor, category=self.category, name="ماوس", slug="mouse-cr",
            sku="SKU-CR1", price=Decimal("300000"), stock=10,
        )
        self.shipping = ShippingMethod.objects.create(store=self.store, name="پست", slug="post-cr", cost=Decimal("45000"))
        self.gateway = PaymentGateway.objects.create(store=self.store, name="زرین‌پال", slug="zarin-cr")
        self.address = Address.objects.create(
            customer=self.customer, receiver_name="رضا نوری", phone="09121230088",
            province="تهران", city="تهران", postal_code="1111111111", full_address="خیابان انقلاب",
        )
        self.cart = Cart.objects.create(customer=self.customer)
        CartItem.objects.create(cart=self.cart, product=self.product, quantity=4, unit_price=self.product.final_price)
        self.order = create_order_from_cart(
            self.cart, customer=self.customer, vendor=self.vendor, address=self.address,
            shipping_method=self.shipping, payment_gateway=self.gateway, store=self.store,
        )

    def test_canceling_pending_order_restocks_product(self):
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 6)  # decremented on order creation

        change_order_status(self.order, Order.Status.CANCELED, by=self.staff, store=self.store)

        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 10)  # fully restored
        restock_movement = StockMovement.objects.filter(
            product=self.product, reason=StockMovement.Reason.ORDER_CANCELED,
        ).first()
        self.assertIsNotNone(restock_movement)
        self.assertEqual(restock_movement.delta, 4)
        self.assertEqual(restock_movement.order_id, self.order.pk)

    def test_canceling_processing_order_also_restocks(self):
        change_order_status(self.order, Order.Status.PROCESSING, store=self.store)
        change_order_status(self.order, Order.Status.CANCELED, store=self.store)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 10)

    def test_delivering_order_does_not_restock(self):
        change_order_status(self.order, Order.Status.PROCESSING, store=self.store)
        change_order_status(self.order, Order.Status.SHIPPED, store=self.store)
        change_order_status(self.order, Order.Status.DELIVERED, store=self.store)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 6)  # never restored — order fulfilled, not canceled


class ChangeOrderStatusTests(TestCase):
    def setUp(self):
        self.store = _akhlaghi()
        self.user = User.objects.create_user(username="mina", password="pass12345")
        self.staff = User.objects.create_user(username="admin1", password="pass12345", is_staff=True)
        self.customer = Customer.objects.create(user=self.user, full_name="مینا صادقی", phone="09129990000")
        self.vendor = Vendor.objects.create(store=self.store, name="فروشگاه", slug="shop-cs")
        self.shipping = ShippingMethod.objects.create(store=self.store, name="پست", slug="post-cs", cost=Decimal("45000"))
        self.gateway = PaymentGateway.objects.create(store=self.store, name="زرین‌پال", slug="zarin-cs")
        self.order = Order.objects.create(
            code="DM-55555", store=self.store, customer=self.customer, vendor=self.vendor, address={},
            shipping_method=self.shipping, payment_gateway=self.gateway,
            items_total=Decimal("100000"), grand_total=Decimal("100000"),
        )

    def test_pending_to_processing_is_allowed(self):
        change_order_status(self.order, Order.Status.PROCESSING, by=self.staff, note="تأیید شد", store=self.store)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.PROCESSING)
        history = self.order.status_history.latest("created_at")
        self.assertEqual(history.from_status, Order.Status.PENDING)
        self.assertEqual(history.to_status, Order.Status.PROCESSING)
        self.assertEqual(history.changed_by, self.staff)
        self.assertEqual(history.note, "تأیید شد")

    def test_full_happy_path_transition(self):
        change_order_status(self.order, Order.Status.PROCESSING, store=self.store)
        change_order_status(self.order, Order.Status.SHIPPED, store=self.store)
        change_order_status(self.order, Order.Status.DELIVERED, store=self.store)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.DELIVERED)
        self.assertEqual(self.order.status_history.count(), 3)

    def test_canceled_allowed_from_pending(self):
        change_order_status(self.order, Order.Status.CANCELED, store=self.store)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.CANCELED)

    def test_canceled_allowed_from_processing(self):
        change_order_status(self.order, Order.Status.PROCESSING, store=self.store)
        change_order_status(self.order, Order.Status.CANCELED, store=self.store)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.CANCELED)

    def test_skipping_a_stage_is_not_allowed(self):
        with self.assertRaises(ValueError):
            change_order_status(self.order, Order.Status.DELIVERED, store=self.store)

    def test_same_status_transition_raises(self):
        with self.assertRaises(ValueError):
            change_order_status(self.order, Order.Status.PENDING, store=self.store)

    def test_delivered_is_final(self):
        change_order_status(self.order, Order.Status.PROCESSING, store=self.store)
        change_order_status(self.order, Order.Status.SHIPPED, store=self.store)
        change_order_status(self.order, Order.Status.DELIVERED, store=self.store)
        with self.assertRaises(ValueError):
            change_order_status(self.order, Order.Status.CANCELED, store=self.store)

    def test_canceled_is_final(self):
        change_order_status(self.order, Order.Status.CANCELED, store=self.store)
        with self.assertRaises(ValueError):
            change_order_status(self.order, Order.Status.PROCESSING, store=self.store)

    def test_invalid_transition_does_not_create_history(self):
        count_before = OrderStatusHistory.objects.filter(order=self.order).count()
        with self.assertRaises(ValueError):
            change_order_status(self.order, Order.Status.DELIVERED, store=self.store)
        count_after = OrderStatusHistory.objects.filter(order=self.order).count()
        self.assertEqual(count_before, count_after)

    def test_processing_transition_sends_sms(self):
        SmsTemplate.ensure_defaults()
        with self.captureOnCommitCallbacks(execute=True):
            change_order_status(self.order, Order.Status.PROCESSING, store=self.store)
        self.assertTrue(
            SmsLog.objects.filter(event_key="order_processing", recipient=self.customer.phone).exists()
        )

    def test_shipped_transition_with_tracking_code_saves_it_and_includes_in_sms(self):
        SmsTemplate.ensure_defaults()
        change_order_status(self.order, Order.Status.PROCESSING, store=self.store)
        with self.captureOnCommitCallbacks(execute=True):
            change_order_status(self.order, Order.Status.SHIPPED, tracking_code="TRACK-999", store=self.store)
        self.order.refresh_from_db()
        self.assertEqual(self.order.tracking_code, "TRACK-999")
        log = SmsLog.objects.filter(event_key="order_shipped", recipient=self.customer.phone).first()
        self.assertIsNotNone(log)
        self.assertIn("TRACK-999", log.message)

    def test_shipped_transition_without_tracking_code_still_sends_sms(self):
        SmsTemplate.ensure_defaults()
        change_order_status(self.order, Order.Status.PROCESSING, store=self.store)
        with self.captureOnCommitCallbacks(execute=True):
            change_order_status(self.order, Order.Status.SHIPPED, store=self.store)
        self.assertTrue(SmsLog.objects.filter(event_key="order_shipped").exists())

    def test_delivered_transition_sends_sms(self):
        SmsTemplate.ensure_defaults()
        change_order_status(self.order, Order.Status.PROCESSING, store=self.store)
        change_order_status(self.order, Order.Status.SHIPPED, store=self.store)
        with self.captureOnCommitCallbacks(execute=True):
            change_order_status(self.order, Order.Status.DELIVERED, store=self.store)
        self.assertTrue(SmsLog.objects.filter(event_key="order_delivered").exists())

    def test_canceled_transition_sends_sms(self):
        SmsTemplate.ensure_defaults()
        with self.captureOnCommitCallbacks(execute=True):
            change_order_status(self.order, Order.Status.CANCELED, store=self.store)
        self.assertTrue(SmsLog.objects.filter(event_key="order_canceled").exists())
