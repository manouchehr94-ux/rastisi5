from decimal import Decimal

from django.db import transaction
from django.test import TestCase

from apps.catalog.models import (
    Attribute,
    Category,
    Product,
    ProductImage,
    ProductOption,
    ProductVariant,
    Vendor,
)
from apps.catalog.services.variant_engine_service import (
    MAX_OPTION_AXES,
    VariantEngineError,
    add_manual_variant,
    add_option_value,
    add_product_option,
    deactivate_product_option,
    generate_variants,
    preview_combination_count,
    remove_option_value,
    reorder_option_values,
    reorder_product_options,
    set_default_variant,
)
from apps.stores.models import Store


def _akhlaghi():
    return Store.objects.get(slug="akhlaghi")


class VariantEngineTestCase(TestCase):
    def setUp(self):
        self.store = _akhlaghi()
        self.vendor = Vendor.objects.create(store=self.store, name="فروشنده", slug="ve-shop")
        self.category = Category.objects.create(store=self.store, name="دسته", slug="ve-cat")
        self.product = Product.objects.create(
            store=self.store, vendor=self.vendor, category=self.category, name="تی‌شرت",
            slug="ve-tshirt", sku="VE-TS1", price=Decimal("300000"),
            product_type=Product.ProductType.VARIABLE,
        )

    def _add_color_size(self):
        color = add_product_option(self.product, label="رنگ", values=["سبز", "آبی", "زرد"])
        size = add_product_option(self.product, label="سایز", values=["S", "M", "L", "XL"])
        return color, size


class AddProductOptionTests(VariantEngineTestCase):
    def test_creates_option_with_values(self):
        option = add_product_option(self.product, label="رنگ", values=["سبز", "آبی"])
        self.assertEqual(option.values.count(), 2)
        self.assertEqual(option.position, 0)

    def test_second_option_gets_next_position(self):
        add_product_option(self.product, label="رنگ", values=["سبز"])
        size = add_product_option(self.product, label="سایز", values=["S"])
        self.assertEqual(size.position, 1)

    def test_blank_label_rejected(self):
        with self.assertRaises(VariantEngineError):
            add_product_option(self.product, label="   ", values=["x"])

    def test_duplicate_axis_label_rejected(self):
        add_product_option(self.product, label="رنگ", values=["سبز"])
        with self.assertRaises(VariantEngineError):
            add_product_option(self.product, label="رنگ", values=["آبی"])

    def test_max_axes_enforced(self):
        add_product_option(self.product, label="رنگ", values=["سبز"])
        add_product_option(self.product, label="سایز", values=["S"])
        add_product_option(self.product, label="جنس", values=["نخی"])
        self.assertEqual(MAX_OPTION_AXES, 3)
        with self.assertRaises(VariantEngineError):
            add_product_option(self.product, label="مدل", values=["A"])

    def test_cross_store_attribute_rejected(self):
        other_store = Store.objects.create(name="فروشگاه دیگر", slug="ve-other", status=Store.Status.ACTIVE)
        other_attr = Attribute.objects.create(
            store=other_store, code="color", label="رنگ", is_variant_axis=True,
        )
        with self.assertRaises(VariantEngineError):
            add_product_option(self.product, label="رنگ", attribute=other_attr)

    def test_non_variant_axis_attribute_rejected(self):
        attr = Attribute.objects.create(
            store=self.store, code="material", label="جنس", is_variant_axis=False,
        )
        with self.assertRaises(VariantEngineError):
            add_product_option(self.product, label="جنس", attribute=attr)

    def test_blocked_while_legacy_variants_exist(self):
        ProductVariant.objects.create(
            product=self.product, store=self.store, attribute="رنگ", value="قرمز",
        )
        with self.assertRaises(VariantEngineError):
            add_product_option(self.product, label="رنگ", values=["سبز"])


