from decimal import Decimal

from django.test import TestCase

from apps.catalog.models import Category, Product, ProductVariant, Vendor
from apps.stores.models import Store


def _akhlaghi():
    return Store.objects.get(slug="akhlaghi")
from apps.catalog.services import variant_service
from apps.catalog.services.variant_service import (
    ProductTypeError,
    VariantError,
    bulk_create_variants,
    can_activate_as_variable,
    copy_variant_structure,
    create_variant,
    deactivate_variant,
    delete_variant,
    generate_variant_sku,
    parse_bulk_values,
    reorder_variants,
    set_product_type,
    update_variant,
)


class BulkValueParserTests(TestCase):
    def test_persian_comma_delimiter(self):
        self.assertEqual(parse_bulk_values("30، 40، 50"), ["30", "40", "50"])

    def test_english_comma_delimiter(self):
        self.assertEqual(parse_bulk_values("30, 40, 50"), ["30", "40", "50"])

    def test_newline_delimiter(self):
        self.assertEqual(parse_bulk_values("30\n40\n50"), ["30", "40", "50"])

    def test_semicolon_and_persian_semicolon_delimiter(self):
        self.assertEqual(parse_bulk_values("30;40؛50"), ["30", "40", "50"])

    def test_persian_digits_normalized(self):
        self.assertEqual(parse_bulk_values("۳۰، ۴۰، ۵۰"), ["30", "40", "50"])

    def test_arabic_digits_normalized(self):
        self.assertEqual(parse_bulk_values("٣٠، ٤٠"), ["30", "40"])

    def test_extra_whitespace_trimmed(self):
        self.assertEqual(parse_bulk_values("  30  ,   40  "), ["30", "40"])

    def test_duplicate_values_deduplicated(self):
        self.assertEqual(parse_bulk_values("30, 30, ۳۰, 40"), ["30", "40"])

    def test_empty_input_returns_empty_list(self):
        self.assertEqual(parse_bulk_values(""), [])
        self.assertEqual(parse_bulk_values("   "), [])

    def test_mixed_delimiters(self):
        self.assertEqual(parse_bulk_values("30, 40؛ 50\n60،70"), ["30", "40", "50", "60", "70"])

    def test_empty_entries_between_delimiters_removed(self):
        self.assertEqual(parse_bulk_values("30,,40,, ,50"), ["30", "40", "50"])


