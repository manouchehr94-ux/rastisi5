from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.cart.models import Cart, CartItem
from apps.catalog.models import Category, Product, Vendor, Warehouse
from apps.catalog.services.warehouse_service import create_warehouse, provision_default_warehouse
from apps.customers.models import Address, Customer
from apps.orders.models import PaymentGateway, ShippingMethod, ShippingRateRule, ShippingZone, TaxClass, TaxRate
from apps.orders.services.order_service import create_order_from_cart
from apps.stores.models import Store

User = get_user_model()


def _akhlaghi():
    return Store.objects.get(slug="akhlaghi")


class ShippingTaxOrderIntegrationTestCase(TestCase):
    def setUp(self):
        self.store = _akhlaghi()
        self.user = User.objects.create_user(username="orders-ship-tax", password="pass12345")
        self.customer = Customer.objects.create(user=self.user, full_name="نوید رضایی", phone="09121230077")
        self.vendor = Vendor.objects.create(store=self.store, name="فروشگاه", slug="shop-ship-tax")
        self.category = Category.objects.create(store=self.store, name="دیجیتال", slug="digital-ship-tax")
        self.product = Product.objects.create(
            store=self.store, vendor=self.vendor, category=self.category, name="هدفون", slug="headphone-ship-tax",
            sku="SKU-ST1", price=Decimal("1000000"), stock=10,
        )
        self.shipping = ShippingMethod.objects.create(
            store=self.store, name="پست", slug="post-ship-tax", cost=Decimal("45000"),
        )
        self.gateway = PaymentGateway.objects.create(store=self.store, name="زرین‌پال", slug="zarin-ship-tax")
        self.address = Address.objects.create(
            customer=self.customer, receiver_name="نوید رضایی", phone="09121230077",
            province="تهران", city="تهران", postal_code="1111111111", full_address="خیابان آزادی",
        )
        self.cart = Cart.objects.create(customer=self.customer)
        CartItem.objects.create(cart=self.cart, product=self.product, quantity=1, unit_price=self.product.final_price)

    def _create(self, *, shipping_method=None):
        return create_order_from_cart(
            self.cart, customer=self.customer, vendor=self.vendor, address=self.address,
            shipping_method=shipping_method or self.shipping, payment_gateway=self.gateway,
            store=self.store,
        )


class ShippingMethodValidationTests(ShippingTaxOrderIntegrationTestCase):
    def test_rejects_shipping_method_from_other_store(self):
        other_store = Store.objects.create(name="فروشگاه دیگر", slug="ship-tax-other", status=Store.Status.ACTIVE)
        other_method = ShippingMethod.objects.create(store=other_store, name="دیگر", slug="other-ship-tax")
        with self.assertRaises(ValueError):
            self._create(shipping_method=other_method)

    def test_rejects_inactive_shipping_method(self):
        self.shipping.is_active = False
        self.shipping.save(update_fields=["is_active"])
        with self.assertRaises(ValueError):
            self._create()

    def test_rejects_method_restricted_to_non_matching_zone(self):
        zone = ShippingZone.objects.create(store=self.store, name="فارس", code="fars-ship-tax", provinces=["فارس"])
        self.shipping.zone = zone
        self.shipping.save(update_fields=["zone"])
        # آدرسِ مشتری «تهران» است، منطقه فقط «فارس» را می‌پوشاند.
        with self.assertRaises(ValueError):
            self._create()

    def test_accepts_method_matching_customer_zone(self):
        zone = ShippingZone.objects.create(store=self.store, name="تهران", code="tehran-ship-tax", provinces=["تهران"])
        self.shipping.zone = zone
        self.shipping.save(update_fields=["zone"])
        order = self._create()
        self.assertEqual(order.shipping_zone_code, "tehran-ship-tax")


class OrderSnapshotTests(ShippingTaxOrderIntegrationTestCase):
    def test_shipping_snapshot_fields_populated(self):
        order = self._create()
        self.assertEqual(order.shipping_method_name, "پست")
        self.assertEqual(order.shipping_method_code, "post-ship-tax")
        self.assertFalse(order.is_pickup)

    def test_rate_rule_snapshot_recorded_when_matched(self):
        ShippingRateRule.objects.create(method=self.shipping, name="قاعده‌ی ویژه", rate_amount=Decimal("20000"))
        # زیرِ آستانه‌ی ارسالِ رایگانِ پیش‌فرض (۵۰۰,۰۰۰) تا هزینه‌ی ارسال صفر نشود.
        cheap_product = Product.objects.create(
            store=self.store, vendor=self.vendor, category=self.category, name="کالای ارزان", slug="cheap-ship-tax",
            sku="SKU-ST-CHEAP", price=Decimal("100000"), stock=10,
        )
        self.cart.items.all().delete()
        CartItem.objects.create(cart=self.cart, product=cheap_product, quantity=1, unit_price=cheap_product.final_price)

        order = self._create()
        self.assertEqual(order.shipping_rate_rule_label, "قاعده‌ی ویژه")
        self.assertEqual(order.shipping_cost, Decimal("20000"))

    def test_fulfillment_warehouse_snapshotted_on_order_item(self):
        order = self._create()
        item = order.items.first()
        self.assertIsNotNone(item.fulfillment_warehouse)
        self.assertTrue(item.fulfillment_warehouse.is_default)

    def test_changing_default_warehouse_later_does_not_alter_historical_snapshot(self):
        order = self._create()
        original_warehouse = order.items.first().fulfillment_warehouse

        new_default = create_warehouse(self.store, name="انبار جدید", code="new-default-ship-tax")
        from apps.catalog.services.warehouse_service import set_default_warehouse
        set_default_warehouse(new_default)

        order.refresh_from_db()
        item = order.items.first()
        self.assertEqual(item.fulfillment_warehouse_id, original_warehouse.pk)
        self.assertNotEqual(item.fulfillment_warehouse_id, new_default.pk)

    def test_pickup_method_snapshot(self):
        warehouse = provision_default_warehouse(self.store)
        warehouse.is_pickup_location = True
        warehouse.save(update_fields=["is_pickup_location"])
        pickup_method = ShippingMethod.objects.create(
            store=self.store, name="بارگیری حضوری", slug="pickup-ship-tax",
            method_type=ShippingMethod.MethodType.LOCAL_PICKUP, is_pickup=True,
            pickup_warehouse=warehouse, cost=Decimal("0"),
        )
        order = self._create(shipping_method=pickup_method)
        self.assertTrue(order.is_pickup)
        self.assertEqual(order.pickup_warehouse_name, warehouse.name)
        self.assertEqual(order.pickup_address, warehouse.address)


class OrderItemTaxSnapshotTests(ShippingTaxOrderIntegrationTestCase):
    def test_legacy_flat_tax_snapshot(self):
        order = self._create()
        item = order.items.first()
        self.assertEqual(item.tax_rate_percent, Decimal("9"))
        self.assertGreater(item.total_tax, 0)

    def test_granular_tax_class_snapshot(self):
        tax_class = TaxClass.objects.create(store=self.store, name="ویژه", code="special-order-tax")
        TaxRate.objects.create(store=self.store, tax_class=tax_class, rate_percent=Decimal("4"))
        self.product.tax_class = tax_class
        self.product.save(update_fields=["tax_class"])

        order = self._create()
        item = order.items.first()
        self.assertEqual(item.tax_class_code, "special-order-tax")
        self.assertEqual(item.tax_rate_percent, Decimal("4"))