class OptionValueTests(VariantEngineTestCase):
    def test_add_value(self):
        color = add_product_option(self.product, label="رنگ")
        value = add_option_value(color, "سبز", color_hex="#00ff00")
        self.assertEqual(value.color_hex, "#00ff00")

    def test_duplicate_value_label_rejected(self):
        color = add_product_option(self.product, label="رنگ", values=["سبز"])
        with self.assertRaises(VariantEngineError):
            add_option_value(color, "سبز")

    def test_reorder_values(self):
        color = add_product_option(self.product, label="رنگ", values=["سبز", "آبی", "زرد"])
        ids = list(color.values.order_by("display_order").values_list("pk", flat=True))
        reorder_option_values(color, list(reversed(ids)))
        new_order = list(color.values.order_by("display_order").values_list("pk", flat=True))
        self.assertEqual(new_order, list(reversed(ids)))

    def test_remove_unused_value_hard_deletes(self):
        color = add_product_option(self.product, label="رنگ", values=["سبز", "آبی"])
        value = color.values.get(label="سبز")
        remove_option_value(value)
        self.assertFalse(color.values.filter(pk=value.pk).exists())

    def test_remove_used_value_soft_deactivates(self):
        self._add_color_size()
        generate_variants(self.product)
        color = self.product.options.get(label="رنگ")
        value = color.values.get(label="سبز")
        remove_option_value(value)
        value.refresh_from_db()
        self.assertFalse(value.is_active)
        self.assertTrue(color.values.filter(pk=value.pk).exists())


class PreviewCombinationCountTests(VariantEngineTestCase):
    def test_single_axis(self):
        add_product_option(self.product, label="رنگ", values=["سبز", "آبی", "زرد"])
        self.assertEqual(preview_combination_count(self.product), 3)

    def test_two_axes(self):
        self._add_color_size()
        self.assertEqual(preview_combination_count(self.product), 12)

    def test_no_axes_is_zero(self):
        self.assertEqual(preview_combination_count(self.product), 0)

    def test_ignores_inactive_axis(self):
        color, size = self._add_color_size()
        deactivate_product_option(size)
        self.assertEqual(preview_combination_count(self.product), 3)


class GenerateVariantsTests(VariantEngineTestCase):
    def test_single_option_three_values(self):
        add_product_option(self.product, label="رنگ", values=["سبز", "آبی", "زرد"])
        result = generate_variants(self.product)
        self.assertEqual(len(result.created), 3)
        self.assertEqual(self.product.variants.count(), 3)

    def test_two_options_cartesian_product(self):
        self._add_color_size()
        result = generate_variants(self.product)
        self.assertEqual(len(result.created), 12)
        combos = {v.value for v in self.product.variants.all()}
        self.assertIn("سبز / S", combos)
        self.assertIn("زرد / XL", combos)

    def test_three_options(self):
        add_product_option(self.product, label="رنگ", values=["سبز", "آبی"])
        add_product_option(self.product, label="سایز", values=["S", "M"])
        add_product_option(self.product, label="جنس", values=["نخی", "پلی‌استر"])
        result = generate_variants(self.product)
        self.assertEqual(len(result.created), 8)

    def test_large_combination_set_125_variants(self):
        add_product_option(self.product, label="رنگ", values=[f"رنگ{i}" for i in range(5)])
        add_product_option(self.product, label="سایز", values=[f"سایز{i}" for i in range(5)])
        add_product_option(self.product, label="جنس", values=[f"جنس{i}" for i in range(5)])
        result = generate_variants(self.product)
        self.assertEqual(len(result.created), 125)
        self.assertEqual(self.product.variants.exclude(combination_key="").count(), 125)
        keys = set(self.product.variants.values_list("combination_key", flat=True))
        self.assertEqual(len(keys), 125)

    def test_idempotent_rerun_creates_nothing(self):
        self._add_color_size()
        generate_variants(self.product)
        result = generate_variants(self.product)
        self.assertEqual(len(result.created), 0)
        self.assertEqual(len(result.obsoleted), 0)
        self.assertEqual(len(result.preserved), 12)
        self.assertEqual(self.product.variants.count(), 12)

    def test_no_duplicate_combination_keys(self):
        self._add_color_size()
        generate_variants(self.product)
        keys = list(self.product.variants.values_list("combination_key", flat=True))
        self.assertEqual(len(keys), len(set(keys)))

    def test_deterministic_ordering(self):
        self._add_color_size()
        generate_variants(self.product)
        orders = list(self.product.variants.order_by("display_order").values_list("value", flat=True))
        self.assertEqual(orders[0], "سبز / S")

    def test_default_variant_assigned(self):
        self._add_color_size()
        generate_variants(self.product)
        self.assertEqual(self.product.variants.filter(is_default=True).count(), 1)

    def test_requires_variable_product_type(self):
        self.product.product_type = Product.ProductType.SIMPLE
        self.product.save(update_fields=["product_type"])
        add_product_option(self.product, label="رنگ", values=["سبز"])
        with self.assertRaises(VariantEngineError):
            generate_variants(self.product)

    def test_requires_at_least_one_axis(self):
        with self.assertRaises(VariantEngineError):
            generate_variants(self.product)

    def test_axis_with_no_active_values_rejected(self):
        color = add_product_option(self.product, label="رنگ", values=["سبز"])
        value = color.values.get()
        value.is_active = False
        value.save(update_fields=["is_active"])
        with self.assertRaises(VariantEngineError):
            generate_variants(self.product)

    def test_transaction_rolls_back_on_failure(self):
        color = add_product_option(self.product, label="رنگ", values=["سبز"])
        # Sabotage: make the size axis exist but have no active values.
        size = ProductOption.objects.create(product=self.product, label="سایز", position=1)
        count_before = self.product.variants.count()
        with self.assertRaises(VariantEngineError):
            with transaction.atomic():
                generate_variants(self.product)
        self.assertEqual(self.product.variants.count(), count_before)


