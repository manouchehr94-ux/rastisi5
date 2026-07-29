from decimal import Decimal

from django.test import TestCase

from apps.catalog.models import Attribute, AttributeValue, Category, Product, ProductAttributeValue, Vendor
from apps.catalog.services.attribute_service import (
    AttributeError_,
    AttributeInUseError,
    activate_attribute,
    add_product_attribute_multiselect_value,
    archive_attribute,
    archive_attribute_value,
    can_delete_attribute,
    can_delete_attribute_value,
    create_attribute,
    create_attribute_value,
    delete_attribute,
    delete_attribute_value,
    remove_product_attribute_value,
    reorder_attribute_values,
    set_product_attribute_value,
    update_attribute,
    update_attribute_value,
)
from apps.stores.models import Store


def _akhlaghi():
    return Store.objects.get(slug="akhlaghi")


class AttributeServiceTestCase(TestCase):
    def setUp(self):
        self.store = _akhlaghi()
        self.vendor = Vendor.objects.create(store=self.store, name="فروشنده", slug="as-shop")
        self.category = Category.objects.create(store=self.store, name="دسته", slug="as-cat")
        self.product = Product.objects.create(
            store=self.store, vendor=self.vendor, category=self.category, name="کالا",
            slug="as-product", sku="AS-SKU1", price=Decimal("100000"),
        )


class CreateAttributeTests(AttributeServiceTestCase):
    def test_creates_with_auto_code(self):
        attribute = create_attribute(self.store, label="جنس")
        self.assertTrue(attribute.code)
        self.assertEqual(attribute.data_type, Attribute.DataType.TEXT)

    def test_blank_label_rejected(self):
        with self.assertRaises(AttributeError_):
            create_attribute(self.store, label="   ")

    def test_duplicate_explicit_code_rejected(self):
        create_attribute(self.store, label="جنس", code="material")
        with self.assertRaises(AttributeError_):
            create_attribute(self.store, label="جنس دو", code="material")

    def test_auto_generated_code_never_collides(self):
        first = create_attribute(self.store, label="جنس")
        second = create_attribute(self.store, label="جنس")
        self.assertNotEqual(first.code, second.code)

    def test_color_type_rejects_dropdown_display(self):
        with self.assertRaises(AttributeError_):
            create_attribute(
                self.store, label="رنگ", data_type=Attribute.DataType.COLOR,
                display_type=Attribute.DisplayType.DROPDOWN,
            )
        # this one should be fine (swatch is compatible with SELECT)
        attr = create_attribute(
            self.store, label="رنگ", data_type=Attribute.DataType.SELECT,
            display_type=Attribute.DisplayType.SWATCH,
        )
        self.assertEqual(attr.display_type, Attribute.DisplayType.SWATCH)

    def test_text_type_rejects_swatch_display(self):
        with self.assertRaises(AttributeError_):
            create_attribute(
                self.store, label="گارانتی", data_type=Attribute.DataType.TEXT,
                display_type=Attribute.DisplayType.SWATCH,
            )

    def test_category_from_other_store_rejected(self):
        other_store = Store.objects.create(name="فروشگاه دیگر", slug="as-other", status=Store.Status.ACTIVE)
        other_category = Category.objects.create(store=other_store, name="دسته دیگر", slug="as-other-cat")
        with self.assertRaises(AttributeError_):
            create_attribute(self.store, label="جنس", category=other_category)

    def test_variant_axis_eligible_flag(self):
        attribute = create_attribute(self.store, label="رنگ", is_variant_axis=True)
        self.assertTrue(attribute.is_variant_axis)


