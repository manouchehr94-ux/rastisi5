from django.core.cache import cache
from django.test import TestCase

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
