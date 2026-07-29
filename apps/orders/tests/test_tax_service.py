from decimal import Decimal

from django.test import TestCase

from apps.core.models import ShopSettings
from apps.orders.models import TaxClass, TaxRate
from apps.orders.services.tax_service import (
    calculate_order_taxes,
    resolve_tax_rate,
    store_has_granular_tax_rates,
)
from apps.stores.models import Store


def _akhlaghi():
    return Store.objects.get(slug="akhlaghi")


def _item(unit_price, quantity, *, discount=Decimal("0"), tax_class=None):
    return {
        "unit_price": Decimal(unit_price), "quantity": quantity,
        "discount_allocation": discount, "tax_class": tax_class,
    }


class StoreHasGranularTaxRatesTests(TestCase):
    def test_false_when_no_rates(self):
        self.assertFalse(store_has_granular_tax_rates(_akhlaghi()))

    def test_true_when_any_rate_exists(self):
        store = _akhlaghi()
        tax_class = TaxClass.objects.create(store=store, name="عمومی", code="general-flag")
        TaxRate.objects.create(store=store, tax_class=tax_class, rate_percent=Decimal("9"))
        self.assertTrue(store_has_granular_tax_rates(store))


class ResolveTaxRateTests(TestCase):
    def setUp(self):
        self.store = _akhlaghi()
        self.tax_class = TaxClass.objects.create(store=self.store, name="عمومی", code="general-resolve")

    def test_no_rates_returns_none(self):
        self.assertIsNone(resolve_tax_rate(self.store, tax_class=self.tax_class))

    def test_province_exact_match_wins_over_store_wide(self):
        store_wide = TaxRate.objects.create(
            store=self.store, tax_class=self.tax_class, province="", rate_percent=Decimal("9"),
        )
        exact = TaxRate.objects.create(
            store=self.store, tax_class=self.tax_class, province="تهران", rate_percent=Decimal("5"),
        )
        result = resolve_tax_rate(self.store, tax_class=self.tax_class, province="تهران")
        self.assertEqual(result, exact)
        self.assertNotEqual(result, store_wide)

    def test_store_wide_used_when_no_province_match(self):
        store_wide = TaxRate.objects.create(
            store=self.store, tax_class=self.tax_class, province="", rate_percent=Decimal("9"),
        )
        result = resolve_tax_rate(self.store, tax_class=self.tax_class, province="فارس")
        self.assertEqual(result, store_wide)

    def test_inactive_rate_never_applies(self):
        TaxRate.objects.create(
            store=self.store, tax_class=self.tax_class, rate_percent=Decimal("9"), is_active=False,
        )
        self.assertIsNone(resolve_tax_rate(self.store, tax_class=self.tax_class))

    def test_no_tax_class_falls_back_to_store_default(self):
        settings_row = ShopSettings.load(store=self.store)
        settings_row.default_tax_class = self.tax_class
        settings_row.save(update_fields=["default_tax_class"])
        rate = TaxRate.objects.create(store=self.store, tax_class=self.tax_class, rate_percent=Decimal("7"))
        result = resolve_tax_rate(self.store, tax_class=None)
        self.assertEqual(result, rate)

    def test_wrong_store_tax_class_never_resolves(self):
        other_store = Store.objects.create(name="فروشگاه دیگر", slug="tax-resolve-other", status=Store.Status.ACTIVE)
        other_class = TaxClass.objects.create(store=other_store, name="دیگر", code="other-resolve")
        TaxRate.objects.create(store=other_store, tax_class=other_class, rate_percent=Decimal("9"))
        self.assertIsNone(resolve_tax_rate(self.store, tax_class=other_class))


class CalculateOrderTaxesLegacyFallbackTests(TestCase):
    """Store has zero TaxRate rows — must match the pre-checkpoint-3B ``cart_totals`` formula exactly."""

    def setUp(self):
        self.store = _akhlaghi()

    def test_matches_legacy_flat_formula_single_item(self):
        settings_row = ShopSettings.load(store=self.store)
        settings_row.tax_percent = Decimal("9")
        settings_row.save(update_fields=["tax_percent"])
        result = calculate_order_taxes(
            self.store, items=[_item("200000", 1)], shipping_amount=Decimal("50000"),
        )
        self.assertEqual(result["total_tax"], Decimal("18000"))  # 9% of 200,000
        self.assertEqual(result["shipping_tax"], Decimal("0"))  # shipping not taxable by default

    def test_shipping_taxable_when_store_settings_enable_it(self):
        settings_row = ShopSettings.load(store=self.store)
        settings_row.shipping_taxable = True
        settings_row.tax_percent = Decimal("9")
        settings_row.save(update_fields=["shipping_taxable", "tax_percent"])
        result = calculate_order_taxes(
            self.store, items=[_item("200000", 1)], shipping_amount=Decimal("100000"),
        )
        self.assertEqual(result["shipping_tax"], Decimal("9000"))

    def test_tax_disabled_returns_zero(self):
        settings_row = ShopSettings.load(store=self.store)
        settings_row.tax_enabled = False
        settings_row.save(update_fields=["tax_enabled"])
        result = calculate_order_taxes(
            self.store, items=[_item("200000", 1)], shipping_amount=Decimal("50000"),
        )
        self.assertEqual(result["total_tax"], Decimal("0"))

    def test_discount_reduces_taxable_amount(self):
        settings_row = ShopSettings.load(store=self.store)
        settings_row.tax_percent = Decimal("9")
        settings_row.save(update_fields=["tax_percent"])
        result = calculate_order_taxes(
            self.store, items=[_item("200000", 1, discount=Decimal("50000"))], shipping_amount=Decimal("0"),
        )
        self.assertEqual(result["total_tax"], Decimal("13500"))  # 9% of 150,000


