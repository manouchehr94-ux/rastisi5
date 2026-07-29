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
    IndustryTemplateRecommendedOption,
    StoreIndustryInstallation,
    StoreTemplateUpdate,
)
from apps.catalog.services.industry_template_service import install_industry_template
from apps.catalog.services.template_update_service import (
    TemplateUpdateError,
    apply_template_update,
    plan_template_update,
)
from apps.stores.models import Store


def _akhlaghi():
    return Store.objects.get(slug="akhlaghi")


def _v1(slug="upd-shoes"):
    v1 = IndustryTemplate.objects.create(
        slug=slug, name="کفش", version=1, readiness=IndustryTemplate.Readiness.PRODUCTION_READY,
    )
    mens = IndustryTemplateCategory.objects.create(industry_template=v1, code="mens", name="مردانه")
    color = IndustryTemplateAttribute.objects.create(
        industry_template=v1, code="color", label="رنگ", data_type=Attribute.DataType.COLOR,
        display_type=Attribute.DisplayType.SWATCH, is_variant_axis=True,
    )
    IndustryTemplateAttributeValue.objects.create(template_attribute=color, label="مشکی", color_hex="#111827")
    IndustryTemplateCategoryAttributeMapping.objects.create(
        template_category=mens, template_attribute=color, group="مشخصات",
    )
    return v1


def _v2_with_additions(v1):
    """v2 = v1 plus a new category, a new attribute+value, and a new mapping/recommendation."""
    v2 = IndustryTemplate.objects.create(
        slug=v1.slug, name="کفش", version=2, readiness=IndustryTemplate.Readiness.PRODUCTION_READY,
    )
    mens2 = IndustryTemplateCategory.objects.create(industry_template=v2, code="mens", name="مردانه")
    outlet = IndustryTemplateCategory.objects.create(industry_template=v2, code="outlet", name="ته‌مانده")
    color2 = IndustryTemplateAttribute.objects.create(
        industry_template=v2, code="color", label="رنگ", data_type=Attribute.DataType.COLOR,
        display_type=Attribute.DisplayType.SWATCH, is_variant_axis=True,
    )
    IndustryTemplateAttributeValue.objects.create(template_attribute=color2, label="مشکی", color_hex="#111827")
    IndustryTemplateAttributeValue.objects.create(template_attribute=color2, label="قرمز", color_hex="#ef4444")
    size2 = IndustryTemplateAttribute.objects.create(
        industry_template=v2, code="size", label="سایز", data_type=Attribute.DataType.SELECT,
        is_variant_axis=True,
    )
    IndustryTemplateAttributeValue.objects.create(template_attribute=size2, label="۴۰")
    IndustryTemplateCategoryAttributeMapping.objects.create(
        template_category=mens2, template_attribute=color2, group="مشخصات",
    )
    IndustryTemplateCategoryAttributeMapping.objects.create(
        template_category=mens2, template_attribute=size2, group="مشخصات",
    )
    IndustryTemplateRecommendedOption.objects.create(template_category=mens2, template_attribute=size2)
    return v2