class VariantReconciliationTests(VariantEngineTestCase):
    def test_add_value_creates_only_missing_variants(self):
        color, size = self._add_color_size()
        generate_variants(self.product)
        existing_ids = set(self.product.variants.values_list("pk", flat=True))

        add_option_value(size, "XXL")
        result = generate_variants(self.product)

        self.assertEqual(len(result.created), 3)  # one new size × 3 colors
        self.assertEqual(set(v.pk for v in result.preserved), existing_ids)
        self.assertEqual(self.product.variants.exclude(combination_key="").count(), 15)

    def test_remove_value_marks_obsolete_not_deleted(self):
        color, size = self._add_color_size()
        generate_variants(self.product)
        yellow = color.values.get(label="زرد")
        remove_option_value(yellow)  # soft-deactivate, used by variants

        result = generate_variants(self.product)

        self.assertEqual(len(result.obsoleted), 4)  # yellow × 4 sizes
        obsolete_variants = self.product.variants.filter(is_obsolete=True)
        self.assertEqual(obsolete_variants.count(), 4)
        for variant in obsolete_variants:
            self.assertFalse(variant.is_active)
        self.assertEqual(self.product.variants.count(), 12)  # nothing deleted

    def test_rename_value_does_not_recreate_variant(self):
        color, size = self._add_color_size()
        generate_variants(self.product)
        green = color.values.get(label="سبز")
        variant_before = self.product.variants.filter(combination_key__isnull=False).exclude(
            combination_key=""
        ).get(value="سبز / S")
        sku_before, pk_before = variant_before.sku, variant_before.pk

        green.label = "سبز روشن"
        green.save(update_fields=["label"])
        result = generate_variants(self.product)

        self.assertEqual(len(result.created), 0)
        self.assertEqual(len(result.obsoleted), 0)
        variant_before.refresh_from_db()
        self.assertEqual(variant_before.pk, pk_before)
        self.assertEqual(variant_before.sku, sku_before)

    def test_rename_option_does_not_recreate_variants(self):
        color, size = self._add_color_size()
        generate_variants(self.product)
        ids_before = set(self.product.variants.values_list("pk", flat=True))

        color.label = "رنگ محصول"
        color.save(update_fields=["label"])
        result = generate_variants(self.product)

        self.assertEqual(len(result.created), 0)
        self.assertEqual(len(result.obsoleted), 0)
        self.assertEqual(set(self.product.variants.values_list("pk", flat=True)), ids_before)

    def test_reorder_options_preserves_variant_identity(self):
        color, size = self._add_color_size()
        generate_variants(self.product)
        variant = self.product.variants.get(value="سبز / S")
        pk_before, sku_before, price_before = variant.pk, variant.sku, variant.extra_price
        variant.stock = 42
        variant.save(update_fields=["stock"])

        reorder_product_options(self.product, [size.pk, color.pk])
        result = generate_variants(self.product)

        self.assertEqual(len(result.created), 0)
        self.assertEqual(len(result.obsoleted), 0)
        variant.refresh_from_db()
        self.assertEqual(variant.pk, pk_before)
        self.assertEqual(variant.sku, sku_before)
        self.assertEqual(variant.extra_price, price_before)
        self.assertEqual(variant.stock, 42)

    def test_preserves_price_inventory_and_images_on_regeneration(self):
        self._add_color_size()
        generate_variants(self.product)
        variant = self.product.variants.first()
        variant.stock = 17
        variant.extra_price = Decimal("5000")
        variant.sku = "CUSTOM-SKU-1"
        variant.save(update_fields=["stock", "extra_price", "sku"])

        generate_variants(self.product)

        variant.refresh_from_db()
        self.assertEqual(variant.stock, 17)
        self.assertEqual(variant.extra_price, Decimal("5000"))
        self.assertEqual(variant.sku, "CUSTOM-SKU-1")

    def test_removing_axis_obsoletes_all_its_combinations(self):
        color, size = self._add_color_size()
        generate_variants(self.product)
        deactivate_product_option(size)

        result = generate_variants(self.product)

        self.assertEqual(len(result.obsoleted), 12)
        self.assertEqual(len(result.created), 3)  # one variant per color, size axis dropped
        self.assertTrue(self.product.variants.filter(is_obsolete=True).count() >= 12)

    def test_re_adding_removed_value_restores_original_variant_not_a_duplicate(self):
        color, size = self._add_color_size()
        generate_variants(self.product)
        yellow = color.values.get(label="زرد")
        original_variant = self.product.variants.get(value="زرد / S")
        original_pk = original_variant.pk
        remove_option_value(yellow)
        generate_variants(self.product)

        yellow.refresh_from_db()
        yellow.is_active = True
        yellow.save(update_fields=["is_active"])
        result = generate_variants(self.product)

        self.assertEqual(len(result.created), 0)
        restored = self.product.variants.get(pk=original_pk)
        self.assertFalse(restored.is_obsolete)
        self.assertTrue(restored.is_active)


