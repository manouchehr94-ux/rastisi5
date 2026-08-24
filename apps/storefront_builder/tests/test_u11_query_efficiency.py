"""U11 — Performance closure: the known N+1 in
``container_service.get_cell_blocks`` (explicitly named in the master
contract's known-technical-debt list).

Audit: ``get_cell_blocks`` is documented as *deliberately* always issuing a
live query per call (a real write-path correctness guarantee against a
caller holding a stale ``StorefrontCell`` right after another code path
mutated the same Cell's placement — e.g. ``place_section``). That
guarantee is correct for its write-adjacent callers and was left
untouched. But `render_service.build_page_render_items` and two builder
views were calling it in a loop *after already prefetching*
``cells__blocks``/``cells__section`` on the very same queryset moments
earlier — discarding that prefetch and issuing one extra live query per
Cell on every public page render and every builder panel refresh. Added
`blocks_from_prefetched_cell` (same precedence rule, trusts the caller's
already-loaded relations) and wired it into exactly those three confirmed
hot loops — every other `get_cell_blocks` call site (write-path adjacent)
is untouched.
"""

from decimal import Decimal

from django.core.cache import cache
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from apps.catalog.models import Category, Product, Vendor
from apps.storefront_builder.models import StorefrontPage
from apps.storefront_builder.services import container_service, layout_service as svc
from apps.storefront_builder.services.render_service import build_page_render_items
from apps.stores.models import Store, StoreDomain

HOST = "sfb-u11-query.example.com"


def _akhlaghi():
    return Store.objects.get(slug="akhlaghi")


def _make_containers_with_sections(page, count):
    for _ in range(count):
        container = container_service.create_empty_container(page, "single")
        cell = container.cells.order_by("order", "id").first()
        container_service.place_section(cell, _make_rich_text_section(page))


def _make_rich_text_section(page):
    from apps.storefront_builder.models import StorefrontSection

    max_order = page.sections.count()
    return StorefrontSection.objects.create(
        page=page, section_key="rich_text", order=max_order, settings={"body_html": "x"},
    )


class GetCellBlocksNPlusOneTests(TestCase):
    def setUp(self):
        cache.clear()
        self.store = _akhlaghi()
        self.draft = svc.get_or_create_draft(self.store)
        self.page = self.draft.get_page(StorefrontPage.PageType.HOME)
        self.page.sections.all().delete()
        self.page.containers.all().delete()

    def _query_count_for_render(self, container_count):
        self.page.containers.all().delete()
        self.page.sections.all().delete()
        _make_containers_with_sections(self.page, container_count)
        with CaptureQueriesContext(connection) as ctx:
            build_page_render_items(self.page, self.store)
        return len(ctx)

    def test_query_count_does_not_scale_with_container_count(self):
        few = self._query_count_for_render(2)
        many = self._query_count_for_render(8)
        # Before the fix this scaled 1:1 with container/cell count (one
        # extra live query per Cell from get_cell_blocks). A flat/near-flat
        # query count across a 4x increase in containers is the real proof.
        self.assertLessEqual(many, few + 2, f"query count grew with container count: {few} -> {many}")

    def test_blocks_from_prefetched_cell_matches_get_cell_blocks(self):
        """Same precedence rule, same answer — only the query cost differs."""
        container = container_service.create_empty_container(self.page, "single")
        cell = container.cells.order_by("order", "id").first()
        section = _make_rich_text_section(self.page)
        container_service.place_section(cell, section)

        fresh_container = self.page.containers.prefetch_related("cells__section", "cells__blocks").get(pk=container.pk)
        fresh_cell = fresh_container.cells.all()[0]

        live = container_service.get_cell_blocks(cell)
        prefetched = container_service.blocks_from_prefetched_cell(fresh_cell)
        self.assertEqual([b.pk for b in live], [b.pk for b in prefetched])

    def test_blocks_from_prefetched_cell_empty_cell(self):
        container = container_service.create_empty_container(self.page, "single")
        cell = container.cells.order_by("order", "id").first()
        self.assertEqual(container_service.blocks_from_prefetched_cell(cell), [])


class HomepageRenderQueryBudgetTests(TestCase):
    """A real end-to-end proof, not just the isolated service-layer test
    above: the public homepage's query count must not grow proportionally
    with the number of containers on the published page."""

    def setUp(self):
        cache.clear()
        self.store = _akhlaghi()
        StoreDomain.objects.create(
            store=self.store, hostname=HOST, is_primary=True,
            verification_status=StoreDomain.VerificationStatus.VERIFIED, verified_at=timezone.now(),
        )
        self._override = self.settings(ALLOWED_HOSTS=[HOST, "testserver"])
        self._override.enable()
        self.addCleanup(self._override.disable)
        vendor = Vendor.objects.create(store=self.store, name="فروشنده یو۱۱", slug="u11-vendor")
        category = Category.objects.create(store=self.store, name="دسته یو۱۱", slug="u11-cat")
        Product.objects.create(
            store=self.store, vendor=vendor, category=category, name="کالای یو۱۱",
            slug="u11-product", sku="U11-SKU", price=Decimal("100000"), stock=5,
        )

    def _publish_with_containers(self, count):
        draft = svc.get_or_create_draft(self.store)
        page = draft.get_page(StorefrontPage.PageType.HOME)
        page.sections.all().delete()
        page.containers.all().delete()
        _make_containers_with_sections(page, count)
        svc.publish(self.store)

    def test_homepage_query_count_does_not_scale_with_container_count(self):
        self._publish_with_containers(2)
        with CaptureQueriesContext(connection) as few_ctx:
            resp = self.client.get(reverse("catalog:home"), HTTP_HOST=HOST)
        self.assertEqual(resp.status_code, 200)

        self._publish_with_containers(10)
        with CaptureQueriesContext(connection) as many_ctx:
            resp = self.client.get(reverse("catalog:home"), HTTP_HOST=HOST)
        self.assertEqual(resp.status_code, 200)

        self.assertLessEqual(
            len(many_ctx), len(few_ctx) + 3,
            f"public homepage query count grew with container count: {len(few_ctx)} -> {len(many_ctx)}",
        )
