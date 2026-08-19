from django.test import TestCase

from apps.catalog.models import (
    Attribute,
    Category,
    CategoryAttributeSchema,
    CategoryRecommendedOption,
    IndustryTemplate,
    IndustryTemplateAttribute,
    IndustryTemplateAttributeValue,
    IndustryTemplateCategory,
    IndustryTemplateCategoryAttributeMapping,
    IndustryTemplateRecommendedOption,
    StoreIndustryInstallation,
)
from apps.catalog.services.industry_template_service import (
    IndustryInstallationError,
    install_industry_template,
)
from apps.stores.models import Store


def _akhlaghi():
    return Store.objects.get(slug="akhlaghi")


def _build_clothing_template():
    template = IndustryTemplate.objects.create(
        slug="clothing", name="پوشاک", version=1, readiness=IndustryTemplate.Readiness.PRODUCTION_READY,
    )
    clothing = IndustryTemplateCategory.objects.create(
        industry_template=template, code="clothing", name="پوشاک", display_order=0,
    )
    mens = IndustryTemplateCategory.objects.create(
        industry_template=template, code="mens", name="مردانه", parent=clothing, display_order=0,
    )
    tshirts = IndustryTemplateCategory.objects.create(
        industry_template=template, code="tshirts", name="تی‌شرت", parent=mens, display_order=0,
    )
    material = IndustryTemplateAttribute.objects.create(
        industry_template=template, code="material", label="جنس", data_type=Attribute.DataType.SELECT,
        display_type=Attribute.DisplayType.DROPDOWN,
    )
    IndustryTemplateAttributeValue.objects.create(template_attribute=material, label="نخی")
    IndustryTemplateAttributeValue.objects.create(template_attribute=material, label="پلی‌استر")
    color = IndustryTemplateAttribute.objects.create(
        industry_template=template, code="color", label="رنگ", data_type=Attribute.DataType.COLOR,
        display_type=Attribute.DisplayType.SWATCH, is_variant_axis=True,
    )
    IndustryTemplateCategoryAttributeMapping.objects.create(
        template_category=tshirts, template_attribute=material, group="عمومی", is_required=True,
    )
    IndustryTemplateRecommendedOption.objects.create(template_category=tshirts, template_attribute=color)
    return template, {"clothing": clothing, "mens": mens, "tshirts": tshirts, "material": material, "color": color}


