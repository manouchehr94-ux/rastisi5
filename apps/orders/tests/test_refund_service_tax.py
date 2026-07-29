from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.catalog.models import Category, Product, Vendor
from apps.customers.models import Customer
from apps.orders.models import Order, OrderItem, PaymentGateway, ShippingMethod
from apps.orders.services.refund_service import (
    RefundError,
    execute_order_refund,
    plan_order_refund,
    refunded_shipping_tax_total,
)
from apps.stores.models import Store

User = get_user_model()


def _akhlaghi():
    return Store.objects.get(slug="akhlaghi")


class RefundTaxTestCase(TestCase):
    """سفارشی با مالیاتِ کالا و مالیاتِ ارسال — دقیقاً همان اسنپ‌شاتی که
    order_service امروز روی Order/OrderItem می‌نویسد (checkpoint 3B)."""

    def setUp(self):
        self.store = _akhlaghi()
        self.user = User.objects.create_user(username="09121350001", password="pass12345")
        self.staff = User.objects.create_user(username="09121350099", password="pass12345", is_staff=True)
        self.customer = Customer.objects.create(user=self.user, full_name="کیانا رستمی", phone="09121350001")
        self.vendor = Vendor.objects.create(store=self.store, name="فروشگاه", slug="shop-rft")
        self.category = Category.objects.create(store=self.store, name="دیجیتال", slug="digital-rft")
        self.product = Product.objects.create(
            store=self.store, vendor=self.vendor, category=self.category, name="اسپیکر", slug="speaker-rft",
            sku="SKU-RFT1", price=Decimal("500000"), stock=20,
        )
        self.shipping = ShippingMethod.objects.create(store=self.store, name="پست", slug="post-rft", cost=Decimal("50000"))
        self.gateway = PaymentGateway.objects.create(store=self.store, name="زرین‌پال", slug="zarin-rft")
        # جمع: کالا ۱,۰۰۰,۰۰۰ + مالیاتِ کالا ۹۰,۰۰۰ (۹٪) + ارسال ۵۰,۰۰۰ + مالیاتِ ارسال ۴,۵۰۰ = ۱,۱۴۴,۵۰۰
        self.order = Order.objects.create(
            code="DM-RFT1", store=self.store, customer=self.customer, vendor=self.vendor, address={},
            shipping_method=self.shipping, payment_gateway=self.gateway,
            items_total=Decimal("1000000"), shipping_cost=Decimal("50000"), tax=Decimal("90000"),
            shipping_tax=Decimal("4500"), grand_total=Decimal("1144500"),
            payment_status=Order.PaymentStatus.PAID,
        )
        self.item = OrderItem.objects.create(
            order=self.order, product=self.product, product_name=self.product.name,
            quantity=2, unit_price=Decimal("500000"), line_total=Decimal("1000000"),
            taxable_amount=Decimal("1000000"), tax_rate_percent=Decimal("9"),
            unit_tax=Decimal("45000"), total_tax=Decimal("90000"),
        )

    def _refund(self, quantity, shipping_amount=Decimal("0")):
        return execute_order_refund(
            self.order, store=self.store, actor=self.staff,
            line_requests=[{"order_item_id": self.item.pk, "quantity": quantity}] if quantity else [],
            shipping_amount=shipping_amount,
        )


class RefundLineTaxTests(RefundTaxTestCase):
    def test_full_quantity_refund_includes_full_item_tax(self):
        refund = self._refund(2)
        self.assertEqual(refund.approved_amount, Decimal("1090000"))  # 1,000,000 + 90,000 tax
        refund_item = refund.items.first()
        self.assertEqual(refund_item.tax_amount, Decimal("90000"))

    def test_partial_quantity_refund_prorates_tax(self):
        refund = self._refund(1)
        refund_item = refund.items.first()
        self.assertEqual(refund_item.amount, Decimal("500000"))
        self.assertEqual(refund_item.tax_amount, Decimal("45000"))  # half of 90,000

    def test_second_partial_refund_cannot_exceed_remaining_tax(self):
        self._refund(1)
        second = self._refund(1)
        second_item = second.items.first()
        self.assertEqual(second_item.tax_amount, Decimal("45000"))

    def test_double_refund_of_same_quantity_rejected(self):
        self._refund(2)
        with self.assertRaises(RefundError):
            self._refund(1)


class RefundShippingTaxTests(RefundTaxTestCase):
    def test_full_shipping_refund_includes_full_shipping_tax(self):
        refund = self._refund(0, shipping_amount=Decimal("50000"))
        self.assertEqual(refund.shipping_tax_refund_amount, Decimal("4500"))

    def test_partial_shipping_refund_prorates_shipping_tax(self):
        refund = self._refund(0, shipping_amount=Decimal("25000"))
        self.assertEqual(refund.shipping_tax_refund_amount, Decimal("2250"))

    def test_shipping_tax_not_refunded_twice(self):
        self._refund(0, shipping_amount=Decimal("50000"))
        self.assertEqual(refunded_shipping_tax_total(self.order), Decimal("4500"))
        with self.assertRaises(RefundError):
            self._refund(0, shipping_amount=Decimal("1"))


class RefundPlanTaxIntegrityTests(RefundTaxTestCase):
    def test_plan_total_amount_includes_tax_and_shipping_tax(self):
        plan = plan_order_refund(
            self.order, store=self.store,
            line_requests=[{"order_item_id": self.item.pk, "quantity": 2}],
            shipping_amount=Decimal("50000"),
        )
        self.assertEqual(plan.total_amount, Decimal("1144500"))  # full grand_total

    def test_full_refund_exhausts_refundable_amount_including_tax(self):
        self._refund(2, shipping_amount=Decimal("50000"))
        from apps.orders.services.refund_service import refundable_amount
        self.assertEqual(refundable_amount(self.order), Decimal("0"))

    def test_refund_cannot_exceed_grand_total_via_tax_padding(self):
        with self.assertRaises(RefundError):
            plan_order_refund(
                self.order, store=self.store,
                line_requests=[{"order_item_id": self.item.pk, "quantity": 2}],
                shipping_amount=Decimal("99999999"),
            )

    def test_current_tax_rate_change_does_not_alter_historical_refund(self):
        """تغییرِ نرخِ مالیاتِ فعلیِ Store نباید محاسبه‌ی استردادِ این سفارشِ
        قدیمی را عوض کند — مالیاتِ استرداد همیشه از رویِ اسنپ‌شاتِ
        OrderItem.unit_tax محاسبه می‌شود، نه نرخِ فعلی."""
        from apps.core.models import ShopSettings
        settings_row = ShopSettings.load(store=self.store)
        settings_row.tax_percent = Decimal("50")
        settings_row.save(update_fields=["tax_percent"])

        refund = self._refund(2)
        refund_item = refund.items.first()
        self.assertEqual(refund_item.tax_amount, Decimal("90000"))  # unchanged by the new 50% rate
