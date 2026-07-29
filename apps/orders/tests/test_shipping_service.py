from decimal import Decimal

from django.test import TestCase

from apps.cart.models import Cart, CartItem
from apps.catalog.models import Category, Product, Vendor
from apps.catalog.services.warehouse_service import create_warehouse
from apps.orders.models import ShippingMethod, ShippingRateRule, ShippingZone
from apps.orders.services.shipping_service import (
    calculate_shipping_rate,
    cart_requires_shipping,
    cart_shippable_weight_grams,
    get_available_shipping_methods,
    resolve_best_rate_rule,
    resolve_shipping_zone,
)
from apps.stores.models import Store


def _akhlaghi():
    return Store.objects.get(slug="akhlaghi")


class ResolveShippingZoneTests(TestCase):
    def setUp(self):
        self.store = _akhlaghi()

    def test_no_zones_returns_none(self):
        self.assertIsNone(resolve_shipping_zone(self.store, province="تهران"))

    def test_postal_code_match_wins_over_province(self):
        ShippingZone.objects.create(
            store=self.store, name="تهران", code="tehran-zone", provinces=["تهران"],
        )
        exact = ShippingZone.objects.create(
            store=self.store, name="کدپستی خاص", code="postal-zone", postal_codes=["1234567890"],
        )
        result = resolve_shipping_zone(self.store, province="تهران", postal_code="1234567890")
        self.assertEqual(result, exact)

    def test_city_match_wins_over_province(self):
        ShippingZone.objects.create(store=self.store, name="استانی", code="province-zone", provinces=["فارس"])
        city_zone = ShippingZone.objects.create(store=self.store, name="شیراز", code="city-zone", cities=["شیراز"])
        result = resolve_shipping_zone(self.store, province="فارس", city="شیراز")
        self.assertEqual(result, city_zone)

    def test_fallback_used_when_nothing_matches(self):
        fallback = ShippingZone.objects.create(
            store=self.store, name="ذخیره", code="fallback-zone", is_fallback=True,
        )
        result = resolve_shipping_zone(self.store, province="نامعلوم")
        self.assertEqual(result, fallback)

    def test_inactive_zone_never_matches(self):
        ShippingZone.objects.create(
            store=self.store, name="غیرفعال", code="inactive-zone", provinces=["تهران"], is_active=False,
        )
        self.assertIsNone(resolve_shipping_zone(self.store, province="تهران"))

    def test_excluded_city_is_not_matched_even_if_province_matches(self):
        zone = ShippingZone.objects.create(
            store=self.store, name="فارس بدون شیراز", code="fars-no-shiraz",
            provinces=["فارس"], excluded_cities=["شیراز"],
        )
        self.assertTrue(zone.matches(province="فارس", city="مرودشت"))
        self.assertFalse(zone.matches(province="فارس", city="شیراز"))

    def test_priority_breaks_tie_between_matching_zones(self):
        low_priority = ShippingZone.objects.create(
            store=self.store, name="اولویتِ کم", code="low-pri", provinces=["تهران"], priority=5,
        )
        ShippingZone.objects.create(
            store=self.store, name="اولویتِ بالا", code="high-pri", provinces=["تهران"], priority=1,
        )
        result = resolve_shipping_zone(self.store, province="تهران")
        self.assertNotEqual(result, low_priority)

    def test_wrong_store_zone_never_matches(self):
        other_store = Store.objects.create(name="فروشگاه دیگر", slug="ship-zone-other", status=Store.Status.ACTIVE)
        ShippingZone.objects.create(store=other_store, name="دیگر", code="other-zone", provinces=["تهران"])
        self.assertIsNone(resolve_shipping_zone(self.store, province="تهران"))


class GetAvailableShippingMethodsTests(TestCase):
    def setUp(self):
        self.store = _akhlaghi()

    def test_zoneless_method_always_available(self):
        method = ShippingMethod.objects.create(store=self.store, name="پست", slug="post-avail")
        self.assertIn(method, get_available_shipping_methods(self.store))
        self.assertIn(method, get_available_shipping_methods(self.store, province="تهران"))

    def test_zoned_method_only_available_in_its_zone(self):
        zone = ShippingZone.objects.create(store=self.store, name="تهران", code="tehran-avail", provinces=["تهران"])
        zoned_method = ShippingMethod.objects.create(
            store=self.store, name="پیک تهران", slug="tehran-courier", zone=zone,
        )
        self.assertNotIn(zoned_method, get_available_shipping_methods(self.store, province="فارس"))
        self.assertIn(zoned_method, get_available_shipping_methods(self.store, province="تهران"))

    def test_inactive_method_excluded(self):
        method = ShippingMethod.objects.create(
            store=self.store, name="غیرفعال", slug="inactive-avail", is_active=False,
        )
        self.assertNotIn(method, get_available_shipping_methods(self.store))

    def test_wrong_store_method_never_available(self):
        other_store = Store.objects.create(name="فروشگاه دیگر", slug="ship-method-other", status=Store.Status.ACTIVE)
        other_method = ShippingMethod.objects.create(store=other_store, name="دیگر", slug="other-method-avail")
        self.assertNotIn(other_method, get_available_shipping_methods(self.store))


