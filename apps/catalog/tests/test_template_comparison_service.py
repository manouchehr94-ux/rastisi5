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
from apps.catalog.services.template_comparison_service import TemplateComparisonError, compare_template_versions


def _base_v1(slug="cmp-shoes"):
    v1 = IndustryTemplate.objects.create(slug=slug, name="کفش", version=1)
    mens = IndustryTemplateCategory.objects.create(industry_template=v1, code="mens", name="مردانه")
    usage = IndustryTemplateAttribute.objects.create(
        industry_template=v1, code="usage", label="کاربری", data_type=Attribute.DataType.SELECT,
        display_type=Attribute.DisplayType.DROPDOWN,
    )
    IndustryTemplateAttributeValue.objects.create(template_attribute=usage, label="روزمره")
    color = IndustryTemplateAttribute.objects.create(
        industry_template=v1, code="color", label="رنگ", data_type=Attribute.DataType.COLOR,
        display_type=Attribute.DisplayType.SWATCH, is_variant_axis=True,
    )
    IndustryTemplateAttributeValue.objects.create(template_attribute=color, label="مشکی", color_hex="#111827")
    IndustryTemplateCategoryAttributeMapping.objects.create(
        template_category=mens, template_attribute=usage, group="مشخصات", is_required=False,
    )
    IndustryTemplateRecommendedOption.objects.create(template_category=mens, template_attribute=color)
    return v1, {"mens": mens, "usage": usage, "color": color}


