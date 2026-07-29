from django.test import TestCase

from apps.catalog.models import (
    Attribute,
    IndustryTemplate,
    IndustryTemplateAttribute,
    IndustryTemplateAttributeValue,
    IndustryTemplateCategory,
    IndustryTemplateCategoryAttributeMapping,
    IndustryTemplateRecommendedOption,
)
from apps.catalog.services.industry_template_service import install_industry_template
from apps.catalog.services.template_preview_service import build_template_preview, plan_industry_template_installation
from apps.catalog.services.attribute_service import create_attribute
from apps.stores.models import Store


def _akhlaghi():
    return Store.objects.get(slug="akhlaghi")


def _preview_template(slug="pv-clothing"):
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
    color = IndustryTemplateAttribute.objects.create(
        industry_template=template, code="color", label="رنگ", data_type=Attribute.DataType.COLOR,
        display_type=Attribute.DisplayType.SWATCH, is_variant_axis=True,
    )
    IndustryTemplateAttributeValue.objects.create(template_attribute=color, label="قرمز", color_hex="#ef4444")
    IndustryTemplateAttributeValue.objects.create(template_attribute=color, label="آبی", color_hex="#3b82f6")
    IndustryTemplateCategoryAttributeMapping.objects.create(
        template_category=child, template_attribute=material, group="عمومی", is_required=True, is_filterable=True,
    )
    IndustryTemplateRecommendedOption.objects.create(template_category=child, template_attribute=color)
    return template


class BuildTemplatePreviewTests(TestCase):
    def test_counts_are_correct(self):
        template = _preview_template()
        preview = build_template_preview(template)
        self.assertEqual(preview["counts"]["categories"], 2)
        self.assertEqual(preview["counts"]["attributes"], 2)
        self.assertEqual(preview["counts"]["values"], 3)
        self.assertEqual(preview["counts"]["mappings"], 1)
        self.assertEqual(preview["counts"]["recommendations"], 1)

    def test_hierarchy_is_nested_correctly(self):
        template = _preview_template()
        preview = build_template_preview(template)
        self.assertEqual(len(preview["hierarchy"]), 1)
        root_node = preview["hierarchy"][0]
        self.assertEqual(root_node["code"], "root")
        self.assertEqual(len(root_node["children"]), 1)
        self.assertEqual(root_node["children"][0]["code"], "mens")

    def test_required_filterable_sets_populated(self):
        template = _preview_template()
        preview = build_template_preview(template)
        self.assertIn("material", preview["required_attribute_codes"])
        self.assertIn("material", preview["filterable_attribute_codes"])

    def test_readiness_and_validation_included(self):
        template = _preview_template()
        preview = build_template_preview(template)
        self.assertEqual(preview["readiness"], IndustryTemplate.Readiness.PRODUCTION_READY)
        self.assertTrue(preview["validation"].is_valid)


class PlanInstallationTests(TestCase):
    def setUp(self):
        self.store = _akhlaghi()

    def test_eligible_plan_for_fresh_store(self):
        template = _preview_template(slug="pv-fresh")
        plan = plan_industry_template_installation(self.store, template)
        self.assertTrue(plan.eligible)
        self.assertEqual(plan.will_create_categories, 2)
        self.assertEqual(plan.will_create_attributes, 2)
        self.assertEqual(plan.will_create_values, 3)
        self.assertEqual(plan.will_create_mappings, 1)
        self.assertEqual(plan.will_create_recommendations, 1)
        self.assertEqual(plan.will_reuse_attributes, [])

    def test_reuses_existing_attribute_by_code(self):
        template = _preview_template(slug="pv-reuse")
        create_attribute(self.store, label="جنس موجود", code="material")
        plan = plan_industry_template_installation(self.store, template)
        self.assertEqual(plan.will_reuse_attributes, ["material"])
        self.assertEqual(plan.will_create_attributes, 1)

    def test_blocked_when_already_installed(self):
        template = _preview_template(slug="pv-blocked")
        install_industry_template(self.store, template)
        other_template = _preview_template(slug="pv-blocked-2")
        plan = plan_industry_template_installation(self.store, other_template)
        self.assertFalse(plan.eligible)
        self.assertTrue(plan.blocking_errors)

    def test_blocked_when_not_production_ready(self):
        template = _preview_template(slug="pv-draft")
        template.readiness = IndustryTemplate.Readiness.DRAFT
        template.save(update_fields=["readiness"])
        plan = plan_industry_template_installation(self.store, template)
        self.assertFalse(plan.eligible)

    def test_plan_reflects_real_store_state_not_hardcoded(self):
        template = _preview_template(slug="pv-real")
        other_store = Store.objects.create(name="فروشگاه دیگر", slug="pv-other-store", status=Store.Status.ACTIVE)
        create_attribute(other_store, label="جنس فروشگاه دیگر", code="material")
        # material exists in a *different* Store — must not be counted as reusable here
        plan = plan_industry_template_installation(self.store, template)
        self.assertEqual(plan.will_reuse_attributes, [])
        self.assertEqual(plan.will_create_attributes, 2)
