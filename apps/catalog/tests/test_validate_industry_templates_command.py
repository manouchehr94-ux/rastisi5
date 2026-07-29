import json
from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from apps.catalog.models import (
    Attribute,
    IndustryTemplate,
    IndustryTemplateAttribute,
    IndustryTemplateCategory,
)


def _valid_template(slug="cmd-valid", version=1):
    template = IndustryTemplate.objects.create(slug=slug, name="قالب معتبر", version=version)
    IndustryTemplateCategory.objects.create(industry_template=template, code="root", name="ریشه")
    IndustryTemplateAttribute.objects.create(
        industry_template=template, code="brand", label="برند", data_type=Attribute.DataType.TEXT,
    )
    return template


def _invalid_template(slug="cmd-invalid", version=1):
    return IndustryTemplate.objects.create(slug=slug, name="ناموفق", version=version)


class ValidateCommandTests(TestCase):
    def test_successful_validation_exit_zero(self):
        _valid_template()
        out = StringIO()
        call_command("validate_industry_templates", "--industry", "cmd-valid", stdout=out)
        self.assertIn("معتبر", out.getvalue())

    def test_failed_validation_raises_system_exit(self):
        _invalid_template()
        with self.assertRaises(SystemExit) as ctx:
            call_command("validate_industry_templates", "--industry", "cmd-invalid", stdout=StringIO())
        self.assertEqual(ctx.exception.code, 1)

    def test_json_output_is_valid_structured_json(self):
        _valid_template(slug="cmd-json")
        out = StringIO()
        call_command("validate_industry_templates", "--industry", "cmd-json", "--json", stdout=out)
        payload = json.loads(out.getvalue())
        self.assertEqual(len(payload), 1)
        self.assertIn("errors", payload[0])
        self.assertIn("metrics", payload[0])
        self.assertIn("quality_score", payload[0])

    def test_industry_filter_narrows_results(self):
        _valid_template(slug="cmd-filter-a")
        _valid_template(slug="cmd-filter-b")
        out = StringIO()
        call_command("validate_industry_templates", "--industry", "cmd-filter-a", "--json", stdout=out)
        payload = json.loads(out.getvalue())
        self.assertEqual(len(payload), 1)
        self.assertEqual(payload[0]["template"]["slug"], "cmd-filter-a")

    def test_template_version_filter(self):
        _valid_template(slug="cmd-ver", version=1)
        _valid_template(slug="cmd-ver", version=2)
        out = StringIO()
        call_command(
            "validate_industry_templates", "--industry", "cmd-ver", "--template-version", "2", "--json", stdout=out,
        )
        payload = json.loads(out.getvalue())
        self.assertEqual(len(payload), 1)
        self.assertEqual(payload[0]["template"]["version"], 2)

    def test_no_matching_templates_raises_system_exit(self):
        with self.assertRaises(SystemExit):
            call_command(
                "validate_industry_templates", "--industry", "does-not-exist", stdout=StringIO(), stderr=StringIO(),
            )

    def test_apply_persists_readiness(self):
        template = _valid_template(slug="cmd-apply")
        call_command("validate_industry_templates", "--industry", "cmd-apply", "--apply", stdout=StringIO())
        template.refresh_from_db()
        self.assertEqual(template.readiness, IndustryTemplate.Readiness.PRODUCTION_READY)
        self.assertTrue(template.content_fingerprint)

    def test_without_apply_does_not_mutate_data(self):
        template = _valid_template(slug="cmd-dry-run")
        call_command("validate_industry_templates", "--industry", "cmd-dry-run", stdout=StringIO())
        template.refresh_from_db()
        self.assertEqual(template.readiness, IndustryTemplate.Readiness.DRAFT)
        self.assertEqual(template.content_fingerprint, "")

    def test_strict_mode_with_apply_downgrades_warnings(self):
        template = _valid_template(slug="cmd-strict")
        # leaf category with no mapping → a warning-level finding
        IndustryTemplateCategory.objects.create(industry_template=template, code="leaf", name="بدون نگاشت")
        call_command(
            "validate_industry_templates", "--industry", "cmd-strict", "--apply", "--strict", stdout=StringIO(),
        )
        template.refresh_from_db()
        self.assertEqual(template.readiness, IndustryTemplate.Readiness.REVIEW_REQUIRED)

    def test_errors_only_flag_omits_warnings_from_output(self):
        template = _valid_template(slug="cmd-errorsonly")
        IndustryTemplateCategory.objects.create(industry_template=template, code="leaf3", name="بدون نگاشت۲")
        out = StringIO()
        call_command("validate_industry_templates", "--industry", "cmd-errorsonly", "--errors-only", stdout=out)
        self.assertNotIn("[WARN]", out.getvalue())

    def test_validates_all_templates_when_no_filter(self):
        _valid_template(slug="cmd-all-a")
        _valid_template(slug="cmd-all-b")
        out = StringIO()
        call_command("validate_industry_templates", "--json", stdout=out)
        payload = json.loads(out.getvalue())
        slugs = {entry["template"]["slug"] for entry in payload}
        self.assertIn("cmd-all-a", slugs)
        self.assertIn("cmd-all-b", slugs)
