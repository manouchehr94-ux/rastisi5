from django.test import TestCase

from apps.catalog.models import (
    Attribute,
    IndustryTemplate,
    IndustryTemplateAttribute,
    IndustryTemplateAttributeValue,
    IndustryTemplateCategory,
    IndustryTemplateCategoryAttributeMapping,
    IndustryTemplateRecommendedOption,
    IndustryTemplateValidationResult,
)
from apps.catalog.services.template_validation_service import (
    compute_template_fingerprint,
    latest_production_version,
    validate_and_persist,
    validate_industry_template,
)


def _valid_template(slug="tv-valid", version=1):
    template = IndustryTemplate.objects.create(slug=slug, name="قالب معتبر", description="توضیح", version=version)
    root = IndustryTemplateCategory.objects.create(industry_template=template, code="root", name="ریشه")
    child = IndustryTemplateCategory.objects.create(
        industry_template=template, code="child", name="فرزند", parent=root,
    )
    color = IndustryTemplateAttribute.objects.create(
        industry_template=template, code="color", label="رنگ", data_type=Attribute.DataType.COLOR,
        display_type=Attribute.DisplayType.SWATCH, is_variant_axis=True,
    )
    IndustryTemplateAttributeValue.objects.create(template_attribute=color, label="قرمز", color_hex="#ef4444")
    IndustryTemplateAttributeValue.objects.create(template_attribute=color, label="آبی", color_hex="#3b82f6")
    material = IndustryTemplateAttribute.objects.create(
        industry_template=template, code="material", label="جنس", data_type=Attribute.DataType.TEXT,
    )
    IndustryTemplateCategoryAttributeMapping.objects.create(
        template_category=child, template_attribute=material, group="عمومی", is_required=True, is_filterable=True,
    )
    IndustryTemplateRecommendedOption.objects.create(template_category=child, template_attribute=color)
    return template