class CompareTemplateVersionsTests(TestCase):
    def test_added_category_detected(self):
        v1, _nodes = _base_v1()
        v2 = IndustryTemplate.objects.create(slug=v1.slug, name="کفش", version=2)
        IndustryTemplateCategory.objects.create(industry_template=v2, code="mens", name="مردانه")
        IndustryTemplateCategory.objects.create(industry_template=v2, code="womens", name="زنانه")
        diff = compare_template_versions(v1, v2)
        added_codes = {e.code for e in diff.added if e.kind == "category"}
        self.assertIn("womens", added_codes)

    def test_removed_category_detected(self):
        v1, nodes = _base_v1(slug="cmp-removed")
        v2 = IndustryTemplate.objects.create(slug=v1.slug, name="کفش", version=2)
        # v2 has none of v1's categories
        diff = compare_template_versions(v1, v2)
        removed_codes = {e.code for e in diff.removed if e.kind == "category"}
        self.assertIn("mens", removed_codes)

    def test_renamed_category_label_is_changed(self):
        v1, _nodes = _base_v1(slug="cmp-rename")
        v2 = IndustryTemplate.objects.create(slug=v1.slug, name="کفش", version=2)
        IndustryTemplateCategory.objects.create(industry_template=v2, code="mens", name="مردانه (جدید)")
        diff = compare_template_versions(v1, v2)
        changed = [e for e in diff.changed if e.kind == "category" and e.code == "mens"]
        self.assertEqual(len(changed), 1)
        self.assertEqual(changed[0].details["name"]["old"], "مردانه")
        self.assertEqual(changed[0].details["name"]["new"], "مردانه (جدید)")

    def test_parent_change_detected(self):
        v1 = IndustryTemplate.objects.create(slug="cmp-parent", name="پ", version=1)
        top = IndustryTemplateCategory.objects.create(industry_template=v1, code="top", name="بالا")
        IndustryTemplateCategory.objects.create(industry_template=v1, code="child", name="فرزند", parent=top)
        v2 = IndustryTemplate.objects.create(slug="cmp-parent", name="پ", version=2)
        IndustryTemplateCategory.objects.create(industry_template=v2, code="top", name="بالا")
        other_top = IndustryTemplateCategory.objects.create(industry_template=v2, code="top2", name="بالا۲")
        IndustryTemplateCategory.objects.create(
            industry_template=v2, code="child", name="فرزند", parent=other_top,
        )
        diff = compare_template_versions(v1, v2)
        changed = [e for e in diff.changed if e.kind == "category" and e.code == "child"]
        self.assertEqual(len(changed), 1)
        self.assertEqual(changed[0].details["parent_code"]["old"], "top")
        self.assertEqual(changed[0].details["parent_code"]["new"], "top2")

    def test_added_attribute_detected(self):
        v1, _nodes = _base_v1(slug="cmp-attr-add")
        v2 = IndustryTemplate.objects.create(slug=v1.slug, name="کفش", version=2)
        IndustryTemplateAttribute.objects.create(
            industry_template=v2, code="usage", label="کاربری", data_type=Attribute.DataType.SELECT,
        )
        IndustryTemplateAttribute.objects.create(
            industry_template=v2, code="new-attr", label="جدید", data_type=Attribute.DataType.TEXT,
        )
        diff = compare_template_versions(v1, v2)
        added_codes = {e.code for e in diff.added if e.kind == "attribute"}
        self.assertIn("new-attr", added_codes)

    def test_data_type_change_detected(self):
        v1, _nodes = _base_v1(slug="cmp-datatype")
        v2 = IndustryTemplate.objects.create(slug=v1.slug, name="کفش", version=2)
        IndustryTemplateAttribute.objects.create(
            industry_template=v2, code="usage", label="کاربری", data_type=Attribute.DataType.TEXT,
        )
        diff = compare_template_versions(v1, v2)
        changed = [e for e in diff.changed if e.kind == "attribute" and e.code == "usage"]
        self.assertEqual(len(changed), 1)
        self.assertIn("data_type", changed[0].details)

    def test_added_value_detected(self):
        v1, _nodes = _base_v1(slug="cmp-value-add")
        v2 = IndustryTemplate.objects.create(slug=v1.slug, name="کفش", version=2)
        usage2 = IndustryTemplateAttribute.objects.create(
            industry_template=v2, code="usage", label="کاربری", data_type=Attribute.DataType.SELECT,
        )
        IndustryTemplateAttributeValue.objects.create(template_attribute=usage2, label="روزمره")
        IndustryTemplateAttributeValue.objects.create(template_attribute=usage2, label="ورزشی")
        diff = compare_template_versions(v1, v2)
        added_values = {e.label for e in diff.added if e.kind == "value"}
        self.assertIn("ورزشی", added_values)

    def test_removed_value_detected(self):
        v1, _nodes = _base_v1(slug="cmp-value-remove")
        v2 = IndustryTemplate.objects.create(slug=v1.slug, name="کفش", version=2)
        IndustryTemplateAttribute.objects.create(
            industry_template=v2, code="usage", label="کاربری", data_type=Attribute.DataType.SELECT,
        )
        # v2's usage attribute has zero values -> "روزمره" is removed
        diff = compare_template_versions(v1, v2)
        removed_values = {e.label for e in diff.removed if e.kind == "value"}
        self.assertIn("روزمره", removed_values)

    def test_mapping_required_state_change_detected(self):
        v1, nodes = _base_v1(slug="cmp-mapping")
        v2 = IndustryTemplate.objects.create(slug=v1.slug, name="کفش", version=2)
        mens2 = IndustryTemplateCategory.objects.create(industry_template=v2, code="mens", name="مردانه")
        usage2 = IndustryTemplateAttribute.objects.create(
            industry_template=v2, code="usage", label="کاربری", data_type=Attribute.DataType.SELECT,
        )
        IndustryTemplateAttributeValue.objects.create(template_attribute=usage2, label="روزمره")
        IndustryTemplateCategoryAttributeMapping.objects.create(
            template_category=mens2, template_attribute=usage2, group="مشخصات", is_required=True,
        )
        diff = compare_template_versions(v1, v2)
        changed_mappings = [e for e in diff.changed if e.kind == "mapping"]
        self.assertEqual(len(changed_mappings), 1)
        self.assertTrue(changed_mappings[0].details["is_required"]["new"])

    def test_filterable_comparable_searchable_visibility_changes(self):
        v1, nodes = _base_v1(slug="cmp-flags")
        v2 = IndustryTemplate.objects.create(slug=v1.slug, name="کفش", version=2)
        mens2 = IndustryTemplateCategory.objects.create(industry_template=v2, code="mens", name="مردانه")
        usage2 = IndustryTemplateAttribute.objects.create(
            industry_template=v2, code="usage", label="کاربری", data_type=Attribute.DataType.SELECT,
        )
        IndustryTemplateAttributeValue.objects.create(template_attribute=usage2, label="روزمره")
        IndustryTemplateCategoryAttributeMapping.objects.create(
            template_category=mens2, template_attribute=usage2, group="مشخصات",
            is_filterable=True, is_comparable=True, is_searchable=True,
        )
        diff = compare_template_versions(v1, v2)
        changed_mappings = [e for e in diff.changed if e.kind == "mapping"]
        details = changed_mappings[0].details
        self.assertTrue(details["is_filterable"]["new"])
        self.assertTrue(details["is_comparable"]["new"])
        self.assertTrue(details["is_searchable"]["new"])

    def test_added_recommendation_detected(self):
        v1, nodes = _base_v1(slug="cmp-rec-add")
        v2 = IndustryTemplate.objects.create(slug=v1.slug, name="کفش", version=2)
        mens2 = IndustryTemplateCategory.objects.create(industry_template=v2, code="mens", name="مردانه")
        color2 = IndustryTemplateAttribute.objects.create(
            industry_template=v2, code="color", label="رنگ", data_type=Attribute.DataType.COLOR,
            is_variant_axis=True,
        )
        size2 = IndustryTemplateAttribute.objects.create(
            industry_template=v2, code="size", label="سایز", data_type=Attribute.DataType.SELECT,
            is_variant_axis=True,
        )
        IndustryTemplateRecommendedOption.objects.create(template_category=mens2, template_attribute=color2)
        IndustryTemplateRecommendedOption.objects.create(template_category=mens2, template_attribute=size2)
        diff = compare_template_versions(v1, v2)
        added_recs = {e.code for e in diff.added if e.kind == "recommendation"}
        self.assertIn("mens:size", added_recs)

    def test_removed_recommendation_detected(self):
        v1, nodes = _base_v1(slug="cmp-rec-remove")
        v2 = IndustryTemplate.objects.create(slug=v1.slug, name="کفش", version=2)
        IndustryTemplateCategory.objects.create(industry_template=v2, code="mens", name="مردانه")
        # v2 defines the category but no recommendation at all
        diff = compare_template_versions(v1, v2)
        removed_recs = {e.code for e in diff.removed if e.kind == "recommendation"}
        self.assertIn("mens:color", removed_recs)

    def test_stable_code_identity_not_display_label(self):
        """Renaming a category's label must not be misread as remove+add — same code == same entity."""
        v1, _nodes = _base_v1(slug="cmp-stable")
        v2 = IndustryTemplate.objects.create(slug=v1.slug, name="کفش", version=2)
        IndustryTemplateCategory.objects.create(industry_template=v2, code="mens", name="کاملاً اسم متفاوت")
        diff = compare_template_versions(v1, v2)
        removed_codes = {e.code for e in diff.removed if e.kind == "category"}
        added_codes = {e.code for e in diff.added if e.kind == "category"}
        self.assertNotIn("mens", removed_codes)
        self.assertNotIn("mens", added_codes)

    def test_deterministic_ordering(self):
        v1, _nodes = _base_v1(slug="cmp-order")
        v2 = IndustryTemplate.objects.create(slug=v1.slug, name="کفش", version=2)
        IndustryTemplateCategory.objects.create(industry_template=v2, code="mens", name="مردانه")
        IndustryTemplateCategory.objects.create(industry_template=v2, code="zzz", name="آخر")
        IndustryTemplateCategory.objects.create(industry_template=v2, code="aaa", name="اول")
        diff1 = compare_template_versions(v1, v2)
        diff2 = compare_template_versions(v1, v2)
        codes1 = [e.code for e in diff1.added]
        codes2 = [e.code for e in diff2.added]
        self.assertEqual(codes1, codes2)
        self.assertEqual(codes1, sorted(codes1))

    def test_different_family_raises_error(self):
        v1, _nodes = _base_v1(slug="cmp-family-a")
        other = IndustryTemplate.objects.create(slug="cmp-family-b", name="دیگر", version=1)
        with self.assertRaises(TemplateComparisonError):
            compare_template_versions(v1, other)