class ShippingRateRuleTestCase(TestCase):
    def setUp(self):
        self.store = _akhlaghi()
        self.method = ShippingMethod.objects.create(store=self.store, name="پست", slug="post-rate", cost=50_000)


class ResolveBestRateRuleTests(ShippingRateRuleTestCase):
    def test_no_rules_returns_none(self):
        self.assertIsNone(resolve_best_rate_rule(self.method, subtotal=Decimal("100000")))

    def test_matching_rule_returned(self):
        rule = ShippingRateRule.objects.create(
            method=self.method, name="عادی", min_subtotal=Decimal("0"), max_subtotal=Decimal("200000"),
            rate_amount=Decimal("30000"),
        )
        result = resolve_best_rate_rule(self.method, subtotal=Decimal("100000"))
        self.assertEqual(result, rule)

    def test_boundary_inclusive_min_and_max(self):
        rule = ShippingRateRule.objects.create(
            method=self.method, name="بازه", min_subtotal=Decimal("100000"), max_subtotal=Decimal("200000"),
            rate_amount=Decimal("20000"),
        )
        self.assertEqual(resolve_best_rate_rule(self.method, subtotal=Decimal("100000")), rule)
        self.assertEqual(resolve_best_rate_rule(self.method, subtotal=Decimal("200000")), rule)
        self.assertIsNone(resolve_best_rate_rule(self.method, subtotal=Decimal("200001")))

    def test_lower_priority_number_wins(self):
        ShippingRateRule.objects.create(method=self.method, name="کم‌اولویت", priority=10, rate_amount=Decimal("40000"))
        winner = ShippingRateRule.objects.create(method=self.method, name="پراولویت", priority=1, rate_amount=Decimal("10000"))
        result = resolve_best_rate_rule(self.method, subtotal=Decimal("50000"))
        self.assertEqual(result, winner)

    def test_more_specific_rule_wins_on_priority_tie(self):
        wide = ShippingRateRule.objects.create(method=self.method, name="باز", priority=1, rate_amount=Decimal("40000"))
        narrow = ShippingRateRule.objects.create(
            method=self.method, name="محدود", priority=1,
            min_subtotal=Decimal("0"), max_subtotal=Decimal("500000"), rate_amount=Decimal("10000"),
        )
        result = resolve_best_rate_rule(self.method, subtotal=Decimal("100000"))
        self.assertEqual(result, narrow)
        self.assertNotEqual(result, wide)

    def test_inactive_rule_never_applies(self):
        ShippingRateRule.objects.create(method=self.method, name="غیرفعال", is_active=False, rate_amount=Decimal("1"))
        self.assertIsNone(resolve_best_rate_rule(self.method, subtotal=Decimal("1000")))

    def test_expired_rule_never_applies(self):
        from django.utils import timezone
        from datetime import timedelta
        ShippingRateRule.objects.create(
            method=self.method, name="منقضی", end_at=timezone.now() - timedelta(days=1), rate_amount=Decimal("1"),
        )
        self.assertIsNone(resolve_best_rate_rule(self.method, subtotal=Decimal("1000")))

    def test_future_rule_does_not_apply_early(self):
        from django.utils import timezone
        from datetime import timedelta
        ShippingRateRule.objects.create(
            method=self.method, name="آینده", start_at=timezone.now() + timedelta(days=1), rate_amount=Decimal("1"),
        )
        self.assertIsNone(resolve_best_rate_rule(self.method, subtotal=Decimal("1000")))

    def test_weight_bounds(self):
        rule = ShippingRateRule.objects.create(
            method=self.method, name="وزنی", min_weight_grams=1000, max_weight_grams=5000, rate_amount=Decimal("15000"),
        )
        self.assertIsNone(resolve_best_rate_rule(self.method, subtotal=Decimal("1000"), weight_grams=500))
        self.assertEqual(resolve_best_rate_rule(self.method, subtotal=Decimal("1000"), weight_grams=2000), rule)