class VariantCreationServiceTests(TestCase):
    def setUp(self):
        self.store = _akhlaghi()
        self.vendor = Vendor.objects.create(store=self.store, name="فروشگاه", slug="shop-vs")
        self.category = Category.objects.create(store=self.store, name="دسته", slug="cat-vs")
        self.product = Product.objects.create(
            store=self.store, vendor=self.vendor, category=self.category, name="شیلنگ فن‌کویل", slug="hose-vs",
            sku="SKU-HOSE-VS", price=Decimal("200000"),
        )
        self.other_product = Product.objects.create(
            store=self.store, vendor=self.vendor, category=self.category, name="کالای دیگر", slug="other-vs",
            sku="SKU-OTHER-VS", price=Decimal("50000"),
        )

    def test_create_variant_auto_generates_sku(self):
        variant = create_variant(self.product, attribute="طول", value="30 سانتی‌متر")
        self.assertTrue(variant.sku.startswith("SKU-HOSE-VS-"))

    def test_create_variant_rejects_negative_stock(self):
        with self.assertRaises(VariantError):
            create_variant(self.product, attribute="طول", value="30", stock=-5)

    def test_create_variant_rejects_duplicate_value(self):
        create_variant(self.product, attribute="طول", value="30")
        with self.assertRaises(VariantError):
            create_variant(self.product, attribute="طول", value="30")

    def test_create_variant_rejects_explicit_duplicate_sku(self):
        create_variant(self.product, attribute="طول", value="30", sku="HOSE-30")
        with self.assertRaises(VariantError):
            create_variant(self.product, attribute="طول", value="40", sku="HOSE-30")

    def test_bulk_create_variants_creates_all_and_reports_no_skips(self):
        created, skipped = bulk_create_variants(
            self.product, attribute="طول", raw_values="30، 40، 50", default_stock=10
        )
        self.assertEqual(len(created), 3)
        self.assertEqual(skipped, [])
        self.assertEqual(self.product.variants.count(), 3)
        for variant in created:
            self.assertEqual(variant.stock, 10)

    def test_bulk_create_variants_skips_existing_active_values(self):
        create_variant(self.product, attribute="طول", value="30")
        created, skipped = bulk_create_variants(self.product, attribute="طول", raw_values="30، 40")
        self.assertEqual(len(created), 1)
        self.assertEqual(created[0].value, "40")
        self.assertEqual(len(skipped), 1)

    def test_bulk_create_variants_rejects_empty_attribute(self):
        with self.assertRaises(VariantError):
            bulk_create_variants(self.product, attribute="  ", raw_values="30، 40")

    def test_bulk_create_variants_rejects_empty_values(self):
        with self.assertRaises(VariantError):
            bulk_create_variants(self.product, attribute="طول", raw_values="   ")

    def test_bulk_create_variants_default_is_active_true(self):
        created, _ = bulk_create_variants(self.product, attribute="طول", raw_values="30، 40")
        self.assertTrue(all(v.is_active for v in created))

    def test_bulk_create_variants_can_create_inactive(self):
        created, skipped = bulk_create_variants(
            self.product, attribute="طول", raw_values="30، 40", is_active=False
        )
        self.assertEqual(len(created), 2)
        self.assertEqual(skipped, [])
        self.assertTrue(all(not v.is_active for v in created))

    def test_bulk_create_variants_inactive_does_not_check_existing_active_duplicates(self):
        create_variant(self.product, attribute="طول", value="30")
        created, skipped = bulk_create_variants(
            self.product, attribute="طول", raw_values="30", is_active=False
        )
        self.assertEqual(len(created), 1)
        self.assertEqual(skipped, [])

    def test_update_variant_changes_stock_and_price_adjustment(self):
        variant = create_variant(self.product, attribute="طول", value="30")
        updated = update_variant(variant, stock=25, extra_price=Decimal("15000"))
        self.assertEqual(updated.stock, 25)
        self.assertEqual(updated.extra_price, Decimal("15000"))

    def test_update_variant_rejects_negative_stock(self):
        variant = create_variant(self.product, attribute="طول", value="30")
        with self.assertRaises(VariantError):
            update_variant(variant, stock=-1)

    def test_update_variant_rejects_sku_collision(self):
        create_variant(self.product, attribute="طول", value="30", sku="HOSE-30")
        variant = create_variant(self.product, attribute="طول", value="40", sku="HOSE-40")
        with self.assertRaises(VariantError):
            update_variant(variant, sku="HOSE-30")

    def test_update_variant_allows_keeping_own_sku(self):
        variant = create_variant(self.product, attribute="طول", value="30", sku="HOSE-30")
        updated = update_variant(variant, sku="HOSE-30", stock=5)
        self.assertEqual(updated.sku, "HOSE-30")

    def test_update_variant_rejects_rename_into_existing_duplicate(self):
        create_variant(self.product, attribute="طول", value="30")
        variant = create_variant(self.product, attribute="طول", value="40")
        with self.assertRaises(VariantError):
            update_variant(variant, value="30")

    def test_deactivate_variant_frees_up_value_for_reuse(self):
        variant = create_variant(self.product, attribute="طول", value="30")
        deactivate_variant(variant)
        self.assertFalse(variant.is_active)
        new_variant = create_variant(self.product, attribute="طول", value="30")
        self.assertTrue(new_variant.is_active)

    def test_delete_variant_without_orders_succeeds(self):
        variant = create_variant(self.product, attribute="طول", value="30")
        delete_variant(variant)
        self.assertEqual(self.product.variants.count(), 0)

    def test_delete_variant_used_in_order_is_blocked(self):
        from apps.customers.models import Customer
        from django.contrib.auth import get_user_model
        from apps.orders.models import Order, OrderItem, PaymentGateway, ShippingMethod

        variant = create_variant(self.product, attribute="طول", value="30")
        User = get_user_model()
        user = User.objects.create_user(username="09121112233", password="pass12345")
        customer = Customer.objects.create(user=user, full_name="مشتری", phone="09121112233")
        shipping = ShippingMethod.objects.create(store=self.store, name="پست", slug="post-vs", cost=Decimal("10000"))
        gateway = PaymentGateway.objects.create(store=self.store, name="درگاه", slug="gw-vs")
        order = Order.objects.create(
            code="DM-11111", store=self.store, customer=customer, vendor=self.vendor, shipping_method=shipping,
            payment_gateway=gateway,
        )
        OrderItem.objects.create(
            order=order, product=self.product, variant=variant, product_name=self.product.name,
            quantity=1, unit_price=Decimal("200000"), line_total=Decimal("200000"),
        )
        with self.assertRaises(VariantError):
            delete_variant(variant)

    def test_reorder_variants_updates_display_order(self):
        v1 = create_variant(self.product, attribute="طول", value="30")
        v2 = create_variant(self.product, attribute="طول", value="40")
        v3 = create_variant(self.product, attribute="طول", value="50")
        reorder_variants(self.product, [v3.pk, v1.pk, v2.pk])
        v1.refresh_from_db()
        v2.refresh_from_db()
        v3.refresh_from_db()
        self.assertEqual(v3.display_order, 0)
        self.assertEqual(v1.display_order, 1)
        self.assertEqual(v2.display_order, 2)

    def test_reorder_variants_ignores_foreign_product_ids(self):
        own = create_variant(self.product, attribute="طول", value="30")
        foreign = create_variant(self.other_product, attribute="رنگ", value="قرمز")
        reorder_variants(self.product, [foreign.pk, own.pk])
        foreign.refresh_from_db()
        self.assertEqual(foreign.display_order, 0)
        own.refresh_from_db()
        self.assertEqual(own.display_order, 0)

    def test_copy_variant_structure_does_not_modify_source(self):
        source_variant = create_variant(
            self.product, attribute="طول", value="30", stock=20, extra_price=Decimal("5000"), sku="HOSE-30"
        )
        copy_variant_structure(self.product, self.other_product)
        source_variant.refresh_from_db()
        self.assertEqual(source_variant.stock, 20)
        self.assertEqual(source_variant.extra_price, Decimal("5000"))
        self.assertEqual(source_variant.sku, "HOSE-30")

    def test_copy_variant_structure_resets_stock_price_and_sku(self):
        create_variant(self.product, attribute="طول", value="30", stock=20, extra_price=Decimal("5000"), sku="HOSE-30")
        copied = copy_variant_structure(self.product, self.other_product)
        self.assertEqual(len(copied), 1)
        self.assertEqual(copied[0].stock, 0)
        self.assertEqual(copied[0].extra_price, 0)
        self.assertNotEqual(copied[0].sku, "HOSE-30")
        self.assertEqual(copied[0].attribute, "طول")
        self.assertEqual(copied[0].value, "30")

    def test_copy_variant_structure_skips_inactive_source_variants(self):
        inactive = create_variant(self.product, attribute="طول", value="30")
        deactivate_variant(inactive)
        copied = copy_variant_structure(self.product, self.other_product)
        self.assertEqual(copied, [])

    def test_copy_variant_structure_rejects_same_product(self):
        with self.assertRaises(VariantError):
            copy_variant_structure(self.product, self.product)

    def test_generate_variant_sku_avoids_collision(self):
        first = generate_variant_sku(self.product, "30")
        create_variant(self.product, attribute="طول", value="30", sku=first)
        second = generate_variant_sku(self.other_product, "30")
        self.assertNotEqual(first, second)