class UpdateArchiveDeleteAttributeTests(AttributeServiceTestCase):
    def test_update_changes_fields(self):
        attribute = create_attribute(self.store, label="جنس")
        update_attribute(attribute, label="جنس محصول", is_filterable=True)
        attribute.refresh_from_db()
        self.assertEqual(attribute.label, "جنس محصول")
        self.assertTrue(attribute.is_filterable)

    def test_archive_and_activate(self):
        attribute = create_attribute(self.store, label="جنس")
        archive_attribute(attribute)
        attribute.refresh_from_db()
        self.assertFalse(attribute.is_active)
        activate_attribute(attribute)
        attribute.refresh_from_db()
        self.assertTrue(attribute.is_active)

    def test_delete_unused_attribute_succeeds(self):
        attribute = create_attribute(self.store, label="جنس")
        delete_attribute(attribute)
        self.assertFalse(Attribute.objects.filter(pk=attribute.pk).exists())

    def test_delete_used_attribute_blocked(self):
        attribute = create_attribute(self.store, label="جنس")
        set_product_attribute_value(self.product, attribute, text_value="نخی")
        with self.assertRaises(AttributeInUseError):
            can_delete_attribute(attribute)
        with self.assertRaises(AttributeInUseError):
            delete_attribute(attribute)
        self.assertTrue(Attribute.objects.filter(pk=attribute.pk).exists())


class AttributeValueTests(AttributeServiceTestCase):
    def test_create_value_auto_fills_internal_value(self):
        attribute = create_attribute(self.store, label="رنگ", data_type=Attribute.DataType.SELECT)
        value = create_attribute_value(attribute, label="سبز")
        self.assertEqual(value.value, "سبز")

    def test_duplicate_label_rejected(self):
        attribute = create_attribute(self.store, label="رنگ", data_type=Attribute.DataType.SELECT)
        create_attribute_value(attribute, label="سبز")
        with self.assertRaises(AttributeError_):
            create_attribute_value(attribute, label="سبز")

    def test_reorder_values(self):
        attribute = create_attribute(self.store, label="رنگ", data_type=Attribute.DataType.SELECT)
        v1 = create_attribute_value(attribute, label="سبز")
        v2 = create_attribute_value(attribute, label="آبی")
        reorder_attribute_values(attribute, [v2.pk, v1.pk])
        v1.refresh_from_db()
        v2.refresh_from_db()
        self.assertEqual(v2.display_order, 0)
        self.assertEqual(v1.display_order, 1)

    def test_update_value(self):
        attribute = create_attribute(self.store, label="رنگ", data_type=Attribute.DataType.SELECT)
        value = create_attribute_value(attribute, label="سبز")
        update_attribute_value(value, color_hex="#00ff00")
        value.refresh_from_db()
        self.assertEqual(value.color_hex, "#00ff00")

    def test_delete_unused_value_succeeds(self):
        attribute = create_attribute(self.store, label="رنگ", data_type=Attribute.DataType.SELECT)
        value = create_attribute_value(attribute, label="سبز")
        delete_attribute_value(value)
        self.assertFalse(AttributeValue.objects.filter(pk=value.pk).exists())

    def test_delete_used_value_blocked(self):
        attribute = create_attribute(self.store, label="رنگ", data_type=Attribute.DataType.SELECT)
        value = create_attribute_value(attribute, label="سبز")
        set_product_attribute_value(self.product, attribute, value=value)
        with self.assertRaises(AttributeInUseError):
            can_delete_attribute_value(value)
        with self.assertRaises(AttributeInUseError):
            delete_attribute_value(value)

    def test_archive_value(self):
        attribute = create_attribute(self.store, label="رنگ", data_type=Attribute.DataType.SELECT)
        value = create_attribute_value(attribute, label="سبز")
        archive_attribute_value(value)
        value.refresh_from_db()
        self.assertFalse(value.is_active)


