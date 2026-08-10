"""تست‌هایِ ProductMetafield — مکانیزمِ extensible متادیتایِ محصول.

پوشش:
  - ساخت و خواندن metafield
  - UniqueConstraint enforcement
  - Template tag product_metafield
  - Namespace constants
"""

from django.test import TestCase

from apps.catalog.models import (
    Product, ProductMetafield,
    METAFIELD_NS_SIZE_GUIDE, METAFIELD_NS_ARTISAN,
    METAFIELD_NS_SPECS, METAFIELD_NS_CUSTOM,
)


class ProductMetafieldNamespaceTests(TestCase):
    """ثابت‌های namespace."""

    def test_namespace_constants_defined(self):
        self.assertEqual(METAFIELD_NS_SIZE_GUIDE, "size_guide")
        self.assertEqual(METAFIELD_NS_ARTISAN, "artisan")
        self.assertEqual(METAFIELD_NS_SPECS, "specs")
        self.assertEqual(METAFIELD_NS_CUSTOM, "custom")


class ProductMetafieldModelTests(TestCase):
    """مدل ProductMetafield."""

    def test_meta_ordering(self):
        self.assertEqual(ProductMetafield._meta.ordering, ["namespace", "key"])

    def test_unique_constraint_name(self):
        constraint_names = {c.name for c in ProductMetafield._meta.constraints}
        self.assertIn("uniq_product_metafield", constraint_names)

    def test_str_representation(self):
        mf = ProductMetafield(
            namespace="artisan", key="maker", value_text="کارگاه صفا"
        )
        self.assertIn("artisan.maker", str(mf))
        self.assertIn("کارگاه صفا", str(mf))

    def test_value_json_default_is_none(self):
        mf = ProductMetafield(namespace="specs", key="weight")
        self.assertIsNone(mf.value_json)

    def test_value_text_default_is_empty(self):
        mf = ProductMetafield(namespace="specs", key="weight")
        self.assertEqual(mf.value_text, "")


class ProductMetafieldTemplateTagTests(TestCase):
    """Template tag product_metafield."""

    def test_tag_returns_default_without_prefetch(self):
        """بدون داده: default برمی‌گردد."""
        from apps.catalog.templatetags.catalog_extras import product_metafield

        # ساخت mock product بدون metafield
        class FakeProduct:
            pk = 99999
            _prefetched_objects_cache = {}

        result = product_metafield(FakeProduct(), "artisan", "maker", "ندارد")
        self.assertEqual(result, "ندارد")

    def test_tag_reads_from_prefetch_cache(self):
        """از prefetch cache می‌خواند."""
        from apps.catalog.templatetags.catalog_extras import product_metafield

        class FakeMF:
            def __init__(self, ns, k, v):
                self.namespace = ns
                self.key = k
                self.value_text = v

        class FakeProduct:
            pk = 1
            _prefetched_objects_cache = {
                "metafields": [
                    FakeMF("artisan", "maker", "استاد حسینی"),
                    FakeMF("artisan", "region", "اصفهان"),
                ]
            }

        self.assertEqual(product_metafield(FakeProduct(), "artisan", "maker", ""), "استاد حسینی")
        self.assertEqual(product_metafield(FakeProduct(), "artisan", "region", ""), "اصفهان")
        self.assertEqual(product_metafield(FakeProduct(), "artisan", "missing", "خالی"), "خالی")
