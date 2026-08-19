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
from apps.catalog.industry_templates.registry import (
    ALL_INDUSTRY_TEMPLATES as INDUSTRY_TEMPLATES,
    DEPRECATED_LEGACY_SLUGS,
)
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
        for template in IndustryTemplate.objects.exclude(slug__in=DEPRECATED_LEGACY_SLUGS):
            with self.subTest(template=template.slug):
                self.assertEqual(template.readiness, IndustryTemplate.Readiness.PRODUCTION_READY)
                self.assertTrue(template.content_fingerprint)
        # صنف‌های قدیمیِ منسوخ‌شده (بدونِ تناظرِ یک‌به‌یک با کاتالوگِ تأییدشده‌ی
        # ۱۰۰ صنفی) عمداً پس از seed غیرفعال/منسوخ می‌شوند — رکوردشان می‌ماند،
        # اما دیگر برای نصبِ جدید پیشنهاد نمی‌شوند (نگاه کنید به بخشِ ۱).
        for template in IndustryTemplate.objects.filter(slug__in=DEPRECATED_LEGACY_SLUGS):
            with self.subTest(template=template.slug):
                self.assertEqual(template.readiness, IndustryTemplate.Readiness.DEPRECATED)
                self.assertFalse(template.is_active)

    def test_every_template_slug_is_seeded_and_active(self):
        _run_seed()
        seeded_slugs = set(IndustryTemplate.objects.values_list("slug", flat=True))
        expected_slugs = {entry["slug"] for entry in INDUSTRY_TEMPLATES}
        self.assertEqual(seeded_slugs, expected_slugs)
        inactive_slugs = set(IndustryTemplate.objects.filter(is_active=False).values_list("slug", flat=True))
        self.assertEqual(inactive_slugs, set(DEPRECATED_LEGACY_SLUGS))

    def test_every_template_has_real_categories_and_attributes(self):
        """صنف‌های غنی (دستی) همچنان معیارِ قدیمی را دارند؛ صنف‌های «کمینه‌یِ
        مفید» (بخشِ ۹ — یک دسته‌بندیِ تک‌سطحی + چند ویژگیِ متنی، یا برایِ
        رستهِ خدماتی/سایر حتی بدونِ ویژگی) فقط باید حداقل یک دسته‌بندیِ
        واقعی داشته باشند."""
        _run_seed()
        for template in IndustryTemplate.objects.all():
            with self.subTest(template=template.slug):
                self.assertGreaterEqual(template.categories.count(), 1)
                if template.sector in (IndustryTemplate.Sector.SERVICES, IndustryTemplate.Sector.OTHER):
                    continue
                self.assertGreaterEqual(template.attributes.count(), 1)

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


class IndustryTemplateBootstrapMigrationTests(TestCase):
    """Regression test for Issue 2 (production had zero Industry Templates).

    Root cause: ``seed_industry_templates`` was a correct, idempotent,
    production-safe management command — but purely opt-in. Nothing ever
    invoked it automatically, so a fresh production database that no
    operator remembered to run it against silently ended up with zero
    ``IndustryTemplate`` rows, and the onboarding "choose your industry"
    step fell back to its (otherwise correct) empty state for every
    merchant.

    The fix is ``apps/catalog/migrations/0039_bootstrap_industry_templates.py``,
    which runs the exact same idempotent command as part of the schema
    migration itself. Django's test runner builds the test database by
    applying every migration before any test runs — so if the bootstrap
    migration works, this test class's ``IndustryTemplate`` table is
    already populated here, without this test (or its ``setUp``) ever
    calling ``seed_industry_templates`` itself. That is exactly what a
    fresh production database gets from a plain ``python manage.py migrate``,
    with no extra manual step required.
    """

    def test_migration_alone_bootstraps_production_ready_templates(self):
        self.assertGreater(IndustryTemplate.objects.count(), 0)
        self.assertGreater(
            IndustryTemplate.objects.filter(
                is_active=True, readiness=IndustryTemplate.Readiness.PRODUCTION_READY,
            ).count(),
            0,
        )

    def test_migration_alone_matches_the_full_registry(self):
        seeded_slugs = set(IndustryTemplate.objects.values_list("slug", flat=True))
        expected_slugs = {entry["slug"] for entry in INDUSTRY_TEMPLATES}
        self.assertEqual(seeded_slugs, expected_slugs)

    def test_re_running_the_command_after_migration_does_not_duplicate(self):
        count_after_migration = IndustryTemplate.objects.count()
        _run_seed()
        self.assertEqual(IndustryTemplate.objects.count(), count_after_migration)


class InstallEverySeededIndustryTests(TestCase):
    """§36.11 — هر صنف ساخته‌شده باید بدون خطا روی یک Store واقعی نصب شود."""

    def setUp(self):
        _run_seed()
        self.store = Store.objects.get(slug="akhlaghi")

    def test_every_seeded_industry_installs_cleanly(self):
        for template in IndustryTemplate.objects.exclude(slug__in=DEPRECATED_LEGACY_SLUGS):
            with self.subTest(template=template.slug):
                store = Store.objects.create(
                    name=f"فروشگاه آزمایشی {template.slug}",
                    slug=f"test-store-{template.slug}",
                    status=Store.Status.ACTIVE,
                )
                result = install_industry_template(store, template)
                self.assertEqual(len(result.categories_created), template.categories.count())
                self.assertGreater(Category.objects.filter(store=store).count(), 0)
