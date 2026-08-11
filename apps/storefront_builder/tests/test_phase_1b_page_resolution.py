"""Phase 1B — Part A: central page resolution service.

Covers required scenarios 1-7 (all six page types resolve from the SAME
published version; each named page type resolves the correct
StorefrontPage) plus tenant isolation (11) for the resolver itself.

Written and read carefully this session; NOT EXECUTED (no Django runtime
available in this sandbox — see the Phase 1B report).
"""

from django.core.cache import cache
from django.test import TestCase

from apps.storefront_builder.models import StorefrontPage
from apps.storefront_builder.services import layout_service as svc
from apps.storefront_builder.services.page_resolution_service import (
    get_published_layout,
    get_published_layout_for_store_id,
    resolve_published_page,
)
from apps.stores.models import Store


def _akhlaghi():
    return Store.objects.get(slug="akhlaghi")


def _other_store():
    return Store.objects.create(
        name="فروشگاه دومِ حل صفحه", slug="sfb-1b-page-res-other", admin_subdomain="sfb-1b-page-res-other",
    )


ALL_PAGE_TYPES = [
    StorefrontPage.PageType.HOME,
    StorefrontPage.PageType.PRODUCT_DETAIL,
    StorefrontPage.PageType.LISTING,
    StorefrontPage.PageType.COLLECTION,
    StorefrontPage.PageType.SEARCH,
    StorefrontPage.PageType.CART,
]


class UnresolvedBeforePublishTests(TestCase):
    """9 (partial) — Draft-only stores (never published) must resolve to
    nothing, never accidentally treated as V2-enabled."""

    def setUp(self):
        cache.clear()
        self.store = _akhlaghi()

    def test_unpublished_store_resolves_to_none_for_every_page_type(self):
        svc.get_or_create_draft(self.store)  # draft exists, never published
        self.assertIsNone(get_published_layout(self.store))
        for page_type in ALL_PAGE_TYPES:
            result = resolve_published_page(self.store, page_type)
            self.assertFalse(result.is_resolved)
            self.assertIsNone(result.version)
            self.assertIsNone(result.page)

    def test_store_with_zero_layout_rows_resolves_to_none(self):
        for page_type in ALL_PAGE_TYPES:
            result = resolve_published_page(self.store, page_type)
            self.assertFalse(result.is_resolved)


class AllSixPageTypesResolveFromSameVersionTests(TestCase):
    """1-7 — all six page types resolve from the SAME published version;
    each named page type resolves to its own correctly-typed StorefrontPage."""

    def setUp(self):
        cache.clear()
        self.store = _akhlaghi()
        svc.get_or_create_draft(self.store)
        self.published = svc.publish(self.store)

    def test_all_six_resolve_to_the_same_published_version(self):
        resolved_versions = {
            resolve_published_page(self.store, pt).version.pk for pt in ALL_PAGE_TYPES
        }
        self.assertEqual(resolved_versions, {self.published.pk})

    def test_home_resolves_home_page_type(self):
        result = resolve_published_page(self.store, StorefrontPage.PageType.HOME)
        self.assertEqual(result.page.page_type, StorefrontPage.PageType.HOME)

    def test_product_detail_resolves_product_detail_page_type(self):
        result = resolve_published_page(self.store, StorefrontPage.PageType.PRODUCT_DETAIL)
        self.assertEqual(result.page.page_type, StorefrontPage.PageType.PRODUCT_DETAIL)

    def test_listing_resolves_listing_page_type(self):
        result = resolve_published_page(self.store, StorefrontPage.PageType.LISTING)
        self.assertEqual(result.page.page_type, StorefrontPage.PageType.LISTING)

    def test_collection_resolves_collection_page_type(self):
        result = resolve_published_page(self.store, StorefrontPage.PageType.COLLECTION)
        self.assertEqual(result.page.page_type, StorefrontPage.PageType.COLLECTION)

    def test_search_resolves_search_page_type(self):
        result = resolve_published_page(self.store, StorefrontPage.PageType.SEARCH)
        self.assertEqual(result.page.page_type, StorefrontPage.PageType.SEARCH)

    def test_cart_resolves_cart_page_type(self):
        result = resolve_published_page(self.store, StorefrontPage.PageType.CART)
        self.assertEqual(result.page.page_type, StorefrontPage.PageType.CART)

    def test_publishing_a_new_version_atomically_changes_resolution_for_all_page_types(self):
        """10 — publishing a new version atomically changes the global
        shell/page resolution for all page types at once."""
        old_page_pks = {pt: resolve_published_page(self.store, pt).page.pk for pt in ALL_PAGE_TYPES}

        svc.get_or_create_draft(self.store)
        new_published = svc.publish(self.store)

        new_page_pks = {pt: resolve_published_page(self.store, pt).page.pk for pt in ALL_PAGE_TYPES}
        for pt in ALL_PAGE_TYPES:
            self.assertNotEqual(old_page_pks[pt], new_page_pks[pt])
            self.assertEqual(resolve_published_page(self.store, pt).version.pk, new_published.pk)


class DraftNeverLeaksIntoResolutionTests(TestCase):
    """9 — Draft changes must NOT leak into public routes before publish."""

    def setUp(self):
        cache.clear()
        self.store = _akhlaghi()
        svc.get_or_create_draft(self.store)
        svc.publish(self.store)

    def test_editing_the_draft_after_publish_does_not_change_resolution(self):
        published_before = resolve_published_page(self.store, StorefrontPage.PageType.HOME).version.pk
        draft = svc.get_or_create_draft(self.store)
        draft.header_config = {**(draft.header_config or {}), "announcement_text": "DRAFT-ONLY"}
        draft.save(update_fields=["header_config"])

        for page_type in ALL_PAGE_TYPES:
            result = resolve_published_page(self.store, page_type)
            self.assertEqual(result.version.pk, published_before)
            self.assertNotEqual(result.version.pk, draft.pk)


class PageResolutionTenantIsolationTests(TestCase):
    """11 — Store A must never receive Store B's version/page/config."""

    def setUp(self):
        cache.clear()
        self.store_a = _akhlaghi()
        self.store_b = _other_store()
        svc.get_or_create_draft(self.store_a)
        self.published_a = svc.publish(self.store_a)
        svc.get_or_create_draft(self.store_b)
        self.published_b = svc.publish(self.store_b)

    def test_store_a_resolution_never_returns_store_bs_version(self):
        for page_type in ALL_PAGE_TYPES:
            result_a = resolve_published_page(self.store_a, page_type)
            self.assertEqual(result_a.version.pk, self.published_a.pk)
            self.assertNotEqual(result_a.version.pk, self.published_b.pk)

    def test_get_published_layout_for_store_id_is_store_scoped(self):
        layout_a = get_published_layout_for_store_id(self.store_a.pk)
        layout_b = get_published_layout_for_store_id(self.store_b.pk)
        self.assertEqual(layout_a.published_version_id, self.published_a.pk)
        self.assertEqual(layout_b.published_version_id, self.published_b.pk)
        self.assertNotEqual(layout_a.published_version_id, layout_b.published_version_id)

    def test_get_published_layout_for_store_id_none_returns_none(self):
        self.assertIsNone(get_published_layout_for_store_id(None))
