from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.catalog.models import Category, Product, Vendor
from apps.customers.models import Customer
from apps.dashboard.services.report_service import (
    RANGE_DAYS,
    category_sales_breakdown,
    range_summary,
    sales_chart_for_range,
    top_customers_report,
    top_products_report,
)
from apps.orders.models import Order, OrderItem, PaymentGateway, ShippingMethod

User = get_user_model()


class ReportServiceTestCase(TestCase):
    def setUp(self):
        user = User.objects.create_user(username="09121190001", password="pass12345")
        self.customer = Customer.objects.create(user=user, full_name="آرش ولی‌زاده", phone="09121190001")
        self.vendor = Vendor.objects.create(name="فروشگاه", slug="shop-rs")
        self.main_cat = Category.objects.create(name="دیجیتال", slug="main-rs")
        self.category = Category.objects.create(name="موبایل", slug="sub-rs", parent=self.main_cat)
        self.product = Product.objects.create(
            vendor=self.vendor, category=self.category, name="گوشی", slug="phone-rs",
            sku="SKU-RS1", price=Decimal("1000000"), icon="📱",
        )
        self.shipping = ShippingMethod.objects.create(name="پست", slug="post-rs", cost=Decimal("45000"))
        self.gateway = PaymentGateway.objects.create(name="زرین‌پال", slug="zarin-rs")
        self.order = Order.objects.create(
            code="DM-rs1", customer=self.customer, vendor=self.vendor, address={},
            shipping_method=self.shipping, payment_gateway=self.gateway,
            grand_total=Decimal("1000000"), payment_status=Order.PaymentStatus.PAID,
        )
        OrderItem.objects.create(
            order=self.order, product=self.product, product_name=self.product.name,
            quantity=2, unit_price=Decimal("1000000"), line_total=Decimal("2000000"),
        )


class RangeSummaryTests(ReportServiceTestCase):
    def test_total_sales_only_counts_paid_orders(self):
        summary = range_summary("30")
        self.assertEqual(summary["total_sales"], Decimal("1000000"))
        self.assertEqual(summary["order_count"], 1)
        self.assertEqual(summary["avg_order_value"], Decimal("1000000"))

    def test_out_of_range_orders_excluded(self):
        old_order = Order.objects.create(
            code="DM-rs-old", customer=self.customer, vendor=self.vendor, address={},
            shipping_method=self.shipping, payment_gateway=self.gateway,
            grand_total=Decimal("500000"), payment_status=Order.PaymentStatus.PAID,
        )
        old_order.created_at = timezone.now() - timezone.timedelta(days=40)
        old_order.save(update_fields=["created_at"])
        summary = range_summary("30")
        self.assertEqual(summary["total_sales"], Decimal("1000000"))


class SalesChartForRangeTests(ReportServiceTestCase):
    def test_all_supported_ranges_return_data_and_labels(self):
        for key in RANGE_DAYS:
            data, labels = sales_chart_for_range(key)
            self.assertTrue(len(data) > 0)
            self.assertEqual(len(data), len(labels))


class CategorySalesBreakdownTests(ReportServiceTestCase):
    def test_breakdown_attributes_sales_to_top_level_category(self):
        rows = category_sales_breakdown("30")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["name"], "دیجیتال")
        self.assertEqual(rows[0]["amount"], Decimal("2000000"))
        self.assertEqual(rows[0]["pct"], 100)

    def test_canceled_orders_excluded(self):
        self.order.status = Order.Status.CANCELED
        self.order.save(update_fields=["status"])
        rows = category_sales_breakdown("30")
        self.assertEqual(rows, [])


class TopProductsReportTests(ReportServiceTestCase):
    def test_returns_ordered_products(self):
        rows = top_products_report("30")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["product__name"], "گوشی")
        self.assertEqual(rows[0]["total_sold"], 2)


class TopCustomersReportTests(ReportServiceTestCase):
    def test_returns_customer_with_paid_total(self):
        rows = top_customers_report("30")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["customer__full_name"], "آرش ولی‌زاده")
        self.assertEqual(rows[0]["total_spent"], Decimal("1000000"))
