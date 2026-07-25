from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.catalog.models import Category, Product, Vendor
from apps.customers.models import Customer
from apps.orders.models import Order, OrderItem, PaymentGateway, ShippingMethod
from apps.dashboard.services import dashboard_service
from apps.stores.models import Store

User = get_user_model()


def _akhlaghi():
    return Store.objects.get(slug="akhlaghi")


class SalesChartDataTests(TestCase):
    def setUp(self):
        self.store = _akhlaghi()
        vendor = Vendor.objects.create(store=self.store, name="فروشگاه", slug="shop-scd")
        category = Category.objects.create(store=self.store, name="دیجیتال", slug="digital-scd")
        self.product = Product.objects.create(
            store=self.store, vendor=vendor, category=category, name="کالای نمونه", slug="sample-scd",
            sku="SKU-SCD1", price=Decimal("100000"),
        )
        user = User.objects.create_user(username="09121120001", password="pass12345")
        self.customer = Customer.objects.create(user=user, full_name="مشتری تست", phone="09121120001")
        self.shipping = ShippingMethod.objects.create(name="پست", slug="post-scd", cost=Decimal("0"))
        self.gateway = PaymentGateway.objects.create(name="زرین‌پال", slug="zarin-scd")

    def _make_paid_order(self, amount, when=None):
        order = Order.objects.create(
            code=f"DM-{Order.objects.count() + 90000}", customer=self.customer, vendor=self.product.vendor,
            address={}, shipping_method=self.shipping, payment_gateway=self.gateway,
            grand_total=Decimal(amount), payment_status=Order.PaymentStatus.PAID,
        )
        if when is not None:
            Order.objects.filter(pk=order.pk).update(created_at=when)
        return order

    def test_week_range_has_seven_points_including_today(self):
        self._make_paid_order(150000, when=timezone.now())
        data, labels = dashboard_service.sales_chart_data("week")
        self.assertEqual(len(data), 7)
        self.assertEqual(len(labels), 7)
        self.assertEqual(data[-1], 150000.0)

    def test_month_range_has_thirty_points(self):
        data, labels = dashboard_service.sales_chart_data("month")
        self.assertEqual(len(data), 30)
        self.assertEqual(len(labels), 30)

    def test_year_range_has_twelve_points_ending_current_month(self):
        self._make_paid_order(200000, when=timezone.now())
        data, labels = dashboard_service.sales_chart_data("year")
        self.assertEqual(len(data), 12)
        self.assertEqual(data[-1], 200000.0)

    def test_unpaid_orders_are_excluded_from_sales(self):
        Order.objects.create(
            code="DM-91111", customer=self.customer, vendor=self.product.vendor, address={},
            shipping_method=self.shipping, payment_gateway=self.gateway,
            grand_total=Decimal("999999"), payment_status=Order.PaymentStatus.PENDING,
        )
        data, _ = dashboard_service.sales_chart_data("week")
        self.assertEqual(sum(data), 0)

    def test_default_range_falls_back_to_month(self):
        data, labels = dashboard_service.sales_chart_data("bogus")
        self.assertEqual(len(data), 30)


class OrderStatusBreakdownTests(TestCase):
    def setUp(self):
        self.store = _akhlaghi()
        vendor = Vendor.objects.create(store=self.store, name="فروشگاه", slug="shop-osb")
        category = Category.objects.create(store=self.store, name="دیجیتال", slug="digital-osb")
        self.product = Product.objects.create(
            store=self.store, vendor=vendor, category=category, name="کالا", slug="sample-osb",
            sku="SKU-OSB1", price=Decimal("1000"),
        )
        user = User.objects.create_user(username="09121120002", password="pass12345")
        self.customer = Customer.objects.create(user=user, full_name="م", phone="09121120002")
        self.shipping = ShippingMethod.objects.create(name="پست", slug="post-osb", cost=0)
        self.gateway = PaymentGateway.objects.create(name="زرین‌پال", slug="zarin-osb")

    def _order(self, status, code):
        return Order.objects.create(
            code=code, customer=self.customer, vendor=self.product.vendor, address={},
            shipping_method=self.shipping, payment_gateway=self.gateway,
            grand_total=Decimal("1000"), status=status,
        )

    def test_counts_orders_by_status_for_current_month(self):
        self._order(Order.Status.PENDING, "DM-92001")
        self._order(Order.Status.PENDING, "DM-92002")
        self._order(Order.Status.DELIVERED, "DM-92003")
        counts = dashboard_service.order_status_breakdown()
        self.assertEqual(counts[Order.Status.PENDING], 2)
        self.assertEqual(counts[Order.Status.DELIVERED], 1)
        self.assertEqual(counts[Order.Status.CANCELED], 0)

    def test_orders_outside_current_month_are_excluded(self):
        order = self._order(Order.Status.DELIVERED, "DM-92004")
        Order.objects.filter(pk=order.pk).update(created_at=timezone.now() - timedelta(days=60))
        counts = dashboard_service.order_status_breakdown()
        self.assertEqual(counts[Order.Status.DELIVERED], 0)