class CalculateShippingRateTests(ShippingRateRuleTestCase):
    def test_falls_back_to_legacy_cost_when_no_rules(self):
        rate = calculate_shipping_rate(self.method, subtotal=Decimal("10000"))
        self.assertEqual(rate, self.method.cost)

    def test_uses_matching_rule_amount(self):
        ShippingRateRule.objects.create(method=self.method, name="قاعده", rate_amount=Decimal("25000"))
        rate = calculate_shipping_rate(self.method, subtotal=Decimal("10000"))
        self.assertEqual(rate, Decimal("25000"))

    def test_rule_free_over_threshold_makes_it_free(self):
        ShippingRateRule.objects.create(
            method=self.method, name="آستانه", rate_amount=Decimal("25000"), free_over=Decimal("100000"),
        )
        rate = calculate_shipping_rate(self.method, subtotal=Decimal("150000"))
        self.assertEqual(rate, Decimal("0"))

    def test_free_method_type_always_zero(self):
        free_method = ShippingMethod.objects.create(
            store=self.store, name="رایگان", slug="free-method-rate",
            method_type=ShippingMethod.MethodType.FREE, cost=99_999,
        )
        rate = calculate_shipping_rate(free_method, subtotal=Decimal("1"))
        self.assertEqual(rate, Decimal("0"))


class WeightAndShippabilityTests(TestCase):
    def setUp(self):
        self.store = _akhlaghi()
        self.vendor = Vendor.objects.create(store=self.store, name="فروشگاه", slug="shop-weight")
        self.category = Category.objects.create(store=self.store, name="لوازم", slug="gear-weight")
        self.cart = Cart.objects.create()

    def _product(self, *, weight_grams=None, requires_shipping=True, slug="prod-weight"):
        return Product.objects.create(
            store=self.store, vendor=self.vendor, category=self.category, name="کالا", slug=slug,
            sku=f"SKU-{slug}", price=Decimal("10000"), stock=10,
            weight_grams=weight_grams, requires_shipping=requires_shipping,
        )

    def test_weight_sums_shippable_items_only(self):
        shippable = self._product(weight_grams=500, slug="shippable-w")
        digital = self._product(weight_grams=999, requires_shipping=False, slug="digital-w")
        CartItem.objects.create(cart=self.cart, product=shippable, quantity=2, unit_price=shippable.price)
        CartItem.objects.create(cart=self.cart, product=digital, quantity=3, unit_price=digital.price)
        items = list(self.cart.items.select_related("product", "variant"))
        self.assertEqual(cart_shippable_weight_grams(items), 1000)

    def test_missing_weight_defaults_to_zero(self):
        product = self._product(weight_grams=None, slug="no-weight")
        CartItem.objects.create(cart=self.cart, product=product, quantity=5, unit_price=product.price)
        items = list(self.cart.items.select_related("product", "variant"))
        self.assertEqual(cart_shippable_weight_grams(items), 0)

    def test_all_digital_cart_does_not_require_shipping(self):
        digital = self._product(requires_shipping=False, slug="digital-only")
        CartItem.objects.create(cart=self.cart, product=digital, quantity=1, unit_price=digital.price)
        items = list(self.cart.items.select_related("product", "variant"))
        self.assertFalse(cart_requires_shipping(items))

    def test_mixed_cart_requires_shipping(self):
        physical = self._product(requires_shipping=True, slug="mixed-physical")
        digital = self._product(requires_shipping=False, slug="mixed-digital")
        CartItem.objects.create(cart=self.cart, product=physical, quantity=1, unit_price=physical.price)
        CartItem.objects.create(cart=self.cart, product=digital, quantity=1, unit_price=digital.price)
        items = list(self.cart.items.select_related("product", "variant"))
        self.assertTrue(cart_requires_shipping(items))


class ShippingMethodPickupWarehouseIsolationTests(TestCase):
    """ShippingMethod.pickup_warehouse هرگز نمی‌تواند به انبارِ فروشگاه دیگری اشاره کند."""

    def test_rejects_pickup_warehouse_from_other_store(self):
        from django.core.exceptions import ValidationError

        store = _akhlaghi()
        other_store = Store.objects.create(name="فروشگاه دیگر", slug="pickup-iso-other", status=Store.Status.ACTIVE)
        foreign_warehouse = create_warehouse(other_store, name="خارجی", code="foreign-pickup-iso")
        method = ShippingMethod(
            store=store, name="حضوری", slug="pickup-iso", is_pickup=True, pickup_warehouse=foreign_warehouse,
        )
        with self.assertRaises(ValidationError):
            method.full_clean()

    def test_rejects_non_pickup_enabled_warehouse(self):
        from django.core.exceptions import ValidationError

        store = _akhlaghi()
        non_pickup_warehouse = create_warehouse(store, name="انبار عادی", code="non-pickup-iso")
        method = ShippingMethod(
            store=store, name="حضوری", slug="pickup-iso2", is_pickup=True, pickup_warehouse=non_pickup_warehouse,
        )
        with self.assertRaises(ValidationError):
            method.full_clean()