class ProductTypeTransitionTests(TestCase):
    def setUp(self):
        self.store = _akhlaghi()
        self.vendor = Vendor.objects.create(store=self.store, name="فروشگاه", slug="shop-pt")
        self.category = Category.objects.create(store=self.store, name="دسته", slug="cat-pt")
        self.product = Product.objects.create(
            store=self.store, vendor=self.vendor, category=self.category, name="کالا", slug="product-pt",
            sku="SKU-PT", price=Decimal("100000"),
        )

    def test_simple_to_variable_allowed(self):
        product = set_product_type(self.product, Product.ProductType.VARIABLE)
        self.assertEqual(product.product_type, Product.ProductType.VARIABLE)

    def test_cannot_activate_as_variable_without_active_variant(self):
        set_product_type(self.product, Product.ProductType.VARIABLE)
        self.assertFalse(can_activate_as_variable(self.product))
        create_variant(self.product, attribute="رنگ", value="قرمز")
        self.assertTrue(can_activate_as_variable(self.product))

    def test_variable_to_simple_blocked_while_variants_exist(self):
        set_product_type(self.product, Product.ProductType.VARIABLE)
        create_variant(self.product, attribute="رنگ", value="قرمز")
        with self.assertRaises(ProductTypeError):
            set_product_type(self.product, Product.ProductType.SIMPLE)

    def test_variable_to_simple_allowed_after_variants_removed(self):
        set_product_type(self.product, Product.ProductType.VARIABLE)
        variant = create_variant(self.product, attribute="رنگ", value="قرمز")
        delete_variant(variant)
        product = set_product_type(self.product, Product.ProductType.SIMPLE)
        self.assertEqual(product.product_type, Product.ProductType.SIMPLE)

    def test_invalid_product_type_rejected(self):
        with self.assertRaises(ProductTypeError):
            set_product_type(self.product, "not-a-real-type")
