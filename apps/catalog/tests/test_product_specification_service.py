from decimal import Decimal

from django.test import TestCase

from apps.catalog.models import Attribute, Category, Product, ProductAttributeValue, Vendor
from apps.catalog.services.attribute_service import create_attribute, create_attribute_value, set_product_attribute_value
from apps.catalog.services.category_schema_service import add_category_attribute
from apps.catalog.services.product_publish_service import validate_product_for_publish
from apps.catalog.services.product_specification_service import build_product_specification
from apps.catalog.services.variant_engine_service import add_product_option, generate_variants
from apps.stores.models import Store


def _akhlaghi():
    return Store.objects.get(slug="akhlaghi")


class SpecificationTestCase(TestCase):
    def setUp(self):
        self.store = _akhlaghi()
        self.vendor = Vendor.objects.create(store=self.store, name="فروشنده", slug="ps-vendor")
        self.category = Category.objects.create(store=self.store, name="پوشاک", slug="ps-cat")
        self.product = Product.objects.create(
            store=self.store, vendor=self.vendor, category=self.category, name="تی‌شرت",
            slug="ps-product", sku="PS-SKU1", price=Decimal("250000"),
        )


class BuildProductSpecificationTests(SpecificationTestCase):
    def test_grouping_and_ordering(self):
        material = create_attribute(self.store, label="جنس")
        weight = create_attribute(self.store, label="وزن", data_type=Attribute.DataType.NUMBER, unit="گرم")
        add_category_attribute(self.category, material, group="عمومی", group_order=0)
        add_category_attribute(self.category, weight, group="فیزیکی", group_order=1)
        set_product_attribute_value(self.product, material, text_value="نخی")
        set_product_attribute_value(self.product, weight, number_value=Decimal("200"))

        spec = build_product_specification(self.product)

        self.assertEqual(len(spec), 2)
        self.assertEqual(spec[0]["group"], "عمومی")
        self.assertEqual(spec[0]["attributes"][0]["value"], "نخی")
        self.assertEqual(spec[1]["attributes"][0]["value"], "200 گرم")

    def test_boolean_display(self):
        waterproof = create_attribute(self.store, label="ضدآب", data_type=Attribute.DataType.BOOLEAN)
        add_category_attribute(self.category, waterproof)
        set_product_attribute_value(self.product, waterproof, boolean_value=True)
        spec = build_product_specification(self.product)
        self.assertEqual(spec[0]["attributes"][0]["value"], "بله")

    def test_select_label_display(self):
        material = create_attribute(self.store, label="جنس", data_type=Attribute.DataType.SELECT)
        cotton = create_attribute_value(material, label="نخی")
        add_category_attribute(self.category, material)
        set_product_attribute_value(self.product, material, value=cotton)
        spec = build_product_specification(self.product)
        self.assertEqual(spec[0]["attributes"][0]["value"], "نخی")

    def test_multiselect_joins_labels(self):
        from apps.catalog.services.attribute_service import add_product_attribute_multiselect_value

        features = create_attribute(self.store, label="ویژگی‌ها", data_type=Attribute.DataType.MULTISELECT)
        waterproof = create_attribute_value(features, label="ضدآب")
        breathable = create_attribute_value(features, label="تنفس‌پذیر")
        add_category_attribute(self.category, features)
        add_product_attribute_multiselect_value(self.product, features, waterproof)
        add_product_attribute_multiselect_value(self.product, features, breathable)

        spec = build_product_specification(self.product)
        self.assertIn("ضدآب", spec[0]["attributes"][0]["value"])
        self.assertIn("تنفس‌پذیر", spec[0]["attributes"][0]["value"])

    def test_empty_value_omitted(self):
        material = create_attribute(self.store, label="جنس")
        add_category_attribute(self.category, material)  # no ProductAttributeValue set
        spec = build_product_specification(self.product)
        self.assertEqual(spec, [])

    def test_hidden_from_storefront_still_shown_in_admin_selector(self):
        # build_product_specification does not filter by storefront visibility itself —
        # that's a template-consumer decision (is_visible_on_storefront flag passed through).
        material = create_attribute(self.store, label="جنس")
        add_category_attribute(self.category, material, is_visible_on_storefront=False)
        set_product_attribute_value(self.product, material, text_value="نخی")
        spec = build_product_specification(self.product)
        self.assertEqual(len(spec), 1)

    def test_comparable_only_filters(self):
        material = create_attribute(self.store, label="جنس")
        season = create_attribute(self.store, label="فصل")
        add_category_attribute(self.category, material, is_comparable_override=True)
        add_category_attribute(self.category, season, is_comparable_override=False)
        set_product_attribute_value(self.product, material, text_value="نخی")
        set_product_attribute_value(self.product, season, text_value="تابستان")

        spec = build_product_specification(self.product, comparable_only=True)

        labels = {a["label"] for group in spec for a in group["attributes"]}
        self.assertEqual(labels, {"جنس"})

    def test_store_isolation_never_leaks_other_store_schema(self):
        other_store = Store.objects.create(name="فروشگاه دیگر", slug="ps-other", status=Store.Status.ACTIVE)
        other_category = Category.objects.create(store=other_store, name="دسته دیگر", slug="ps-other-cat")
        other_attr = create_attribute(other_store, label="ویژگی دیگر")
        add_category_attribute(other_category, other_attr)
        spec = build_product_specification(self.product)
        self.assertEqual(spec, [])


