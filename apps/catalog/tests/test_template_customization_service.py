from django.test import TestCase

from apps.catalog.models import (
    Attribute,
    AttributeValue,
    Category,
    CategoryAttributeSchema,
    IndustryTemplate,
    IndustryTemplateAttribute,
    IndustryTemplateAttributeValue,
    IndustryTemplateCategory,
    IndustryTemplateCategoryAttributeMapping,
    StoreIndustryInstallation,
)
from apps.catalog.services.industry_template_service import install_industry_template
from apps.catalog.services.template_customization_service import (
    detect_installation_customizations,
    is_attribute_customized,
    is_category_customized,
    is_schema_entry_customized,
    is_value_customized,
)
from apps.stores.models import Store


def _akhlaghi():
    return Store.objects.get(slug="akhlaghi")


def _install_clothing(store, slug="cust-clothing"):
    template = IndustryTemplate.objects.create(
        slug=slug, name="پوشاک", version=1, readiness=IndustryTemplate.Readiness.PRODUCTION_READY,
    )
    root = IndustryTemplateCategory.objects.create(industry_template=template, code="root", name="پوشاک")
    child = IndustryTemplateCategory.objects.create(
        industry_template=template, code="mens", name="مردانه", parent=root,
    )
    material = IndustryTemplateAttribute.objects.create(
        industry_template=template, code="material", label="جنس", data_type=Attribute.DataType.SELECT,
        display_type=Attribute.DisplayType.DROPDOWN,
    )
    IndustryTemplateAttributeValue.objects.create(template_attribute=material, label="نخی")
    IndustryTemplateCategoryAttributeMapping.objects.create(
        template_category=child, template_attribute=material, group="عمومی", is_required=True, is_filterable=True,
    )
    install_industry_template(store, template)
    return template


class CategoryCustomizationTests(TestCase):
    def setUp(self):
        self.store = _akhlaghi()
        self.template = _install_clothing(self.store, slug="cc-cat")
        self.category = Category.objects.get(store=self.store, name="مردانه")

    def test_untouched_installed_category_is_not_customized(self):
        self.assertFalse(is_category_customized(self.category))

    def test_renamed_category_is_customized(self):
        self.category.name = "مردانه ویژه"
        self.category.save()
        self.assertTrue(is_category_customized(self.category))

    def test_reordered_category_is_not_flagged_by_name_check(self):
        # order isn't part of is_category_customized's identity check (only name/icon/parent/active) —
        # this documents that scope precisely rather than silently over- or under-claiming.
        self.category.order = 99
        self.category.save()
        self.assertFalse(is_category_customized(self.category))

    def test_disabled_category_is_customized(self):
        self.category.is_active = False
        self.category.save()
        self.assertTrue(is_category_customized(self.category))

    def test_changed_parent_is_customized(self):
        new_parent = Category.objects.create(store=self.store, name="دسته‌ی جدید", slug="cc-new-parent")
        self.category.parent = new_parent
        self.category.save()
        self.assertTrue(is_category_customized(self.category))

    def test_merchant_created_category_always_customized(self):
        merchant_category = Category.objects.create(store=self.store, name="دستی", slug="cc-manual")
        self.assertTrue(is_category_customized(merchant_category))


class AttributeCustomizationTests(TestCase):
    def setUp(self):
        self.store = _akhlaghi()
        self.template = _install_clothing(self.store, slug="cc-attr")
        self.attribute = Attribute.objects.get(store=self.store, code="material")

    def test_untouched_installed_attribute_is_not_customized(self):
        self.assertFalse(is_attribute_customized(self.attribute))

    def test_renamed_attribute_label_is_customized(self):
        self.attribute.label = "جنس (سفارشی)"
        self.attribute.save()
        self.assertTrue(is_attribute_customized(self.attribute))

    def test_merchant_created_attribute_always_customized(self):
        from apps.catalog.services.attribute_service import create_attribute

        manual = create_attribute(self.store, label="ویژگی دستی", code="cc-manual-attr")
        self.assertTrue(is_attribute_customized(manual))


class ValueCustomizationTests(TestCase):
    def setUp(self):
        self.store = _akhlaghi()
        self.template = _install_clothing(self.store, slug="cc-value")
        self.attribute = Attribute.objects.get(store=self.store, code="material")
        self.value = self.attribute.values.get(label="نخی")

    def test_untouched_installed_value_is_not_customized(self):
        self.assertFalse(is_value_customized(self.value))

    def test_added_value_by_merchant_is_customized(self):
        added = AttributeValue.objects.create(attribute=self.attribute, label="پشمی")
        self.assertTrue(is_value_customized(added))

    def test_renamed_value_is_customized(self):
        self.value.label = "نخی (سفارشی)"
        self.value.save()
        self.assertTrue(is_value_customized(self.value))


class SchemaEntryCustomizationTests(TestCase):
    def setUp(self):
        self.store = _akhlaghi()
        self.template = _install_clothing(self.store, slug="cc-schema")
        self.category = Category.objects.get(store=self.store, name="مردانه")
        self.attribute = Attribute.objects.get(store=self.store, code="material")
        self.entry = CategoryAttributeSchema.objects.get(category=self.category, attribute=self.attribute)

    def test_untouched_installed_entry_is_not_customized(self):
        self.assertFalse(is_schema_entry_customized(self.entry))

    def test_changed_required_state_is_customized(self):
        self.entry.is_required = False
        self.entry.save()
        self.assertTrue(is_schema_entry_customized(self.entry))

    def test_filterable_override_change_is_customized(self):
        self.entry.is_filterable_override = False
        self.entry.save()
        self.assertTrue(is_schema_entry_customized(self.entry))

    def test_manual_entry_without_source_always_customized(self):
        from apps.catalog.services.category_schema_service import add_category_attribute
        from apps.catalog.services.attribute_service import create_attribute

        manual_attr = create_attribute(self.store, label="ویژگی دستی۲", code="cc-manual-attr-2")
        manual_entry = add_category_attribute(self.category, manual_attr)
        self.assertTrue(is_schema_entry_customized(manual_entry))


class DetectInstallationCustomizationsTests(TestCase):
    def setUp(self):
        self.store = _akhlaghi()
        self.template = _install_clothing(self.store, slug="cc-detect")
        self.installation = StoreIndustryInstallation.objects.get(store=self.store)

    def test_no_customizations_on_fresh_install(self):
        report = detect_installation_customizations(self.installation)
        self.assertEqual(report["customized_category_codes"], set())
        self.assertEqual(report["customized_attribute_codes"], set())

    def test_detects_renamed_category(self):
        category = Category.objects.get(store=self.store, name="مردانه")
        category.name = "مردانه سفارشی"
        category.save()
        report = detect_installation_customizations(self.installation)
        self.assertIn("mens", report["customized_category_codes"])

    def test_other_store_isolation(self):
        other_store = Store.objects.create(name="فروشگاه دیگر", slug="cc-other-store", status=Store.Status.ACTIVE)
        _install_clothing(other_store, slug="cc-detect-other")
        other_category = Category.objects.get(store=other_store, name="مردانه")
        other_category.name = "سفارشی در فروشگاه دیگر"
        other_category.save()
        # this Store's report must not reflect the other Store's customization
        report = detect_installation_customizations(self.installation)
        self.assertNotIn("mens", report["customized_category_codes"])