class ValidateIndustryTemplateTests(TestCase):
    def test_valid_template_has_no_errors(self):
        template = _valid_template()
        result = validate_industry_template(template)
        self.assertTrue(result.is_valid)
        self.assertEqual(result.errors, [])

    def test_missing_root_category_is_error(self):
        template = IndustryTemplate.objects.create(slug="tv-no-root", name="بدون ریشه", version=1)
        root = IndustryTemplateCategory.objects.create(industry_template=template, code="root", name="ریشه")
        IndustryTemplateCategory.objects.create(
            industry_template=template, code="child", name="فرزند", parent=root,
        )
        other_template = IndustryTemplate.objects.create(slug="tv-no-root-other", name="دیگر", version=1)
        foreign_category = IndustryTemplateCategory.objects.create(
            industry_template=other_template, code="foreign", name="خارجی",
        )
        # sabotage: root's parent points at a category from a *different* template (valid FK,
        # but semantically an orphan since this template's own tree never resolves to it).
        IndustryTemplateCategory.objects.filter(pk=root.pk).update(parent_id=foreign_category.pk)
        result = validate_industry_template(template)
        self.assertFalse(result.is_valid)
        self.assertIn("CATEGORY_ORPHAN", [e.code for e in result.errors])

    def test_no_categories_at_all_is_error(self):
        template = IndustryTemplate.objects.create(slug="tv-empty", name="خالی", version=1)
        result = validate_industry_template(template)
        self.assertFalse(result.is_valid)
        self.assertIn("CATEGORY_NONE", [e.code for e in result.errors])

    def test_circular_hierarchy_detected(self):
        template = IndustryTemplate.objects.create(slug="tv-cycle", name="حلقه‌ای", version=1)
        a = IndustryTemplateCategory.objects.create(industry_template=template, code="a", name="آ")
        b = IndustryTemplateCategory.objects.create(industry_template=template, code="b", name="ب", parent=a)
        # Force a cycle: a's parent becomes b (bypassing clean())
        IndustryTemplateCategory.objects.filter(pk=a.pk).update(parent_id=b.pk)
        result = validate_industry_template(template)
        self.assertFalse(result.is_valid)
        self.assertIn("CATEGORY_CIRCULAR_HIERARCHY", [e.code for e in result.errors])

    def test_choice_attribute_with_no_values_is_error(self):
        template = IndustryTemplate.objects.create(slug="tv-nochoice", name="بدون مقدار", version=1)
        IndustryTemplateCategory.objects.create(industry_template=template, code="root", name="ریشه")
        IndustryTemplateAttribute.objects.create(
            industry_template=template, code="size", label="سایز", data_type=Attribute.DataType.SELECT,
        )
        result = validate_industry_template(template)
        self.assertFalse(result.is_valid)
        self.assertIn("ATTRIBUTE_CHOICE_NO_VALUES", [e.code for e in result.errors])

    def test_required_mapping_with_unobtainable_value_is_error(self):
        template = IndustryTemplate.objects.create(slug="tv-unobtainable", name="نامعتبر", version=1)
        cat = IndustryTemplateCategory.objects.create(industry_template=template, code="root", name="ریشه")
        attr = IndustryTemplateAttribute.objects.create(
            industry_template=template, code="size", label="سایز", data_type=Attribute.DataType.SELECT,
        )
        IndustryTemplateCategoryAttributeMapping.objects.create(
            template_category=cat, template_attribute=attr, is_required=True,
        )
        result = validate_industry_template(template)
        self.assertFalse(result.is_valid)
        self.assertIn("SCHEMA_REQUIRED_UNOBTAINABLE", [e.code for e in result.errors])

    def test_recommendation_with_few_values_is_warning(self):
        template = IndustryTemplate.objects.create(slug="tv-fewvalues", name="کم‌مقدار", version=1)
        cat = IndustryTemplateCategory.objects.create(industry_template=template, code="root", name="ریشه")
        attr = IndustryTemplateAttribute.objects.create(
            industry_template=template, code="size", label="سایز", data_type=Attribute.DataType.SELECT,
            is_variant_axis=True,
        )
        IndustryTemplateAttributeValue.objects.create(template_attribute=attr, label="یکی")
        IndustryTemplateRecommendedOption.objects.create(template_category=cat, template_attribute=attr)
        result = validate_industry_template(template)
        self.assertTrue(result.is_valid)
        self.assertIn("RECOMMENDATION_TOO_FEW_VALUES", [w.code for w in result.warnings])

    def test_deterministic_result_across_calls(self):
        template = _valid_template()
        r1 = validate_industry_template(template)
        r2 = validate_industry_template(template)
        self.assertEqual(r1.metrics, r2.metrics)
        self.assertEqual(r1.quality_score, r2.quality_score)
        self.assertEqual([e.code for e in r1.errors], [e.code for e in r2.errors])

    def test_error_caps_quality_score(self):
        template = IndustryTemplate.objects.create(slug="tv-capped", name="محدود", version=1)
        result = validate_industry_template(template)
        self.assertFalse(result.is_valid)
        self.assertLessEqual(result.quality_score, 40)

    def test_metrics_counts_are_correct(self):
        template = _valid_template()
        result = validate_industry_template(template)
        self.assertEqual(result.metrics["category_count"], 2)
        self.assertEqual(result.metrics["attribute_count"], 2)
        self.assertEqual(result.metrics["value_count"], 2)
        self.assertEqual(result.metrics["mapping_count"], 1)
        self.assertEqual(result.metrics["recommendation_count"], 1)


class FingerprintTests(TestCase):
    def test_deterministic_across_calls(self):
        template = _valid_template(slug="fp-1")
        self.assertEqual(compute_template_fingerprint(template), compute_template_fingerprint(template))

    def test_independent_of_primary_keys(self):
        t1 = _valid_template(slug="fp-a")
        t2 = _valid_template(slug="fp-a", version=2)
        # same slug, byte-identical content, different version/PK → the fingerprint (which
        # excludes version and every primary key) must still match exactly.
        self.assertNotEqual(t1.pk, t2.pk)
        self.assertEqual(compute_template_fingerprint(t1), compute_template_fingerprint(t2))

    def test_changes_when_content_changes(self):
        template = _valid_template(slug="fp-changes")
        original = compute_template_fingerprint(template)
        IndustryTemplateCategory.objects.create(industry_template=template, code="extra", name="اضافه")
        changed = compute_template_fingerprint(template)
        self.assertNotEqual(original, changed)

    def test_does_not_depend_on_timestamps(self):
        t1 = _valid_template(slug="fp-time-a")
        fingerprint_before = compute_template_fingerprint(t1)
        # re-saving without changing any content field bumps updated_at (auto_now) but must not
        # change the fingerprint, since the payload never includes created_at/updated_at.
        category = t1.categories.first()
        category.save()
        fingerprint_after = compute_template_fingerprint(t1)
        self.assertEqual(fingerprint_before, fingerprint_after)