class ProductDescriptiveAttributeTests(AttributeServiceTestCase):
    def test_text_assignment(self):
        attribute = create_attribute(self.store, label="گارانتی", data_type=Attribute.DataType.TEXT)
        assignment = set_product_attribute_value(self.product, attribute, text_value="۱۲ ماه")
        self.assertEqual(assignment.text_value, "۱۲ ماه")

    def test_numeric_assignment(self):
        attribute = create_attribute(self.store, label="وزن خالص", data_type=Attribute.DataType.NUMBER)
        assignment = set_product_attribute_value(self.product, attribute, number_value=Decimal("250"))
        self.assertEqual(assignment.number_value, Decimal("250"))

    def test_boolean_assignment(self):
        attribute = create_attribute(self.store, label="ضدآب", data_type=Attribute.DataType.BOOLEAN)
        assignment = set_product_attribute_value(self.product, attribute, boolean_value=True)
        self.assertTrue(assignment.boolean_value)

    def test_single_select_assignment(self):
        attribute = create_attribute(self.store, label="جنس", data_type=Attribute.DataType.SELECT)
        cotton = create_attribute_value(attribute, label="نخی")
        assignment = set_product_attribute_value(self.product, attribute, value=cotton)
        self.assertEqual(assignment.value_id, cotton.pk)

    def test_multiselect_assignment_multiple_rows(self):
        attribute = create_attribute(self.store, label="ویژگی‌های خاص", data_type=Attribute.DataType.MULTISELECT)
        waterproof = create_attribute_value(attribute, label="ضدآب")
        wireless = create_attribute_value(attribute, label="بی‌سیم")
        add_product_attribute_multiselect_value(self.product, attribute, waterproof)
        add_product_attribute_multiselect_value(self.product, attribute, wireless)
        self.assertEqual(
            ProductAttributeValue.objects.filter(product=self.product, attribute=attribute).count(), 2
        )

    def test_setting_single_value_twice_replaces_not_duplicates(self):
        attribute = create_attribute(self.store, label="گارانتی", data_type=Attribute.DataType.TEXT)
        set_product_attribute_value(self.product, attribute, text_value="۶ ماه")
        set_product_attribute_value(self.product, attribute, text_value="۱۲ ماه")
        assignments = ProductAttributeValue.objects.filter(product=self.product, attribute=attribute)
        self.assertEqual(assignments.count(), 1)
        self.assertEqual(assignments.first().text_value, "۱۲ ماه")

    def test_invalid_type_missing_number_value_rejected(self):
        attribute = create_attribute(self.store, label="وزن خالص", data_type=Attribute.DataType.NUMBER)
        with self.assertRaises(AttributeError_):
            set_product_attribute_value(self.product, attribute, number_value=None)

    def test_select_without_value_rejected(self):
        attribute = create_attribute(self.store, label="جنس", data_type=Attribute.DataType.SELECT)
        with self.assertRaises(AttributeError_):
            set_product_attribute_value(self.product, attribute, value=None)

    def test_value_from_wrong_attribute_rejected(self):
        attribute_a = create_attribute(self.store, label="جنس", data_type=Attribute.DataType.SELECT)
        attribute_b = create_attribute(self.store, label="رنگ", data_type=Attribute.DataType.SELECT)
        wrong_value = create_attribute_value(attribute_b, label="سبز")
        with self.assertRaises(AttributeError_):
            set_product_attribute_value(self.product, attribute_a, value=wrong_value)

    def test_cross_store_attribute_rejected(self):
        other_store = Store.objects.create(name="فروشگاه دیگر", slug="as-other2", status=Store.Status.ACTIVE)
        other_attribute = create_attribute(other_store, label="جنس")
        with self.assertRaises(AttributeError_):
            set_product_attribute_value(self.product, other_attribute, text_value="x")

    def test_remove_assignment(self):
        attribute = create_attribute(self.store, label="گارانتی", data_type=Attribute.DataType.TEXT)
        set_product_attribute_value(self.product, attribute, text_value="۱۲ ماه")
        remove_product_attribute_value(self.product, attribute)
        self.assertFalse(
            ProductAttributeValue.objects.filter(product=self.product, attribute=attribute).exists()
        )

    def test_remove_single_multiselect_value(self):
        attribute = create_attribute(self.store, label="ویژگی‌های خاص", data_type=Attribute.DataType.MULTISELECT)
        waterproof = create_attribute_value(attribute, label="ضدآب")
        wireless = create_attribute_value(attribute, label="بی‌سیم")
        add_product_attribute_multiselect_value(self.product, attribute, waterproof)
        add_product_attribute_multiselect_value(self.product, attribute, wireless)
        remove_product_attribute_value(self.product, attribute, waterproof)
        remaining = ProductAttributeValue.objects.filter(product=self.product, attribute=attribute)
        self.assertEqual(remaining.count(), 1)
        self.assertEqual(remaining.first().value_id, wireless.pk)
