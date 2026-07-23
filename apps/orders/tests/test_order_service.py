from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db import transaction
from django.test import TestCase

from apps.cart.models import Cart, CartItem, Coupon
from apps.catalog.models import Category, Product, Vendor
from apps.customers.models import Address, Customer
from apps.orders.models import Order, OrderStatusHistory, PaymentGateway, ShippingMethod
from apps.orders.services.order_service import change_order_status, create_order_from_cart
from apps.sms.models import SmsLog, SmsTemplate

User = get_user_model()


class CreateOrderFromCartTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="hasan", password="pass12345")
        self.customer = Customer.objects.create(user=self.user, full_name="حسن کریمی", phone="09121230000")
        self.vendor = Vendor.objects.create(name="فروشگاه", slug="shop-os")
        self.category = Category.objects.create(name="دیجیتال", slug="digital-os")
        self.product = Product.objects.create(
            vendor=self.vendor, category=self.category, name="هدفون", slug="headphone-os",
            sku="SKU-OS1", price=Decimal("1000000"), discount_percent=10, stock=10,
        )
        self.shipping = ShippingMethod.objects.create(name="پست", slug="post-os", cost=Decimal("45000"))
        self.gateway = PaymentGateway.objects.create(name="زرین‌پال", slug="zarin-os")
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
                shipping_method=self.shipping, payment_gateway=self.gateway,
            )

    def test_create_order_increments_coupon_used_count_when_applied(self):
        coupon = Coupon.objects.create(code="STYLE20", type=Coupon.Type.PERCENT, value=20)
        self._create(coupon=coupon)
        coupon.refresh_from_db()
        self.assertEqual(coupon.used_count, 1)

    def test_create_order_does_not_increment_coupon_used_count_when_not_applicable(self):
        coupon = Coupon.objects.create(
            code="BIG500", type=Coupon.Type.FIXED, value=100_000, min_order=Decimal("5000000")
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


class ChangeOrderStatusTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="mina", password="pass12345")
        self.staff = User.objects.create_user(username="admin1", password="pass12345", is_staff=True)
        self.customer = Customer.objects.create(user=self.user, full_name="مینا صادقی", phone="09129990000")
        self.vendor = Vendor.objects.create(name="فروشگاه", slug="shop-cs")
        self.shipping = ShippingMethod.objects.create(name="پست", slug="post-cs", cost=Decimal("45000"))
        self.gateway = PaymentGateway.objects.create(name="زرین‌پال", slug="zarin-cs")
        self.order = Order.objects.create(
            code="DM-55555", customer=self.customer, vendor=self.vendor, address={},
            shipping_method=self.shipping, payment_gateway=self.gateway,
            items_total=Decimal("100000"), grand_total=Decimal("100000"),
        )

    def test_pending_to_processing_is_allowed(self):
        change_order_status(self.order, Order.Status.PROCESSING, by=self.staff, note="تأیید شد")
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.PROCESSING)
        history = self.order.status_history.latest("created_at")
        self.assertEqual(history.from_status, Order.Status.PENDING)
        self.assertEqual(history.to_status, Order.Status.PROCESSING)
        self.assertEqual(history.changed_by, self.staff)
        self.assertEqual(history.note, "تأیید شد")

    def test_full_happy_path_transition(self):
        change_order_status(self.order, Order.Status.PROCESSING)
        change_order_status(self.order, Order.Status.SHIPPED)
        change_order_status(self.order, Order.Status.DELIVERED)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.DELIVERED)
        self.assertEqual(self.order.status_history.count(), 3)

    def test_canceled_allowed_from_pending(self):
        change_order_status(self.order, Order.Status.CANCELED)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.CANCELED)

    def test_canceled_allowed_from_processing(self):
        change_order_status(self.order, Order.Status.PROCESSING)
        change_order_status(self.order, Order.Status.CANCELED)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.CANCELED)

    def test_skipping_a_stage_is_not_allowed(self):
        with self.assertRaises(ValueError):
            change_order_status(self.order, Order.Status.DELIVERED)

    def test_same_status_transition_raises(self):
        with self.assertRaises(ValueError):
            change_order_status(self.order, Order.Status.PENDING)

    def test_delivered_is_final(self):
        change_order_status(self.order, Order.Status.PROCESSING)
        change_order_status(self.order, Order.Status.SHIPPED)
        change_order_status(self.order, Order.Status.DELIVERED)
        with self.assertRaises(ValueError):
            change_order_status(self.order, Order.Status.CANCELED)

    def test_canceled_is_final(self):
        change_order_status(self.order, Order.Status.CANCELED)
        with self.assertRaises(ValueError):
            change_order_status(self.order, Order.Status.PROCESSING)

    def test_invalid_transition_does_not_create_history(self):
        count_before = OrderStatusHistory.objects.filter(order=self.order).count()
        with self.assertRaises(ValueError):
            change_order_status(self.order, Order.Status.DELIVERED)
        count_after = OrderStatusHistory.objects.filter(order=self.order).count()
        self.assertEqual(count_before, count_after)

    def test_processing_transition_sends_sms(self):
        SmsTemplate.ensure_defaults()
        with self.captureOnCommitCallbacks(execute=True):
            change_order_status(self.order, Order.Status.PROCESSING)
        self.assertTrue(
            SmsLog.objects.filter(event_key="order_processing", recipient=self.customer.phone).exists()
        )

    def test_shipped_transition_with_tracking_code_saves_it_and_includes_in_sms(self):
        SmsTemplate.ensure_defaults()
        change_order_status(self.order, Order.Status.PROCESSING)
        with self.captureOnCommitCallbacks(execute=True):
            change_order_status(self.order, Order.Status.SHIPPED, tracking_code="TRACK-999")
        self.order.refresh_from_db()
        self.assertEqual(self.order.tracking_code, "TRACK-999")
        log = SmsLog.objects.filter(event_key="order_shipped", recipient=self.customer.phone).first()
        self.assertIsNotNone(log)
        self.assertIn("TRACK-999", log.message)

    def test_shipped_transition_without_tracking_code_still_sends_sms(self):
        SmsTemplate.ensure_defaults()
        change_order_status(self.order, Order.Status.PROCESSING)
        with self.captureOnCommitCallbacks(execute=True):
            change_order_status(self.order, Order.Status.SHIPPED)
        self.assertTrue(SmsLog.objects.filter(event_key="order_shipped").exists())

    def test_delivered_transition_sends_sms(self):
        SmsTemplate.ensure_defaults()
        change_order_status(self.order, Order.Status.PROCESSING)
        change_order_status(self.order, Order.Status.SHIPPED)
        with self.captureOnCommitCallbacks(execute=True):
            change_order_status(self.order, Order.Status.DELIVERED)
        self.assertTrue(SmsLog.objects.filter(event_key="order_delivered").exists())

    def test_canceled_transition_sends_sms(self):
        SmsTemplate.ensure_defaults()
        with self.captureOnCommitCallbacks(execute=True):
            change_order_status(self.order, Order.Status.CANCELED)
        self.assertTrue(SmsLog.objects.filter(event_key="order_canceled").exists())