class ValidateAndPersistTests(TestCase):
    def test_valid_template_becomes_production_ready(self):
        template = _valid_template(slug="vp-ready")
        validate_and_persist(template)
        template.refresh_from_db()
        self.assertEqual(template.readiness, IndustryTemplate.Readiness.PRODUCTION_READY)
        self.assertTrue(template.content_fingerprint)

    def test_invalid_template_becomes_validation_failed(self):
        template = IndustryTemplate.objects.create(slug="vp-fail", name="ناموفق", version=1)
        validate_and_persist(template)
        template.refresh_from_db()
        self.assertEqual(template.readiness, IndustryTemplate.Readiness.VALIDATION_FAILED)

    def test_persists_validation_result_record(self):
        template = _valid_template(slug="vp-persist")
        validate_and_persist(template)
        record = IndustryTemplateValidationResult.objects.get(industry_template=template)
        self.assertEqual(record.status, IndustryTemplateValidationResult.Status.VALID)
        self.assertFalse(record.is_stale)

    def test_stale_detection_when_fingerprint_changes(self):
        template = _valid_template(slug="vp-stale")
        validate_and_persist(template)
        record = IndustryTemplateValidationResult.objects.get(industry_template=template)
        # simulate drift: template's cached fingerprint no longer matches the persisted record's
        IndustryTemplate.objects.filter(pk=template.pk).update(content_fingerprint="deadbeef")
        template.refresh_from_db()
        record.refresh_from_db()
        self.assertTrue(record.is_stale)

    def test_deprecated_template_never_auto_promoted(self):
        template = _valid_template(slug="vp-deprecated")
        template.readiness = IndustryTemplate.Readiness.DEPRECATED
        template.save(update_fields=["readiness"])
        validate_and_persist(template)
        template.refresh_from_db()
        self.assertEqual(template.readiness, IndustryTemplate.Readiness.DEPRECATED)

    def test_strict_mode_downgrades_warnings_to_review_required(self):
        template = _valid_template(slug="vp-strict")
        # clothing-fashion-style template with a warning (leaf category with no mapping)
        IndustryTemplateCategory.objects.create(industry_template=template, code="leaf2", name="برگ بدون نگاشت")
        validate_and_persist(template, strict=True)
        template.refresh_from_db()
        self.assertEqual(template.readiness, IndustryTemplate.Readiness.REVIEW_REQUIRED)


class LatestProductionVersionTests(TestCase):
    def test_returns_highest_production_ready_version(self):
        IndustryTemplate.objects.create(
            slug="lpv-fam", name="v1", version=1, readiness=IndustryTemplate.Readiness.PRODUCTION_READY,
        )
        v2 = IndustryTemplate.objects.create(
            slug="lpv-fam", name="v2", version=2, readiness=IndustryTemplate.Readiness.PRODUCTION_READY,
        )
        IndustryTemplate.objects.create(
            slug="lpv-fam", name="v3-draft", version=3, readiness=IndustryTemplate.Readiness.DRAFT,
        )
        result = latest_production_version("lpv-fam")
        self.assertEqual(result.pk, v2.pk)

    def test_returns_none_when_no_production_ready_version(self):
        IndustryTemplate.objects.create(
            slug="lpv-none", name="draft", version=1, readiness=IndustryTemplate.Readiness.DRAFT,
        )
        self.assertIsNone(latest_production_version("lpv-none"))