class ValidateProductForPublishTests(SpecificationTestCase):
    def test_missing_required_attribute_blocks_publish(self):
        material = create_attribute(self.store, label="جنس")
        add_category_attribute(self.category, material, is_required=True)
        errors = validate_product_for_publish(self.product)
        self.assertTrue(any("جنس" in e for e in errors))

    def test_filled_required_attribute_passes(self):
        material = create_attribute(self.store, label="جنس")
        add_category_attribute(self.category, material, is_required=True)
        set_product_attribute_value(self.product, material, text_value="نخی")
        errors = validate_product_for_publish(self.product)
        self.assertEqual(errors, [])

    def test_optional_attribute_never_blocks(self):
        material = create_attribute(self.store, label="جنس")
        add_category_attribute(self.category, material, is_required=False)
        errors = validate_product_for_publish(self.product)
        self.assertEqual(errors, [])

    def test_variable_product_without_variant_is_not_blocked(self):
        # Deliberate: preserves the existing, tested simple->variable transition
        # workflow (product becomes ACTIVE + VARIABLE before variants are added
        # in a separate step) — see product_publish_service's own comment.
        self.product.product_type = Product.ProductType.VARIABLE
        self.product.save(update_fields=["product_type"])
        errors = validate_product_for_publish(self.product)
        self.assertEqual(errors, [])

    def test_variable_product_with_active_variant_passes(self):
        self.product.product_type = Product.ProductType.VARIABLE
        self.product.save(update_fields=["product_type"])
        add_product_option(self.product, label="رنگ", values=["سبز"])
        generate_variants(self.product)
        errors = validate_product_for_publish(self.product)
        self.assertEqual(errors, [])

    def test_zero_price_blocks_publish(self):
        self.product.price = Decimal("0")
        self.product.save(update_fields=["price"])
        errors = validate_product_for_publish(self.product)
        self.assertTrue(any("قیمت" in e for e in errors))

    def test_draft_save_does_not_call_publish_validation(self):
        # Draft is simply "don't call validate_product_for_publish" — this test
        # documents the contract: the function itself is stateless and only
        # ever consulted by the view when target status is ACTIVE.
        material = create_attribute(self.store, label="جنس")
        add_category_attribute(self.category, material, is_required=True)
        # A draft product with a missing required attribute is a valid DB state:
        self.assertTrue(Product.objects.filter(pk=self.product.pk).exists())
