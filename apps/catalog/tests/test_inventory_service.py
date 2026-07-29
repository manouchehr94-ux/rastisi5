from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.catalog.models import Category, Product, ProductVariant, StockMovement, Vendor
from apps.catalog.services.inventory_service import (
    InsufficientStockError,
    adjust_stock_manually,
    decrement_stock_for_order_item,
    list_stock_movements,
    restock_order,
)
from apps.customers.models import Address, Customer
from apps.orders.models import Order, PaymentGateway, ShippingMethod
from apps.stores.models import Store

User = get_user_model()


def _akhlaghi():
    return Store.objects.get(slug="akhlaghi")


class InventoryServiceTestCase(TestCase):
    def setUp(self):
        self.store = _akhlaghi()
        self.vendor = Vendor.objects.create(store=self.store, name="فروشگاه", slug="shop-inv")
        self.category = Category.objects.create(store=self.store, name="لوازم", slug="gear-inv")
        self.product = Product.objects.create(
            store=self.store, vendor=self.vendor, category=self.category, name="کیف پول", slug="wallet-inv",
            sku="SKU-INV1", price=Decimal("200000"), stock=10,
        )
        self.actor = User.objects.create_user(username="09121199001", password="pass12345", is_staff=True)


class DecrementStockForOrderItemTests(InventoryServiceTestCase):
    def test_decrements_product_stock_when_no_variant(self):
        decrement_stock_for_order_item(store=self.store, product=self.product, variant=None, quantity=3, order=None)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 7)
        movement = StockMovement.objects.get(product=self.product)
        self.assertEqual(movement.delta, -3)
        self.assertEqual(movement.stock_before, 10)
        self.assertEqual(movement.stock_after, 7)
        self.assertIsNone(movement.variant)

    def test_decrements_variant_stock_when_variant_given(self):
        variant = ProductVariant.objects.create(
            product=self.product, store=self.store, attribute="رنگ", value="قرمز", stock=6,
        )
        decrement_stock_for_order_item(store=self.store, product=self.product, variant=variant, quantity=4, order=None)
        variant.refresh_from_db()
        self.product.refresh_from_db()
        self.assertEqual(variant.stock, 2)
        self.assertEqual(self.product.stock, 10)  # untouched
        movement = StockMovement.objects.get(variant=variant)
        self.assertEqual(movement.delta, -4)

    def test_raises_when_insufficient(self):
        with self.assertRaises(InsufficientStockError):
            decrement_stock_for_order_item(store=self.store, product=self.product, variant=None, quantity=999, order=None)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 10)
        self.assertFalse(StockMovement.objects.filter(product=self.product).exists())


class RestockOrderTests(InventoryServiceTestCase):
    def setUp(self):
        super().setUp()
        self.customer = Customer.objects.create(user=self.actor, full_name="آرش رضایی", phone="09121199002")
        self.shipping = ShippingMethod.objects.create(store=self.store, name="پست", slug="post-inv", cost=Decimal("45000"))
        self.gateway = PaymentGateway.objects.create(store=self.store, name="زرین‌پال", slug="zarin-inv")
        self.order = Order.objects.create(
            code="DM-INV1", store=self.store, customer=self.customer, vendor=self.vendor, address={},
            shipping_method=self.shipping, payment_gateway=self.gateway,
            items_total=Decimal("400000"), grand_total=Decimal("400000"),
        )

    def test_restocks_simple_product_item(self):
        decrement_stock_for_order_item(store=self.store, product=self.product, variant=None, quantity=3, order=self.order)
        self.order.items.create(
            product=self.product, product_name=self.product.name, quantity=3,
            unit_price=Decimal("200000"), line_total=Decimal("600000"),
        )
        restock_order(store=self.store, order=self.order, actor=self.actor)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 10)
        restock_movement = StockMovement.objects.filter(product=self.product, reason=StockMovement.Reason.ORDER_CANCELED).first()
        self.assertIsNotNone(restock_movement)
        self.assertEqual(restock_movement.delta, 3)

    def test_restocks_variant_item(self):
        variant = ProductVariant.objects.create(
            product=self.product, store=self.store, attribute="سایز", value="متوسط", stock=5,
        )
        decrement_stock_for_order_item(store=self.store, product=self.product, variant=variant, quantity=2, order=self.order)
        self.order.items.create(
            product=self.product, variant=variant, product_name=self.product.name, quantity=2,
            unit_price=Decimal("200000"), line_total=Decimal("400000"),
        )
        restock_order(store=self.store, order=self.order, actor=self.actor)
        variant.refresh_from_db()
        self.assertEqual(variant.stock, 5)

    def test_no_items_is_a_safe_noop(self):
        restock_order(store=self.store, order=self.order, actor=self.actor)
        self.assertFalse(StockMovement.objects.filter(order=self.order).exists())

    def test_skips_item_whose_product_was_deleted(self):
        self.order.items.create(
            product=None, product_name="کالای حذف‌شده", quantity=2,
            unit_price=Decimal("200000"), line_total=Decimal("400000"),
        )
        # must not raise despite product_id being None
        restock_order(store=self.store, order=self.order, actor=self.actor)


