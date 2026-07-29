from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from apps.catalog.models import (
    Category,
    IndustryTemplate,
    IndustryTemplateAttribute,
    IndustryTemplateAttributeValue,
    IndustryTemplateCategory,
    IndustryTemplateCategoryAttributeMapping,
    IndustryTemplateRecommendedOption,
)
from apps.catalog.industry_templates.registry import ALL_INDUSTRY_TEMPLATES as INDUSTRY_TEMPLATES
from apps.catalog.services.industry_template_service import install_industry_template
from apps.stores.models import Store


def _run_seed():
    call_command("seed_industry_templates", stdout=StringIO())


class SeedIndustryTemplatesCommandTests(TestCase):
    def test_creates_expected_number_of_templates(self):
        _run_seed()
        self.assertEqual(IndustryTemplate.objects.count(), len(INDUSTRY_TEMPLATES))
        self.assertGreaterEqual(len(INDUSTRY_TEMPLATES), 30)

    def test_every_template_is_production_ready_after_seed(self):
        _run_seed()
        for template in IndustryTemplate.objects.all():
            with self.subTest(template=template.slug):
                self.assertEqual(template.readiness, IndustryTemplate.Readiness.PRODUCTION_READY)
                self.assertTrue(template.content_fingerprint)

    def test_every_template_slug_is_seeded_and_active(self):
        _run_seed()
        seeded_slugs = set(IndustryTemplate.objects.values_list("slug", flat=True))
        expected_slugs = {entry["slug"] for entry in INDUSTRY_TEMPLATES}
        self.assertEqual(seeded_slugs, expected_slugs)
        self.assertFalse(IndustryTemplate.objects.filter(is_active=False).exists())

    def test_every_template_has_real_categories_and_attributes(self):
        _run_seed()
        for template in IndustryTemplate.objects.all():
            with self.subTest(template=template.slug):
                self.assertGreaterEqual(template.categories.count(), 3)
                self.assertGreaterEqual(template.attributes.count(), 4)

    def test_running_twice_does_not_duplicate_records(self):
        _run_seed()
        counts_after_first = {
            "templates": IndustryTemplate.objects.count(),
            "categories": IndustryTemplateCategory.objects.count(),
            "attributes": IndustryTemplateAttribute.objects.count(),
            "values": IndustryTemplateAttributeValue.objects.count(),
            "mappings": IndustryTemplateCategoryAttributeMapping.objects.count(),
            "recommended": IndustryTemplateRecommendedOption.objects.count(),
        }

        _run_seed()

        counts_after_second = {
            "templates": IndustryTemplate.objects.count(),
            "categories": IndustryTemplateCategory.objects.count(),
            "attributes": IndustryTemplateAttribute.objects.count(),
            "values": IndustryTemplateAttributeValue.objects.count(),
            "mappings": IndustryTemplateCategoryAttributeMapping.objects.count(),
            "recommended": IndustryTemplateRecommendedOption.objects.count(),
        }
        self.assertEqual(counts_after_first, counts_after_second)

    def test_category_hierarchy_is_stable_across_reruns(self):
        _run_seed()
        _run_seed()
        clothing_template = IndustryTemplate.objects.get(slug="clothing-fashion")
        tshirts = IndustryTemplateCategory.objects.get(
            industry_template=clothing_template, code="clothing-mens-tshirts",
        )
        self.assertEqual(tshirts.parent.code, "clothing-mens")
        self.assertEqual(tshirts.parent.parent.code, "clothing")

    def test_recommended_options_only_reference_variant_axis_attributes(self):
        _run_seed()
        for option in IndustryTemplateRecommendedOption.objects.select_related("template_attribute"):
            with self.subTest(option=str(option)):
                self.assertTrue(option.template_attribute.is_variant_axis)

    def test_mappings_reference_attribute_and_category_from_same_template(self):
        _run_seed()
        for mapping in IndustryTemplateCategoryAttributeMapping.objects.select_related(
            "template_category", "template_attribute",
        ):
            with self.subTest(mapping=str(mapping)):
                self.assertEqual(
                    mapping.template_category.industry_template_id,
                    mapping.template_attribute.industry_template_id,
                )


class InstallEverySeededIndustryTests(TestCase):
    """§36.11 — هر صنف ساخته‌شده باید بدون خطا روی یک Store واقعی نصب شود."""

    def setUp(self):
        _run_seed()
        self.store = Store.objects.get(slug="akhlaghi")

    def test_every_seeded_industry_installs_cleanly(self):
        for template in IndustryTemplate.objects.all():
            with self.subTest(template=template.slug):
                store = Store.objects.create(
                    name=f"فروشگاه آزمایشی {template.slug}",
                    slug=f"test-store-{template.slug}",
                    status=Store.Status.ACTIVE,
                )
                result = install_industry_template(store, template)
                self.assertEqual(len(result.categories_created), template.categories.count())
                self.assertGreater(Category.objects.filter(store=store).count(), 0)