class InstallIndustryTemplateTests(TestCase):
    def setUp(self):
        self.store = _akhlaghi()
        self.template, self.nodes = _build_clothing_template()

    def test_creates_category_hierarchy(self):
        install_industry_template(self.store, self.template)
        clothing = Category.objects.get(store=self.store, name="پوشاک")
        mens = Category.objects.get(store=self.store, name="مردانه")
        tshirts = Category.objects.get(store=self.store, name="تی‌شرت")
        self.assertIsNone(clothing.parent)
        self.assertEqual(mens.parent_id, clothing.pk)
        self.assertEqual(tshirts.parent_id, mens.pk)

    def test_creates_attributes_and_values(self):
        install_industry_template(self.store, self.template)
        material = Attribute.objects.get(store=self.store, code="material")
        self.assertEqual(material.values.count(), 2)
        self.assertEqual(material.data_type, Attribute.DataType.SELECT)

    def test_creates_category_attribute_schema(self):
        install_industry_template(self.store, self.template)
        tshirts = Category.objects.get(store=self.store, name="تی‌شرت")
        entry = CategoryAttributeSchema.objects.get(category=tshirts)
        self.assertTrue(entry.is_required)
        self.assertEqual(entry.group, "عمومی")

    def test_creates_recommended_options(self):
        install_industry_template(self.store, self.template)
        tshirts = Category.objects.get(store=self.store, name="تی‌شرت")
        self.assertEqual(CategoryRecommendedOption.objects.filter(category=tshirts).count(), 1)

    def test_records_installation(self):
        result = install_industry_template(self.store, self.template)
        installation = StoreIndustryInstallation.objects.get(store=self.store)
        self.assertEqual(installation.industry_template_id, self.template.pk)
        self.assertEqual(installation.installed_version, 1)
        self.assertEqual(result.installation.pk, installation.pk)
        self.assertEqual(len(result.categories_created), 3)

    def test_source_traceability_recorded(self):
        install_industry_template(self.store, self.template)
        tshirts = Category.objects.get(store=self.store, name="تی‌شرت")
        self.assertEqual(tshirts.source_template_category_id, self.nodes["tshirts"].pk)
        material = Attribute.objects.get(store=self.store, code="material")
        self.assertEqual(material.source_template_attribute_id, self.nodes["material"].pk)

    def test_second_installation_rejected(self):
        install_industry_template(self.store, self.template)
        with self.assertRaises(IndustryInstallationError):
            install_industry_template(self.store, self.template)
        self.assertEqual(StoreIndustryInstallation.objects.filter(store=self.store).count(), 1)

    def test_installing_different_template_also_rejected(self):
        install_industry_template(self.store, self.template)
        other_template = IndustryTemplate.objects.create(slug="perfume", name="عطر", version=1)
        with self.assertRaises(IndustryInstallationError):
            install_industry_template(self.store, other_template)

    def test_inactive_template_rejected(self):
        self.template.is_active = False
        self.template.save(update_fields=["is_active"])
        with self.assertRaises(IndustryInstallationError):
            install_industry_template(self.store, self.template)
        self.assertFalse(StoreIndustryInstallation.objects.filter(store=self.store).exists())

    def test_non_production_ready_template_rejected(self):
        """نگاه کنید به ADR-26 — فقط قالب production_ready قابل‌نصب است."""
        self.template.readiness = IndustryTemplate.Readiness.DRAFT
        self.template.save(update_fields=["readiness"])
        with self.assertRaises(IndustryInstallationError):
            install_industry_template(self.store, self.template)
        self.assertFalse(StoreIndustryInstallation.objects.filter(store=self.store).exists())

    def test_reuses_existing_attribute_with_matching_code(self):
        from apps.catalog.services.attribute_service import create_attribute

        existing = create_attribute(self.store, label="جنس محصول موجود", code="material")
        install_industry_template(self.store, self.template)
        self.assertEqual(Attribute.objects.filter(store=self.store, code="material").count(), 1)
        material = Attribute.objects.get(store=self.store, code="material")
        self.assertEqual(material.pk, existing.pk)
        # existing label was NOT overwritten by the template
        self.assertEqual(material.label, "جنس محصول موجود")

    def test_store_isolation_other_store_unaffected(self):
        other_store = Store.objects.create(name="فروشگاه دیگر", slug="its-other", status=Store.Status.ACTIVE)
        install_industry_template(self.store, self.template)
        self.assertFalse(Category.objects.filter(store=other_store).exists())
        self.assertFalse(StoreIndustryInstallation.objects.filter(store=other_store).exists())

    def test_atomic_rollback_on_invalid_category_chain(self):
        # Sabotage: point tshirts' parent at a category from a *different* template
        # so full_clean rejects it mid-installation — nothing should be created.
        other_template = IndustryTemplate.objects.create(slug="test-other-foreign", name="دیگر", version=1)
        foreign_parent = IndustryTemplateCategory.objects.create(
            industry_template=other_template, code="foreign", name="خارجی",
        )
        self.nodes["mens"].parent = None
        self.nodes["mens"].save(update_fields=["parent"])
        IndustryTemplateCategory.objects.filter(pk=self.nodes["tshirts"].pk).update(parent=foreign_parent)

        count_before = Category.objects.filter(store=self.store).count()
        with self.assertRaises(Exception):
            install_industry_template(self.store, self.template)
        self.assertEqual(Category.objects.filter(store=self.store).count(), count_before)
        self.assertFalse(StoreIndustryInstallation.objects.filter(store=self.store).exists())


class IdempotencyReRunTests(TestCase):
    """The chosen idempotency policy is 'reject duplicate' — see ADR-25."""

    def setUp(self):
        self.store = _akhlaghi()
        self.template, _ = _build_clothing_template()

    def test_running_twice_creates_no_duplicate_categories(self):
        install_industry_template(self.store, self.template)
        try:
            install_industry_template(self.store, self.template)
        except IndustryInstallationError:
            pass
        self.assertEqual(Category.objects.filter(store=self.store, name="پوشاک").count(), 1)