class AdjustStockManuallyTests(InventoryServiceTestCase):
    def test_increases_stock_and_records_positive_delta(self):
        movement = adjust_stock_manually(store=self.store, product=self.product, new_stock=15, actor=self.actor, note="شمارش انبار")
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 15)
        self.assertEqual(movement.delta, 5)
        self.assertEqual(movement.reason, StockMovement.Reason.MANUAL_ADJUSTMENT)
        self.assertEqual(movement.note, "شمارش انبار")

    def test_decreases_stock_and_records_negative_delta(self):
        movement = adjust_stock_manually(store=self.store, product=self.product, new_stock=4, actor=self.actor)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 4)
        self.assertEqual(movement.delta, -6)

    def test_no_change_returns_none_and_writes_nothing(self):
        result = adjust_stock_manually(store=self.store, product=self.product, new_stock=10, actor=self.actor)
        self.assertIsNone(result)
        self.assertFalse(StockMovement.objects.filter(product=self.product).exists())

    def test_negative_stock_rejected(self):
        with self.assertRaises(ValueError):
            adjust_stock_manually(store=self.store, product=self.product, new_stock=-1, actor=self.actor)

    def test_adjusts_variant_stock_when_given(self):
        variant = ProductVariant.objects.create(
            product=self.product, store=self.store, attribute="رنگ", value="آبی", stock=3,
        )
        movement = adjust_stock_manually(store=self.store, product=self.product, variant=variant, new_stock=8, actor=self.actor)
        variant.refresh_from_db()
        self.product.refresh_from_db()
        self.assertEqual(variant.stock, 8)
        self.assertEqual(self.product.stock, 10)  # untouched
        self.assertEqual(movement.variant, variant)


class ListStockMovementsTests(InventoryServiceTestCase):
    def test_filters_by_store(self):
        other_store = Store.objects.create(name="فروشگاه دیگر", slug="inv-other", status=Store.Status.ACTIVE)
        other_vendor = Vendor.objects.create(store=other_store, name="فروشگاه دیگر", slug="shop-inv-other")
        other_category = Category.objects.create(store=other_store, name="لوازم", slug="gear-inv-other")
        other_product = Product.objects.create(
            store=other_store, vendor=other_vendor, category=other_category, name="کیف پول ۲", slug="wallet-inv-2",
            sku="SKU-INV2", price=Decimal("200000"), stock=10,
        )
        decrement_stock_for_order_item(store=self.store, product=self.product, variant=None, quantity=1, order=None)
        decrement_stock_for_order_item(store=other_store, product=other_product, variant=None, quantity=1, order=None)
        movements = list_stock_movements(self.store)
        self.assertEqual(movements.count(), 1)
        self.assertEqual(movements.first().product_id, self.product.pk)

    def test_filters_by_product(self):
        other_product = Product.objects.create(
            store=self.store, vendor=self.vendor, category=self.category, name="کیف پول ۳", slug="wallet-inv-3",
            sku="SKU-INV3", price=Decimal("200000"), stock=10,
        )
        decrement_stock_for_order_item(store=self.store, product=self.product, variant=None, quantity=1, order=None)
        decrement_stock_for_order_item(store=self.store, product=other_product, variant=None, quantity=1, order=None)
        movements = list_stock_movements(self.store, product=self.product)
        self.assertEqual(movements.count(), 1)
        self.assertEqual(movements.first().product_id, self.product.pk)