class PlanTemplateUpdateTests(TestCase):
    def setUp(self):
        self.store = _akhlaghi()
        self.v1 = _v1(slug="plan-shoes")
        install_industry_template(self.store, self.v1)
        self.installation = StoreIndustryInstallation.objects.get(store=self.store)

    def test_safe_additive_changes_identified(self):
        v2 = _v2_with_additions(self.v1)
        plan = plan_template_update(self.installation, v2)
        self.assertTrue(plan.eligible)
        kinds = {(c.diff_entry.kind, c.diff_entry.code) for c in plan.safe_additive}
        self.assertIn(("category", "outlet"), kinds)
        self.assertIn(("attribute", "size"), kinds)
        self.assertIn(("value", "size:۴۰"), kinds)
        self.assertIn(("value", "color:قرمز"), kinds)

    def test_default_selection_is_all_safe_additive(self):
        v2 = _v2_with_additions(self.v1)
        plan = plan_template_update(self.installation, v2)
        self.assertEqual(set(plan.default_selected_change_ids), {c.change_id for c in plan.safe_additive})

    def test_customized_record_changes_are_blocked(self):
        category = Category.objects.get(store=self.store, name="مردانه")
        category.name = "مردانه سفارشی"
        category.save()
        v2 = IndustryTemplate.objects.create(
            slug=self.v1.slug, name="کفش", version=2, readiness=IndustryTemplate.Readiness.PRODUCTION_READY,
        )
        IndustryTemplateCategory.objects.create(industry_template=v2, code="mens", name="مردانه (به‌روزشده)")
        plan = plan_template_update(self.installation, v2)
        blocked_codes = {c.diff_entry.code for c in plan.blocked}
        self.assertIn("mens", blocked_codes)

    def test_uncustomized_record_change_is_review_required(self):
        v2 = IndustryTemplate.objects.create(
            slug=self.v1.slug, name="کفش", version=2, readiness=IndustryTemplate.Readiness.PRODUCTION_READY,
        )
        IndustryTemplateCategory.objects.create(industry_template=v2, code="mens", name="مردانه (به‌روزشده)")
        plan = plan_template_update(self.installation, v2)
        review_codes = {c.diff_entry.code for c in plan.review_required}
        self.assertIn("mens", review_codes)

    def test_removed_entries_are_always_blocked(self):
        v2 = IndustryTemplate.objects.create(
            slug=self.v1.slug, name="کفش", version=2, readiness=IndustryTemplate.Readiness.PRODUCTION_READY,
        )
        # v2 has no categories at all -> mens is "removed"
        plan = plan_template_update(self.installation, v2)
        blocked_codes = {c.diff_entry.code for c in plan.blocked}
        self.assertIn("mens", blocked_codes)

    def test_conflicting_attribute_data_type_is_blocked(self):
        from apps.catalog.services.attribute_service import create_attribute

        create_attribute(self.store, label="اندازه دستی", code="size", data_type=Attribute.DataType.TEXT)
        v2 = _v2_with_additions(self.v1)
        plan = plan_template_update(self.installation, v2)
        blocked_codes = {c.diff_entry.code for c in plan.blocked}
        self.assertIn("size", blocked_codes)

    def test_same_version_is_rejected(self):
        plan = plan_template_update(self.installation, self.v1)
        self.assertFalse(plan.eligible)

    def test_older_version_is_rejected(self):
        v2 = _v2_with_additions(self.v1)
        self.installation.industry_template = v2
        self.installation.installed_version = 2
        self.installation.save()
        plan = plan_template_update(self.installation, self.v1)
        self.assertFalse(plan.eligible)

    def test_deprecated_target_is_rejected(self):
        v2 = _v2_with_additions(self.v1)
        v2.readiness = IndustryTemplate.Readiness.DEPRECATED
        v2.save(update_fields=["readiness"])
        plan = plan_template_update(self.installation, v2)
        self.assertFalse(plan.eligible)

    def test_plan_does_not_mutate_store_data(self):
        v2 = _v2_with_additions(self.v1)
        plan_template_update(self.installation, v2)
        self.assertFalse(Category.objects.filter(store=self.store, name="ته‌مانده").exists())