class VariantImagePreservedOnRegenerationTests(VariantEngineTestCase):
    def test_variant_image_survives_regeneration(self):
        self._add_color_size()
        generate_variants(self.product)
        variant = self.product.variants.first()
        image = ProductImage.objects.create(
            product=self.product, image="products/gallery/sample.jpg", variant=variant,
        )

        generate_variants(self.product)

        image.refresh_from_db()
        self.assertEqual(image.variant_id, variant.pk)


class VariantFieldContractTests(VariantEngineTestCase):
    def test_compare_at_price_and_cost_default_to_none(self):
        add_product_option(self.product, label="رنگ", values=["سبز"])
        generate_variants(self.product)
        variant = self.product.variants.first()
        self.assertIsNone(variant.compare_at_price)
        self.assertIsNone(variant.cost)

    def test_negative_weight_rejected_by_full_clean(self):
        add_product_option(self.product, label="رنگ", values=["سبز"])
        generate_variants(self.product)
        variant = self.product.variants.first()
        variant.weight_grams = -10
        with self.assertRaises(Exception):
            variant.full_clean()

    def test_low_stock_threshold_and_dimensions_round_trip(self):
        add_product_option(self.product, label="رنگ", values=["سبز"])
        generate_variants(self.product)
        variant = self.product.variants.first()
        variant.low_stock_threshold = 5
        variant.weight_grams = 250
        variant.length_mm = 100
        variant.width_mm = 50
        variant.height_mm = 20
        variant.full_clean(exclude=["normalized_attribute", "normalized_value"])
        variant.save()
        variant.refresh_from_db()
        self.assertEqual(variant.low_stock_threshold, 5)
        self.assertEqual(variant.weight_grams, 250)
        self.assertEqual(variant.length_mm, 100)


