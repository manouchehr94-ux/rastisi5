from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import TestCase

from apps.catalog.models import Category, Product, Vendor
from apps.customers.models import Customer

from .models import Order, OrderItem, OrderStatusHistory, PaymentGateway, ShippingMethod, Transaction

User = get_user_model()


class OrdersModelsTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="reza", password="pass12345")
        self.customer = Customer.objects.create(user=self.user, full_name="رضا محمدی", phone="09123334455")
        self.vendor = Vendor.objects.create(name="فروشگاه", slug="shop-o")
        self.category = Category.objects.create(name="کفش", slug="shoes-o")
        self.product = Product.objects.create(
            vendor=self.vendor, category=self.category, name="کتانی", slug="sneaker-o",
            sku="SKU-O1", price=Decimal("2000000"),
        )
        self.shipping = ShippingMethod.objects.create(name="پست پیشتاز", slug="post-o", cost=45_000)
        self.gateway = PaymentGateway.objects.create(name="زرین‌پال", slug="zarin-o")

    def _make_order(self, code="DM-10001"):
        return Order.objects.create(
            code=code,
            customer=self.customer,
            vendor=self.vendor,
            address={"receiver_name": "رضا محمدی", "city": "تهران"},
            shipping_method=self.shipping,
            payment_gateway=self.gateway,
            items_total=Decimal("2000000"),
            shipping_cost=Decimal("45000"),
            tax=Decimal("180000"),
            grand_total=Decimal("2225000"),
        )

    def test_order_creation_defaults(self):
        order = self._make_order()
        self.assertEqual(order.status, Order.Status.PENDING)
        self.assertEqual(order.payment_status, Order.PaymentStatus.PENDING)
        self.assertEqual(order.get_status_display(), "در انتظار")

    def test_order_code_must_be_unique(self):
        self._make_order()
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                self._make_order()

    def test_order_item_line_total(self):
        order = self._make_order()
        item = OrderItem.objects.create(
            order=order, product=self.product, product_name=self.product.name,
            quantity=2, unit_price=Decimal("2000000"), line_total=Decimal("4000000"),
        )
        self.assertEqual(order.items.count(), 1)
        self.assertEqual(item.line_total, item.quantity * item.unit_price)

    def test_order_status_history_created(self):
        order = self._make_order()
        history = OrderStatusHistory.objects.create(
            order=order, from_status="", to_status=Order.Status.PENDING, changed_by=self.user
        )
        self.assertIn(history, order.status_history.all())

    def test_transaction_code_must_be_unique(self):
        order = self._make_order()
        Transaction.objects.create(
            code="TX-90001", order=order, gateway=self.gateway, amount=order.grand_total,
            status=Transaction.Status.OK,
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Transaction.objects.create(
                    code="TX-90001", order=order, gateway=self.gateway, amount=order.grand_total,
                )