class ApplyTemplateUpdateTests(TestCase):
    def setUp(self):
        self.store = _akhlaghi()
        self.v1 = _v1(slug="apply-shoes")
        install_industry_template(self.store, self.v1)
        self.installation = StoreIndustryInstallation.objects.get(store=self.store)
        self.v2 = _v2_with_additions(self.v1)

    def test_apply_all_safe_changes(self):
        plan = plan_template_update(self.installation, self.v2)
        result = apply_template_update(self.installation, self.v2, plan.default_selected_change_ids, actor=None)
        self.assertEqual(result.status, StoreTemplateUpdate.Status.COMPLETED)
        self.assertTrue(Category.objects.filter(store=self.store, name="ته‌مانده").exists())
        self.assertTrue(
            Attribute.objects.get(store=self.store, code="color").values.filter(label="قرمز").exists()
        )
        self.installation.refresh_from_db()
        self.assertEqual(self.installation.installed_version, 2)

    def test_apply_only_selected_subset(self):
        plan = plan_template_update(self.installation, self.v2)
        category_only = [c.change_id for c in plan.safe_additive if c.diff_entry.kind == "category"]
        result = apply_template_update(self.installation, self.v2, category_only, actor=None)
        self.assertTrue(Category.objects.filter(store=self.store, name="ته‌مانده").exists())
        self.assertFalse(Attribute.objects.filter(store=self.store, code="size").exists())
        self.assertIn(
            [c.change_id for c in plan.safe_additive if c.diff_entry.kind == "attribute"][0],
            result.skipped_changes,
        )

    def test_preserves_customized_category_untouched(self):
        category = Category.objects.get(store=self.store, name="مردانه")
        category.name = "مردانه سفارشی من"
        category.save()
        v3 = IndustryTemplate.objects.create(
            slug=self.v1.slug, name="کفش", version=3, readiness=IndustryTemplate.Readiness.PRODUCTION_READY,
        )
        IndustryTemplateCategory.objects.create(industry_template=v3, code="mens", name="مردانه (نسخه‌ی جدید)")
        plan = plan_template_update(self.installation, v3)
        apply_template_update(self.installation, v3, plan.default_selected_change_ids, actor=None)
        category.refresh_from_db()
        self.assertEqual(category.name, "مردانه سفارشی من")

    def test_preserves_merchant_created_records(self):
        manual_category = Category.objects.create(store=self.store, name="دسته‌ی دستی من", slug="apply-manual")
        plan = plan_template_update(self.installation, self.v2)
        apply_template_update(self.installation, self.v2, plan.default_selected_change_ids, actor=None)
        self.assertTrue(Category.objects.filter(pk=manual_category.pk, name="دسته‌ی دستی من").exists())

    def test_records_update_history(self):
        plan = plan_template_update(self.installation, self.v2)
        apply_template_update(self.installation, self.v2, plan.default_selected_change_ids, actor=None)
        update = StoreTemplateUpdate.objects.get(store=self.store)
        self.assertEqual(update.from_template_id, self.v1.pk)
        self.assertEqual(update.target_template_id, self.v2.pk)
        self.assertTrue(update.applied_changes)
        self.assertIsNotNone(update.completed_at)

    def test_duplicate_apply_rejected(self):
        plan = plan_template_update(self.installation, self.v2)
        apply_template_update(self.installation, self.v2, plan.default_selected_change_ids, actor=None)
        with self.assertRaises(TemplateUpdateError):
            apply_template_update(self.installation, self.v2, plan.default_selected_change_ids, actor=None)

    def test_rejects_selecting_review_required_change(self):
        category = Category.objects.get(store=self.store, name="مردانه")
        v3 = IndustryTemplate.objects.create(
            slug=self.v1.slug, name="کفش", version=3, readiness=IndustryTemplate.Readiness.PRODUCTION_READY,
        )
        IndustryTemplateCategory.objects.create(industry_template=v3, code="mens", name="مردانه (جدید)")
        plan = plan_template_update(self.installation, v3)
        review_ids = [c.change_id for c in plan.review_required]
        with self.assertRaises(TemplateUpdateError):
            apply_template_update(self.installation, v3, review_ids, actor=None)
        category.refresh_from_db()
        self.assertEqual(category.name, "مردانه")

    def test_rejects_selecting_blocked_change(self):
        v3 = IndustryTemplate.objects.create(
            slug=self.v1.slug, name="کفش", version=3, readiness=IndustryTemplate.Readiness.PRODUCTION_READY,
        )
        # v3 has no categories -> mens is removed -> blocked
        plan = plan_template_update(self.installation, v3)
        blocked_ids = [c.change_id for c in plan.blocked]
        with self.assertRaises(TemplateUpdateError):
            apply_template_update(self.installation, v3, blocked_ids, actor=None)

    def test_ineligible_plan_raises_before_applying(self):
        with self.assertRaises(TemplateUpdateError):
            apply_template_update(self.installation, self.v1, [], actor=None)

    def test_atomic_rollback_on_failure(self):
        """A failure partway through applying (after the category/attribute/value steps have
        already run inside the same atomic block) must roll back everything, not just skip the
        step that failed — and the update history row must end up FAILED, not silently lost."""
        from unittest.mock import patch

        plan = plan_template_update(self.installation, self.v2)
        categories_before = Category.objects.filter(store=self.store).count()
        attributes_before = Attribute.objects.filter(store=self.store).count()

        with patch(
            "apps.catalog.services.template_update_service.CategoryRecommendedOption.objects.get_or_create",
            side_effect=RuntimeError("simulated failure during recommendation step"),
        ):
            with self.assertRaises(RuntimeError):
                apply_template_update(self.installation, self.v2, plan.default_selected_change_ids, actor=None)

        self.assertEqual(Category.objects.filter(store=self.store).count(), categories_before)
        self.assertEqual(Attribute.objects.filter(store=self.store).count(), attributes_before)
        self.installation.refresh_from_db()
        self.assertEqual(self.installation.installed_version, 1)
        update = StoreTemplateUpdate.objects.get(store=self.store, target_template=self.v2)
        self.assertEqual(update.status, StoreTemplateUpdate.Status.FAILED)
        self.assertIn("simulated failure", update.failure_reason)

    def test_cross_installation_target_family_mismatch_rejected(self):
        other_family = IndustryTemplate.objects.create(
            slug="apply-other-family", name="دیگر", version=1, readiness=IndustryTemplate.Readiness.PRODUCTION_READY,
        )
        with self.assertRaises(TemplateUpdateError):
            apply_template_update(self.installation, other_family, [], actor=None)
