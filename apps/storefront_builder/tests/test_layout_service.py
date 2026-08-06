from django.core.cache import cache
from django.test import TestCase

from apps.catalog.models import IndustryTemplate
from apps.core.services.rate_limit import RateLimitExceeded
from apps.storefront_builder.models import StorefrontLayoutVersion, StorefrontSection
from apps.storefront_builder.services import layout_service as svc
from apps.stores.models import Store


def _akhlaghi():
    return Store.objects.get(slug="akhlaghi")


def _other_store():
    return Store.objects.create(name="فروشگاه دوم", slug="second-store", admin_subdomain="second-store")


class GetOrCreateDraftTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_creates_draft_when_none_exists(self):
        draft = svc.get_or_create_draft(_akhlaghi())
        self.assertEqual(draft.status, StorefrontLayoutVersion.Status.DRAFT)
        self.assertEqual(draft.version_number, 1)

    def test_idempotent_returns_same_draft(self):
        a = svc.get_or_create_draft(_akhlaghi())
        b = svc.get_or_create_draft(_akhlaghi())
        self.assertEqual(a.pk, b.pk)

    def test_new_draft_clones_published_content(self):
        store = _akhlaghi()
        d1 = svc.get_or_create_draft(store)
        # d1 is the first-ever draft, so it starts pre-populated by the
        # legacy bootstrap (checkpoint 5) — clear it to isolate exactly
        # what this test cares about: that publish -> next-draft round-trips
        # sections faithfully, independent of bootstrap content.
        d1.sections.all().delete()
        StorefrontSection.objects.create(version=d1, section_key="hero_banner", order=0, settings={"a": 1})
        published = svc.publish(store)
        self.assertEqual(published.sections.count(), 1)

        d2 = svc.get_or_create_draft(store)
        self.assertNotEqual(d1.pk, d2.pk)
        self.assertEqual(d2.sections.count(), 1)
        self.assertEqual(d2.sections.first().section_key, "hero_banner")

    def test_two_stores_get_independent_drafts(self):
        store_a = _akhlaghi()
        store_b = _other_store()
        draft_a = svc.get_or_create_draft(store_a)
        draft_b = svc.get_or_create_draft(store_b)
        self.assertNotEqual(draft_a.layout_id, draft_b.layout_id)


class PublishTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_publish_requires_existing_draft(self):
        with self.assertRaises(svc.NoDraftToPublishError):
            svc.publish(_akhlaghi())

    def test_publish_sets_layout_pointers(self):
        store = _akhlaghi()
        draft = svc.get_or_create_draft(store)
        published = svc.publish(store)
        self.assertEqual(draft.pk, published.pk)

        layout = svc.get_or_create_layout(store)
        self.assertEqual(layout.published_version_id, published.pk)
        self.assertIsNone(layout.draft_version_id)
        self.assertTrue(layout.uses_visual_storefront_layout)

    def test_publish_archives_previous_published(self):
        store = _akhlaghi()
        svc.get_or_create_draft(store)
        first = svc.publish(store)

        svc.get_or_create_draft(store)
        svc.publish(store)

        first.refresh_from_db()
        self.assertEqual(first.status, StorefrontLayoutVersion.Status.ARCHIVED)

    def test_publish_sets_published_at(self):
        store = _akhlaghi()
        svc.get_or_create_draft(store)
        published = svc.publish(store)
        self.assertIsNotNone(published.published_at)

    def test_publish_computes_fingerprint(self):
        store = _akhlaghi()
        svc.get_or_create_draft(store)
        published = svc.publish(store)
        self.assertTrue(published.content_fingerprint)


class DiscardDraftTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_discard_removes_draft(self):
        store = _akhlaghi()
        draft = svc.get_or_create_draft(store)
        svc.discard_draft(store)
        layout = svc.get_or_create_layout(store)
        self.assertIsNone(layout.draft_version_id)
        self.assertFalse(StorefrontLayoutVersion.objects.filter(pk=draft.pk).exists())

    def test_discard_does_not_affect_published(self):
        store = _akhlaghi()
        svc.get_or_create_draft(store)
        published = svc.publish(store)
        svc.get_or_create_draft(store)
        svc.discard_draft(store)
        layout = svc.get_or_create_layout(store)
        self.assertEqual(layout.published_version_id, published.pk)

    def test_discard_noop_when_no_draft(self):
        store = _akhlaghi()
        svc.discard_draft(store)  # must not raise


class RestoreVersionTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_restore_creates_new_draft_not_publish(self):
        store = _akhlaghi()
        d1 = svc.get_or_create_draft(store)
        StorefrontSection.objects.create(version=d1, section_key="hero_banner", order=0)
        v1 = svc.publish(store)

        d2 = svc.get_or_create_draft(store)
        StorefrontSection.objects.create(version=d2, section_key="newest_products", order=1)
        svc.publish(store)

        restored = svc.restore_version(store, v1.pk)
        self.assertEqual(restored.status, StorefrontLayoutVersion.Status.DRAFT)
        self.assertEqual(restored.source, StorefrontLayoutVersion.Source.RESTORED)

        layout = svc.get_or_create_layout(store)
        self.assertEqual(layout.draft_version_id, restored.pk)
        # published pointer must NOT have moved — restore never auto-publishes
        self.assertNotEqual(layout.published_version_id, restored.pk)

    def test_restore_clones_source_sections(self):
        store = _akhlaghi()
        d1 = svc.get_or_create_draft(store)
        d1.sections.all().delete()  # isolate from checkpoint-5 legacy-bootstrap defaults
        StorefrontSection.objects.create(version=d1, section_key="hero_banner", order=0, settings={"x": 1})
        v1 = svc.publish(store)

        svc.get_or_create_draft(store)
        svc.publish(store)

        restored = svc.restore_version(store, v1.pk)
        self.assertEqual(restored.sections.count(), 1)
        self.assertEqual(restored.sections.first().settings, {"x": 1})

    def test_restore_replaces_existing_unsaved_draft(self):
        store = _akhlaghi()
        svc.get_or_create_draft(store)
        v1 = svc.publish(store)

        stale_draft = svc.get_or_create_draft(store)
        restored = svc.restore_version(store, v1.pk)
        self.assertNotEqual(stale_draft.pk, restored.pk)
        self.assertFalse(StorefrontLayoutVersion.objects.filter(pk=stale_draft.pk).exists())

    def test_restore_rejects_cross_store_version(self):
        store_a = _akhlaghi()
        store_b = _other_store()

        svc.get_or_create_draft(store_a)
        version_a = svc.publish(store_a)

        with self.assertRaises(svc.CrossStoreVersionError):
            svc.restore_version(store_b, version_a.pk)

    def test_restore_nonexistent_version_rejected(self):
        store = _akhlaghi()
        with self.assertRaises(svc.CrossStoreVersionError):
            svc.restore_version(store, 999999)


class ListVersionsTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_lists_all_versions_newest_first(self):
        store = _akhlaghi()
        svc.get_or_create_draft(store)
        svc.publish(store)
        svc.get_or_create_draft(store)
        svc.publish(store)

        versions = list(svc.list_versions(store))
        self.assertEqual(len(versions), 2)
        self.assertGreater(versions[0].version_number, versions[1].version_number)

    def test_versions_scoped_to_store(self):
        store_a = _akhlaghi()
        store_b = _other_store()
        svc.get_or_create_draft(store_a)
        svc.publish(store_a)

        self.assertEqual(svc.list_versions(store_a).count(), 1)
        self.assertEqual(svc.list_versions(store_b).count(), 0)


class RateLimitTests(TestCase):
    """اطمینان از این‌که publish/restore/ساخت Draft محدود به نرخ هستند، اما
    این تست‌ها فقط رفتار «فراخوانی مکرر رد می‌شود» را چک می‌کنند، نه بازچینش
    معمولی که طبق تصمیم کاربر عمداً rate-limit ندارد."""

    def setUp(self):
        cache.clear()

    def test_excessive_publish_calls_rejected(self):
        store = _akhlaghi()
        with self.settings():
            from apps.storefront_builder.services import layout_service

            original = layout_service._PUBLISH_RATE_LIMIT
            layout_service._PUBLISH_RATE_LIMIT = dict(max_attempts=2, window_seconds=3600)
            try:
                for _ in range(2):
                    svc.get_or_create_draft(store)
                    svc.publish(store)
                svc.get_or_create_draft(store)
                with self.assertRaises(RateLimitExceeded):
                    svc.publish(store)
            finally:
                layout_service._PUBLISH_RATE_LIMIT = original

    def test_excessive_restore_calls_rejected(self):
        store = _akhlaghi()
        svc.get_or_create_draft(store)
        v1 = svc.publish(store)

        from apps.storefront_builder.services import layout_service

        original = layout_service._RESTORE_RATE_LIMIT
        layout_service._RESTORE_RATE_LIMIT = dict(max_attempts=1, window_seconds=3600)
        try:
            svc.restore_version(store, v1.pk)
            with self.assertRaises(RateLimitExceeded):
                svc.restore_version(store, v1.pk)
        finally:
            layout_service._RESTORE_RATE_LIMIT = original


