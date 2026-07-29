from decimal import Decimal

from django.test import TestCase

from apps.catalog.models import Attribute, Category, Product, ProductAttributeValue, Vendor
from apps.catalog.services.attribute_service import create_attribute
from apps.catalog.services.category_schema_service import (
    CategorySchemaError,
    add_category_attribute,
    cleanup_orphaned_attribute_values,
    orphaned_product_attribute_values,
    remove_category_attribute,
    reorder_category_attributes,
    resolve_category_schema,
    update_category_attribute,
)
from apps.stores.models import Store


def _akhlaghi():
    return Store.objects.get(slug="akhlaghi")


class CategorySchemaTestCase(TestCase):
    def setUp(self):
        self.store = _akhlaghi()
        self.clothing = Category.objects.create(store=self.store, name="پوشاک", slug="cs-clothing")
        self.mens = Category.objects.create(store=self.store, name="مردانه", slug="cs-mens", parent=self.clothing)
        self.tshirts = Category.objects.create(store=self.store, name="تی‌شرت", slug="cs-tshirts", parent=self.mens)
        self.material = create_attribute(self.store, label="جنس")
        self.season = create_attribute(self.store, label="فصل")
        self.fit = create_attribute(self.store, label="فیت")


class AddCategoryAttributeTests(CategorySchemaTestCase):
    def test_adds_entry(self):
        entry = add_category_attribute(self.clothing, self.material, is_required=True)
        self.assertTrue(entry.is_required)

    def test_duplicate_rejected(self):
        add_category_attribute(self.clothing, self.material)
        with self.assertRaises(CategorySchemaError):
            add_category_attribute(self.clothing, self.material)

    def test_cross_store_attribute_rejected(self):
        other_store = Store.objects.create(name="فروشگاه دیگر", slug="cs-other", status=Store.Status.ACTIVE)
        other_attr = create_attribute(other_store, label="جنس دیگر")
        with self.assertRaises(CategorySchemaError):
            add_category_attribute(self.clothing, other_attr)

    def test_reorder(self):
        e1 = add_category_attribute(self.clothing, self.material)
        e2 = add_category_attribute(self.clothing, self.season)
        reorder_category_attributes(self.clothing, [e2.pk, e1.pk])
        e1.refresh_from_db()
        e2.refresh_from_db()
        self.assertEqual(e2.display_order, 0)
        self.assertEqual(e1.display_order, 1)

    def test_update_and_remove(self):
        entry = add_category_attribute(self.clothing, self.material)
        update_category_attribute(entry, is_required=True, help_text="جنس پارچه را وارد کنید")
        entry.refresh_from_db()
        self.assertTrue(entry.is_required)
        remove_category_attribute(entry)
        self.assertEqual(self.clothing.attribute_schema_entries.count(), 0)


class ResolveCategorySchemaTests(CategorySchemaTestCase):
    def test_direct_only(self):
        add_category_attribute(self.tshirts, self.fit)
        resolved = resolve_category_schema(self.tshirts)
        self.assertEqual(len(resolved), 1)
        self.assertFalse(resolved[0].is_inherited)

    def test_single_level_inheritance(self):
        add_category_attribute(self.mens, self.material)
        resolved = resolve_category_schema(self.tshirts)
        self.assertEqual(len(resolved), 1)
        self.assertTrue(resolved[0].is_inherited)
        self.assertEqual(resolved[0].source_category, self.mens)

    def test_multi_level_inheritance(self):
        add_category_attribute(self.clothing, self.material)
        add_category_attribute(self.mens, self.season)
        add_category_attribute(self.tshirts, self.fit)
        resolved = resolve_category_schema(self.tshirts)
        attribute_labels = {e.attribute.label for e in resolved}
        self.assertEqual(attribute_labels, {"جنس", "فصل", "فیت"})

    def test_direct_mapping_wins_over_inherited_no_duplicates(self):
        add_category_attribute(self.clothing, self.material, group="عمومی", is_required=False)
        add_category_attribute(self.tshirts, self.material, group="پارچه", is_required=True)
        resolved = resolve_category_schema(self.tshirts)
        material_entries = [e for e in resolved if e.attribute.pk == self.material.pk]
        self.assertEqual(len(material_entries), 1)
        self.assertEqual(material_entries[0].group, "پارچه")
        self.assertTrue(material_entries[0].is_required)
        self.assertFalse(material_entries[0].is_inherited)

    def test_non_inherited_mapping_does_not_propagate(self):
        add_category_attribute(self.clothing, self.material, is_inherited_by_children=False)
        resolved = resolve_category_schema(self.tshirts)
        self.assertEqual(len(resolved), 0)

    def test_ordering_by_group_then_display_order(self):
        add_category_attribute(self.tshirts, self.fit, group="ب", group_order=1, display_order=0)
        add_category_attribute(self.tshirts, self.material, group="آ", group_order=0, display_order=0)
        resolved = resolve_category_schema(self.tshirts)
        self.assertEqual(resolved[0].attribute.pk, self.material.pk)
        self.assertEqual(resolved[1].attribute.pk, self.fit.pk)

    def test_filterable_comparable_searchable_override_semantics(self):
        material = create_attribute(self.store, label="متریال", is_filterable=True, is_comparable=False)
        entry = add_category_attribute(self.clothing, material)
        self.assertTrue(entry.is_filterable)  # inherits Attribute default (True)
        self.assertFalse(entry.is_comparable)  # inherits Attribute default (False)
        update_category_attribute(entry, is_comparable_override=True)
        entry.refresh_from_db()
        self.assertTrue(entry.is_comparable)  # explicit override wins

    def test_store_isolation_categories_never_leak(self):
        other_store = Store.objects.create(name="فروشگاه دیگر", slug="cs-other2", status=Store.Status.ACTIVE)
        other_category = Category.objects.create(store=other_store, name="دسته دیگر", slug="cs-other2-cat")
        other_attr = create_attribute(other_store, label="ویژگی دیگر")
        add_category_attribute(other_category, other_attr)
        resolved = resolve_category_schema(self.clothing)
        self.assertEqual(len(resolved), 0)


