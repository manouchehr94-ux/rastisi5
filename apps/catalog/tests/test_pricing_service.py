from decimal import Decimal

from django.test import TestCase

from apps.catalog.models import Category, Product, ProductVariant, Vendor
from apps.stores.models import Store


def _akhlaghi():
    return Store.objects.get(slug="akhlaghi")
from apps.catalog.services.pricing_service import (
    PricingError,
    is_variant_purchasable,
    resolve_effective_price,
    resolve_regular_price,
    resolve_savings,
)


class ResolveEffectivePriceTests(TestCase):
    def setUp(self):
        self.store = _akhlaghi()
        self.vendor = Vendor.objects.create(store=self.store, name="فروشگاه", slug="shop-ps")
        self.category = Category.objects.create(store=self.store, name="دسته", slug="cat-ps")
        self.product = Product.objects.create(
            store=self.store, vendor=self.vendor, category=self.category, name="شیلنگ فن‌کویل", slug="hose-ps",
            sku="SKU-HOSE-PS", price=Decimal("200000"),
        )

    def test_no_variant_matches_product_final_price(self):
        self.assertEqual(resolve_effective_price(self.product), self.product.final_price)

    def test_zero_adjustment_variant_equals_base_price(self):
        variant = ProductVariant.objects.create(product=self.product, attribute="طول", value="30", extra_price=0)
        self.assertEqual(resolve_effective_price(self.product, variant), Decimal("200000"))

    def test_positive_adjustment_variant(self):
        variant = ProductVariant.objects.create(
            product=self.product, attribute="طول", value="100", extra_price=Decimal("60000")
        )
        self.assertEqual(resolve_effective_price(self.product, variant), Decimal("260000"))

    def test_negative_adjustment_variant(self):
        variant = ProductVariant.objects.create(
            product=self.product, attribute="طول", value="20", extra_price=Decimal("-20000")
        )
        self.assertEqual(resolve_effective_price(self.product, variant), Decimal("180000"))

    def test_discount_percent_applies_on_top_of_variant_adjustment(self):
        self.product.discount_percent = 10
        self.product.save(update_fields=["discount_percent"])
        variant = ProductVariant.objects.create(
            product=self.product, attribute="طول", value="100", extra_price=Decimal("60000")
        )
        # (200000 + 60000) * 0.9 = 234000
        self.assertEqual(resolve_effective_price(self.product, variant), Decimal("234000"))

    def test_variant_from_another_product_raises(self):
        other_product = Product.objects.create(
            store=self.store, vendor=self.vendor, category=self.category, name="کالای دیگر", slug="other-ps",
            sku="SKU-OTHER-PS", price=Decimal("50000"),
        )
        foreign_variant = ProductVariant.objects.create(product=other_product, attribute="رنگ", value="قرمز")
        with self.assertRaises(PricingError):
            resolve_effective_price(self.product, foreign_variant)


class AbsoluteVariantPriceTests(TestCase):
    """قیچیِ ایرانی/ایتالیایی — دو تنوعِ یک کالا با قیمت‌هایِ کاملاً متفاوت،
    نه delta نسبت به قیمتِ پایه (نگاه کنید به Part 5 مشخصات)."""

    def setUp(self):
        self.store = _akhlaghi()
        self.vendor = Vendor.objects.create(store=self.store, name="فروشگاه", slug="shop-scissors")
        self.category = Category.objects.create(store=self.store, name="ابزار", slug="cat-scissors")
        self.product = Product.objects.create(
            store=self.store, vendor=self.vendor, category=self.category, name="قیچی", slug="scissors-ps",
            sku="SKU-SCISSORS", price=Decimal("1"), product_type=Product.ProductType.VARIABLE,
        )

    def test_absolute_price_ignores_product_base_price_and_discount(self):
        self.product.discount_percent = 50
        self.product.save(update_fields=["discount_percent"])
        iranian = ProductVariant.objects.create(
            product=self.product, attribute="کشور سازنده", value="ایرانی", price=Decimal("100000"),
        )
        italian = ProductVariant.objects.create(
            product=self.product, attribute="کشور سازنده", value="ایتالیایی", price=Decimal("800000"),
        )
        self.assertEqual(resolve_effective_price(self.product, iranian), Decimal("100000"))
        self.assertEqual(resolve_effective_price(self.product, italian), Decimal("800000"))

    def test_compare_at_price_becomes_regular_price_for_absolute_variant(self):
        variant = ProductVariant.objects.create(
            product=self.product, attribute="کشور سازنده", value="ایرانی",
            price=Decimal("100000"), compare_at_price=Decimal("150000"),
        )
        self.assertEqual(resolve_regular_price(self.product, variant), Decimal("150000"))
        self.assertEqual(resolve_effective_price(self.product, variant), Decimal("100000"))
        self.assertEqual(resolve_savings(self.product, variant), Decimal("50000"))

    def test_absolute_variant_without_compare_at_has_no_savings(self):
        variant = ProductVariant.objects.create(
            product=self.product, attribute="کشور سازنده", value="ایتالیایی", price=Decimal("800000"),
        )
        self.assertEqual(resolve_regular_price(self.product, variant), Decimal("800000"))
        self.assertEqual(resolve_savings(self.product, variant), Decimal("0"))

    def test_legacy_delta_variant_unaffected_by_new_fields(self):
        variant = ProductVariant.objects.create(
            product=self.product, attribute="طول", value="30", extra_price=Decimal("5000"),
        )
        self.product.price = Decimal("200000")
        self.product.save(update_fields=["price"])
        self.assertIsNone(variant.price)
        self.assertEqual(resolve_effective_price(self.product, variant), Decimal("205000"))
        self.assertEqual(resolve_regular_price(self.product, variant), Decimal("205000"))


class IsVariantPurchasableTests(TestCase):
    def setUp(self):
        self.store = _akhlaghi()
        self.vendor = Vendor.objects.create(store=self.store, name="فروشگاه", slug="shop-pur")
        self.category = Category.objects.create(store=self.store, name="دسته", slug="cat-pur")
        self.product = Product.objects.create(
            store=self.store, vendor=self.vendor, category=self.category, name="کالا", slug="product-pur",
            sku="SKU-PUR", price=Decimal("100000"),
        )

    def test_active_with_stock_is_purchasable(self):
        variant = ProductVariant.objects.create(product=self.product, attribute="رنگ", value="قرمز", stock=5)
        self.assertTrue(is_variant_purchasable(variant))

    def test_inactive_is_not_purchasable(self):
        variant = ProductVariant.objects.create(
            product=self.product, attribute="رنگ", value="قرمز", stock=5, is_active=False
        )
        self.assertFalse(is_variant_purchasable(variant))

    def test_out_of_stock_is_not_purchasable(self):
        variant = ProductVariant.objects.create(product=self.product, attribute="رنگ", value="قرمز", stock=0)
        self.assertFalse(is_variant_purchasable(variant))