class TopSellingProductsTests(TestCase):
    def setUp(self):
        self.store = _akhlaghi()
        vendor = Vendor.objects.create(store=self.store, name="فروشگاه", slug="shop-tsp")
        category = Category.objects.create(store=self.store, name="دیجیتال", slug="digital-tsp")
        self.p1 = Product.objects.create(
            store=self.store, vendor=vendor, category=category, name="کالای پرفروش", slug="best-tsp",
            sku="SKU-TSP1", price=Decimal("50000"),
        )
        self.p2 = Product.objects.create(
            store=self.store, vendor=vendor, category=category, name="کالای کم‌فروش", slug="worst-tsp",
            sku="SKU-TSP2", price=Decimal("50000"),
        )
        user = User.objects.create_user(username="09121120003", password="pass12345")
        self.customer = Customer.objects.create(user=user, full_name="م", phone="09121120003")
        self.shipping = ShippingMethod.objects.create(name="پست", slug="post-tsp", cost=0)
        self.gateway = PaymentGateway.objects.create(name="زرین‌پال", slug="zarin-tsp")

    def _order_with_item(self, product, quantity, status=Order.Status.DELIVERED, days_ago=1):
        order = Order.objects.create(
            code=f"DM-{93000 + Order.objects.count()}", customer=self.customer, vendor=product.vendor,
            address={}, shipping_method=self.shipping, payment_gateway=self.gateway,
            grand_total=Decimal("1000"), status=status,
        )
        Order.objects.filter(pk=order.pk).update(created_at=timezone.now() - timedelta(days=days_ago))
        OrderItem.objects.create(
            order=order, product=product, product_name=product.name,
            quantity=quantity, unit_price=Decimal("50000"), line_total=Decimal("50000") * quantity,
        )
        return order

    def test_ranks_products_by_quantity_sold(self):
        self._order_with_item(self.p1, 5)
        self._order_with_item(self.p2, 2)
        top = dashboard_service.top_selling_products()
        self.assertEqual(top[0]["product_id"], self.p1.id)
        self.assertEqual(top[0]["total_sold"], 5)
        self.assertEqual(top[0]["progress_pct"], 100)
        self.assertEqual(top[1]["progress_pct"], 40)

    def test_excludes_canceled_orders(self):
        self._order_with_item(self.p1, 5, status=Order.Status.CANCELED)
        top = dashboard_service.top_selling_products()
        self.assertEqual(top, [])

    def test_excludes_items_older_than_window(self):
        self._order_with_item(self.p1, 5, days_ago=45)
        top = dashboard_service.top_selling_products(days=30)
        self.assertEqual(top, [])


class LowStockProductsTests(TestCase):
    def setUp(self):
        self.store = _akhlaghi()
        self.vendor = Vendor.objects.create(store=self.store, name="فروشگاه", slug="shop-lsp")
        self.parent = Category.objects.create(store=self.store, name="خانه", slug="home-lsp")
        self.child = Category.objects.create(store=self.store, name="آشپزخانه", slug="kitchen-lsp", parent=self.parent)

    def test_zero_stock_is_out_of_stock_badge(self):
        Product.objects.create(
            store=self.store, vendor=self.vendor, category=self.child, name="کالای ناموجود", slug="out-lsp",
            sku="SKU-LSP1", price=Decimal("1000"), stock=0,
        )
        rows = dashboard_service.low_stock_products()
        self.assertEqual(rows[0]["badge_label"], "ناموجود")
        self.assertEqual(rows[0]["category_chain"], "خانه › آشپزخانه")

    def test_critical_vs_low_thresholds(self):
        Product.objects.create(
            store=self.store, vendor=self.vendor, category=self.child, name="بحرانی", slug="critical-lsp",
            sku="SKU-LSP2", price=Decimal("1000"), stock=3,
        )
        Product.objects.create(
            store=self.store, vendor=self.vendor, category=self.child, name="رو به اتمام", slug="low-lsp",
            sku="SKU-LSP3", price=Decimal("1000"), stock=8,
        )
        rows = {row["product"].slug: row["badge_label"] for row in dashboard_service.low_stock_products()}
        self.assertEqual(rows["critical-lsp"], "بحرانی")
        self.assertEqual(rows["low-lsp"], "رو به اتمام")

    def test_products_above_threshold_are_excluded(self):
        Product.objects.create(
            store=self.store, vendor=self.vendor, category=self.child, name="موجودی کافی", slug="plenty-lsp",
            sku="SKU-LSP4", price=Decimal("1000"), stock=50,
        )
        rows = dashboard_service.low_stock_products()
        self.assertEqual(rows, [])


class StatCardsTests(TestCase):
    def test_no_previous_data_yields_none_trend(self):
        cards = dashboard_service.stat_cards()
        self.assertIsNone(cards["today_sales_trend"])
        self.assertIsNone(cards["today_orders_trend"])

    def test_low_stock_count_reflects_threshold(self):
        store = _akhlaghi()
        vendor = Vendor.objects.create(store=store, name="فروشگاه", slug="shop-sct")
        category = Category.objects.create(store=store, name="دیجیتال", slug="digital-sct")
        Product.objects.create(
            store=store, vendor=vendor, category=category, name="کم‌موجودی", slug="low-sct",
            sku="SKU-SCT1", price=Decimal("1000"), stock=5,
        )
        Product.objects.create(
            store=store, vendor=vendor, category=category, name="پرموجودی", slug="high-sct",
            sku="SKU-SCT2", price=Decimal("1000"), stock=500,
        )
        cards = dashboard_service.stat_cards()
        self.assertEqual(cards["low_stock_count"], 1)