class CalculateOrderTaxesGranularTests(TestCase):
    def setUp(self):
        self.store = _akhlaghi()
        self.tax_class = TaxClass.objects.create(store=self.store, name="عمومی", code="general-granular")
        TaxRate.objects.create(store=self.store, tax_class=self.tax_class, rate_percent=Decimal("9"))

    def test_resolved_line_tax_uses_matching_rate(self):
        result = calculate_order_taxes(
            self.store, items=[_item("100000", 1, tax_class=self.tax_class)], shipping_amount=Decimal("0"),
        )
        self.assertEqual(result["total_tax"], Decimal("9000"))
        self.assertEqual(result["lines"][0]["tax_class_code"], "general-granular")

    def test_line_without_matching_rate_is_zero_not_flat_fallback(self):
        other_class = TaxClass.objects.create(store=self.store, name="معاف", code="exempt-granular")
        result = calculate_order_taxes(
            self.store, items=[_item("100000", 1, tax_class=other_class)], shipping_amount=Decimal("0"),
        )
        self.assertEqual(result["total_tax"], Decimal("0"))

    def test_quantity_multiplies_taxable_amount(self):
        result = calculate_order_taxes(
            self.store, items=[_item("100000", 3, tax_class=self.tax_class)], shipping_amount=Decimal("0"),
        )
        self.assertEqual(result["total_tax"], Decimal("27000"))

    def test_shipping_tax_uses_default_tax_class_rate(self):
        settings_row = ShopSettings.load(store=self.store)
        settings_row.default_tax_class = self.tax_class
        settings_row.shipping_taxable = True
        settings_row.save(update_fields=["default_tax_class", "shipping_taxable"])
        result = calculate_order_taxes(
            self.store, items=[_item("100000", 1, tax_class=self.tax_class)], shipping_amount=Decimal("50000"),
        )
        self.assertEqual(result["shipping_tax"], Decimal("4500"))


class InclusiveTaxTests(TestCase):
    """قیمت‌های شاملِ مالیات (``prices_include_tax=True``) — مالیات از دلِ
    قیمت استخراج می‌شود، نه افزوده به آن (ADR-45)."""

    def setUp(self):
        self.store = _akhlaghi()
        settings_row = ShopSettings.load(store=self.store)
        settings_row.prices_include_tax = True
        settings_row.tax_percent = Decimal("9")
        settings_row.save(update_fields=["prices_include_tax", "tax_percent"])

    def test_tax_extracted_not_added_legacy_path(self):
        result = calculate_order_taxes(self.store, items=[_item("109000", 1)], shipping_amount=Decimal("0"))
        # 109,000 already includes 9% tax: tax = 109000 * 9/109 = 9000
        self.assertEqual(result["total_tax"], Decimal("9000"))
        self.assertEqual(result["tax_added_to_grand_total"], Decimal("0"))

    def test_taxable_amount_excludes_extracted_tax(self):
        result = calculate_order_taxes(self.store, items=[_item("109000", 1)], shipping_amount=Decimal("0"))
        self.assertEqual(result["lines"][0]["taxable_amount"], Decimal("100000"))

    def test_shipping_tax_still_added_on_top(self):
        settings_row = ShopSettings.load(store=self.store)
        settings_row.shipping_taxable = True
        settings_row.save(update_fields=["shipping_taxable"])
        result = calculate_order_taxes(self.store, items=[_item("109000", 1)], shipping_amount=Decimal("50000"))
        self.assertEqual(result["shipping_tax"], Decimal("4500"))
        self.assertEqual(result["tax_added_to_grand_total"], Decimal("4500"))

    def test_granular_path_inclusive(self):
        tax_class = TaxClass.objects.create(store=self.store, name="عمومی", code="inclusive-granular")
        TaxRate.objects.create(store=self.store, tax_class=tax_class, rate_percent=Decimal("9"))
        result = calculate_order_taxes(
            self.store, items=[_item("109000", 1, tax_class=tax_class)], shipping_amount=Decimal("0"),
        )
        self.assertEqual(result["total_tax"], Decimal("9000"))
        self.assertEqual(result["tax_added_to_grand_total"], Decimal("0"))