class OrphanedAttributeValueTests(CategorySchemaTestCase):
    def setUp(self):
        super().setUp()
        self.vendor = Vendor.objects.create(store=self.store, name="فروشنده", slug="cs-vendor")
        self.shoes = Category.objects.create(store=self.store, name="کفش", slug="cs-shoes")
        self.product = Product.objects.create(
            store=self.store, vendor=self.vendor, category=self.tshirts, name="تی‌شرت مردانه",
            slug="cs-product", sku="CS-SKU1", price=Decimal("200000"),
        )

    def test_no_orphans_when_schema_matches(self):
        add_category_attribute(self.tshirts, self.material)
        ProductAttributeValue.objects.create(product=self.product, attribute=self.material, text_value="نخی")
        self.assertEqual(orphaned_product_attribute_values(self.product).count(), 0)

    def test_category_change_creates_orphans_without_deleting(self):
        add_category_attribute(self.tshirts, self.fit)
        ProductAttributeValue.objects.create(product=self.product, attribute=self.fit, text_value="اسلیم")

        self.product.category = self.shoes
        self.product.save(update_fields=["category"])

        orphaned = orphaned_product_attribute_values(self.product)
        self.assertEqual(orphaned.count(), 1)
        # هنوز در دیتابیس موجود است — چیزی خودکار حذف نشده
        self.assertTrue(ProductAttributeValue.objects.filter(product=self.product, attribute=self.fit).exists())

    def test_overlapping_schema_preserves_shared_attribute(self):
        add_category_attribute(self.tshirts, self.material)
        add_category_attribute(self.shoes, self.material)
        ProductAttributeValue.objects.create(product=self.product, attribute=self.material, text_value="چرم")

        self.product.category = self.shoes
        self.product.save(update_fields=["category"])

        self.assertEqual(orphaned_product_attribute_values(self.product).count(), 0)

    def test_explicit_cleanup_deletes_orphans(self):
        add_category_attribute(self.tshirts, self.fit)
        ProductAttributeValue.objects.create(product=self.product, attribute=self.fit, text_value="اسلیم")
        self.product.category = self.shoes
        self.product.save(update_fields=["category"])

        deleted_count = cleanup_orphaned_attribute_values(self.product)

        self.assertEqual(deleted_count, 1)
        self.assertFalse(ProductAttributeValue.objects.filter(product=self.product, attribute=self.fit).exists())

    def test_completely_different_schema_orphans_everything(self):
        add_category_attribute(self.tshirts, self.material)
        add_category_attribute(self.tshirts, self.fit)
        ProductAttributeValue.objects.create(product=self.product, attribute=self.material, text_value="نخی")
        ProductAttributeValue.objects.create(product=self.product, attribute=self.fit, text_value="اسلیم")

        self.product.category = self.shoes  # no schema entries at all on shoes
        self.product.save(update_fields=["category"])

        self.assertEqual(orphaned_product_attribute_values(self.product).count(), 2)