class ApplyIndustryLayoutTests(TestCase):
    def setUp(self):
        cache.clear()

    def _template(self, slug="test-apply-industry", **keys):
        return IndustryTemplate.objects.create(
            slug=slug, name="صنف تست",
            default_section_keys=keys.get("default_section_keys", ["hero_banner", "category_grid"]),
        )

    def test_applies_directly_when_never_published(self):
        store = _akhlaghi()
        template = self._template()
        draft = svc.apply_industry_layout(store, template)
        self.assertEqual(draft.source, StorefrontLayoutVersion.Source.INDUSTRY_TEMPLATE)
        self.assertEqual(
            list(draft.sections.order_by("order").values_list("section_key", flat=True)),
            ["hero_banner", "category_grid"],
        )
        layout = svc.get_or_create_layout(store)
        self.assertEqual(layout.draft_version_id, draft.pk)

    def test_rejected_without_force_when_already_published(self):
        store = _akhlaghi()
        svc.get_or_create_draft(store)
        svc.publish(store)
        template = self._template(slug="test-apply-industry-published")
        with self.assertRaises(svc.StorefrontAlreadyPublishedError):
            svc.apply_industry_layout(store, template)

    def test_applies_with_force_when_already_published_does_not_touch_published_version(self):
        store = _akhlaghi()
        svc.get_or_create_draft(store)
        published = svc.publish(store)
        template = self._template(slug="test-apply-industry-forced")
        draft = svc.apply_industry_layout(store, template, force=True)
        self.assertEqual(draft.source, StorefrontLayoutVersion.Source.INDUSTRY_TEMPLATE)
        layout = svc.get_or_create_layout(store)
        self.assertEqual(layout.published_version_id, published.pk)
        self.assertEqual(layout.draft_version_id, draft.pk)

    def test_replaces_existing_draft_not_stacked(self):
        store = _akhlaghi()
        first_draft = svc.get_or_create_draft(store)
        template = self._template(slug="test-apply-industry-replace")
        new_draft = svc.apply_industry_layout(store, template)
        self.assertNotEqual(new_draft.pk, first_draft.pk)
        self.assertFalse(StorefrontLayoutVersion.objects.filter(pk=first_draft.pk).exists())

    def test_never_leaves_layout_without_draft_on_empty_keys(self):
        store = _akhlaghi()
        template = self._template(slug="test-apply-industry-empty", default_section_keys=[])
        draft = svc.apply_industry_layout(store, template)
        self.assertGreater(draft.sections.count(), 0)


class ValidateHeaderConfigTests(TestCase):
    """A2 — validate_header_config: قواعد اعمال‌شده روی قرارداد واقعی موجود
    (HEADER_TOGGLE_FIELDS)، نه فرض‌های سند معماری."""

    def test_accepts_full_valid_config(self):
        cleaned = svc.validate_header_config({
            "show_search": True, "show_account": True, "show_cart": True,
            "show_wishlist": True, "sticky": False, "announcement_enabled": True,
            "announcement_text": "سلام",
        })
        self.assertTrue(cleaned["show_cart"])
        self.assertEqual(cleaned["announcement_text"], "سلام")

    def test_missing_fields_default_to_true(self):
        cleaned = svc.validate_header_config({})
        for field in ["show_search", "show_account", "show_cart", "show_wishlist", "sticky", "announcement_enabled"]:
            self.assertTrue(cleaned[field])

    def test_rejects_hidden_cart(self):
        with self.assertRaises(svc.HeaderConfigValidationError):
            svc.validate_header_config({"show_cart": False})

    def test_rejects_non_boolean_toggle(self):
        with self.assertRaises(svc.HeaderConfigValidationError):
            svc.validate_header_config({"show_cart": True, "show_search": "yes"})

    def test_rejects_non_string_announcement_text(self):
        with self.assertRaises(svc.HeaderConfigValidationError):
            svc.validate_header_config({"show_cart": True, "announcement_text": 12345})

    def test_truncates_long_announcement_text(self):
        cleaned = svc.validate_header_config({"show_cart": True, "announcement_text": "ا" * 500})
        self.assertEqual(len(cleaned["announcement_text"]), 300)

    def test_unknown_keys_are_dropped_silently(self):
        cleaned = svc.validate_header_config({"show_cart": True, "malicious_field": "<script>"})
        self.assertNotIn("malicious_field", cleaned)


class ValidateFooterConfigTests(TestCase):
    """A2 — validate_footer_config: حداقل یک بخش فعال، طبق تصمیم محصولی
    این فاز (مستند در layout_service.validate_footer_config)."""

    def test_accepts_config_with_one_active_block(self):
        all_false_except_copyright = {f: False for f in [
            "show_about", "show_contact", "show_quick_links", "show_categories",
            "show_social", "show_trust_badges", "show_payment_logos", "show_newsletter",
        ]} | {"show_copyright": True}
        cleaned = svc.validate_footer_config(all_false_except_copyright)
        self.assertTrue(cleaned["show_copyright"])
        self.assertFalse(cleaned["show_about"])

    def test_missing_fields_default_to_true(self):
        cleaned = svc.validate_footer_config({})
        self.assertTrue(cleaned["show_about"])

    def test_rejects_all_blocks_disabled(self):
        all_false = {f: False for f in [
            "show_about", "show_contact", "show_quick_links", "show_categories",
            "show_social", "show_trust_badges", "show_payment_logos", "show_newsletter", "show_copyright",
        ]}
        with self.assertRaises(svc.FooterConfigValidationError):
            svc.validate_footer_config(all_false)

    def test_rejects_non_boolean_toggle(self):
        with self.assertRaises(svc.FooterConfigValidationError):
            svc.validate_footer_config({"show_about": "on"})

    def test_unknown_keys_are_dropped_silently(self):
        cleaned = svc.validate_footer_config({"show_about": True, "malicious_field": "<script>"})
        self.assertNotIn("malicious_field", cleaned)