class DefaultVariantTests(VariantEngineTestCase):
    def test_set_default_variant(self):
        self._add_color_size()
        generate_variants(self.product)
        variant = self.product.variants.exclude(is_default=True).first()
        set_default_variant(self.product, variant)
        variant.refresh_from_db()
        self.assertTrue(variant.is_default)
        self.assertEqual(self.product.variants.filter(is_default=True).count(), 1)

    def test_setting_new_default_clears_old_one(self):
        self._add_color_size()
        generate_variants(self.product)
        old_default = self.product.variants.get(is_default=True)
        new_default = self.product.variants.exclude(pk=old_default.pk).first()

        set_default_variant(self.product, new_default)

        old_default.refresh_from_db()
        self.assertFalse(old_default.is_default)

    def test_cannot_set_obsolete_variant_as_default(self):
        color, size = self._add_color_size()
        generate_variants(self.product)
        yellow = color.values.get(label="زرد")
        variant = self.product.variants.get(value="زرد / S")
        remove_option_value(yellow)
        generate_variants(self.product)
        variant.refresh_from_db()
        with self.assertRaises(VariantEngineError):
            set_default_variant(self.product, variant)

    def test_cross_product_default_rejected(self):
        other_vendor = Vendor.objects.create(store=self.store, name="ف2", slug="ve-shop2")
        other_product = Product.objects.create(
            store=self.store, vendor=other_vendor, category=self.category, name="کالای دیگر",
            slug="ve-other-product", sku="VE-TS2", price=Decimal("100000"),
            product_type=Product.ProductType.VARIABLE,
        )
        add_product_option(other_product, label="رنگ", values=["سبز"])
        generate_variants(other_product)
        other_variant = other_product.variants.first()

        with self.assertRaises(VariantEngineError):
            set_default_variant(self.product, other_variant)

    def test_default_reassigned_when_current_default_becomes_obsolete(self):
        color, size = self._add_color_size()
        generate_variants(self.product)
        default_variant = self.product.variants.get(is_default=True)
        default_label = default_variant.value
        default_color_label = default_label.split(" / ")[0]
        default_color_value = color.values.get(label=default_color_label)

        remove_option_value(default_color_value)
        generate_variants(self.product)

        self.assertEqual(self.product.variants.filter(is_default=True, is_active=True).count(), 1)
        new_default = self.product.variants.get(is_default=True)
        self.assertFalse(new_default.is_obsolete)


class OptionInputTypeTests(VariantEngineTestCase):
    def test_defaults_to_text(self):
        option = add_product_option(self.product, label="کشور سازنده", values=["ایرانی", "ایتالیایی"])
        self.assertEqual(option.input_type, ProductOption.InputType.TEXT)

    def test_color_input_type_persisted(self):
        option = add_product_option(self.product, label="رنگ", input_type=ProductOption.InputType.COLOR)
        self.assertEqual(option.input_type, ProductOption.InputType.COLOR)


class AddManualVariantTests(VariantEngineTestCase):
    def test_creates_single_combination(self):
        color, size = self._add_color_size()
        green = color.values.get(label="سبز")
        m = size.values.get(label="M")

        variant = add_manual_variant(self.product, {color.pk: green.pk, size.pk: m.pk})

        self.assertEqual(variant.value, "سبز / M")
        self.assertEqual(self.product.variants.count(), 1)
        self.assertEqual(variant.option_values.count(), 2)

    def test_missing_axis_value_raises(self):
        color, size = self._add_color_size()
        green = color.values.get(label="سبز")
        with self.assertRaises(VariantEngineError):
            add_manual_variant(self.product, {color.pk: green.pk})

    def test_no_active_axes_raises(self):
        with self.assertRaises(VariantEngineError):
            add_manual_variant(self.product, {})

    def test_idempotent_same_combination_returns_existing(self):
        color, size = self._add_color_size()
        green = color.values.get(label="سبز")
        m = size.values.get(label="M")
        first = add_manual_variant(self.product, {color.pk: green.pk, size.pk: m.pk})
        second = add_manual_variant(self.product, {color.pk: green.pk, size.pk: m.pk})
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(self.product.variants.count(), 1)

    def test_scissors_country_of_origin_example(self):
        scissors = Product.objects.create(
            store=self.store, vendor=self.vendor, category=self.category, name="قیچی",
            slug="ve-scissors", sku="VE-SC1", price=Decimal("100000"),
            product_type=Product.ProductType.VARIABLE,
        )
        country = add_product_option(scissors, label="کشور سازنده", values=["ایرانی", "ایتالیایی"])
        iranian = country.values.get(label="ایرانی")
        italian = country.values.get(label="ایتالیایی")

        v_iranian = add_manual_variant(scissors, {country.pk: iranian.pk})
        v_italian = add_manual_variant(scissors, {country.pk: italian.pk})

        self.assertEqual(scissors.variants.count(), 2)
        self.assertNotEqual(v_iranian.combination_key, v_italian.combination_key)
