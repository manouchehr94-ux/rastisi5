from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from apps.catalog.models import Category, Product, Vendor
from apps.catalog.services import collection_service as svc
from apps.stores.models import Store


def _akhlaghi():
    return Store.objects.get(slug="akhlaghi")


def _product(store, slug, *, status=Product.Status.ACTIVE, vendor=None, category=None):
    vendor = vendor or Vendor.objects.create(store=store, name=f"فروشنده {slug}", slug=f"v-{slug}")
    category = category or Category.objects.create(store=store, name=f"دسته {slug}", slug=f"c-{slug}")
    return Product.objects.create(
        store=store, vendor=vendor, category=category, name=f"کالای {slug}", slug=slug,
        sku=f"SKU-{slug}", price=Decimal("10000"), status=status,
    )


class CollectionIndexViewTests(TestCase):
    def setUp(self):
        self.store = _akhlaghi()

    def test_shows_active_collections(self):
        active = svc.create_collection(self.store, name="فعال عمومی")
        resp = self.client.get(reverse("catalog:collection-index"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, active.name)

    def test_hides_inactive_collections(self):
        inactive = svc.create_collection(self.store, name="غیرفعال عمومی")
        svc.deactivate_collection(inactive)
        resp = self.client.get(reverse("catalog:collection-index"))
        self.assertNotContains(resp, inactive.name)

    def test_empty_state(self):
        resp = self.client.get(reverse("catalog:collection-index"))
        self.assertContains(resp, "فعلاً کالکشنی")


class CollectionDetailViewTests(TestCase):
    def setUp(self):
        self.store = _akhlaghi()

    def test_active_collection_renders(self):
        collection = svc.create_collection(self.store, name="کالکشن عمومی", description="توضیح تستی")
        resp = self.client.get(reverse("catalog:collection-detail", args=[collection.slug]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "کالکشن عمومی")
        self.assertContains(resp, "توضیح تستی")

    def test_inactive_collection_404(self):
        collection = svc.create_collection(self.store, name="غیرفعال جزئیات")
        svc.deactivate_collection(collection)
        resp = self.client.get(reverse("catalog:collection-detail", args=[collection.slug]))
        self.assertEqual(resp.status_code, 404)

    def test_missing_slug_404(self):
        resp = self.client.get(reverse("catalog:collection-detail", args=["does-not-exist"]))
        self.assertEqual(resp.status_code, 404)

    def test_cross_store_slug_404(self):
        other_store = Store.objects.create(name="فروشگاه دیگر عمومی", slug="coll-public-cross", admin_subdomain="coll-public-cross")
        other_collection = svc.create_collection(other_store, name="فروشگاه دیگر")
        resp = self.client.get(reverse("catalog:collection-detail", args=[other_collection.slug]))
        self.assertEqual(resp.status_code, 404)

    def test_only_storefront_visible_products_shown(self):
        collection = svc.create_collection(self.store, name="نمایش کالا")
        visible = _product(self.store, "public-visible")
        hidden = _product(self.store, "public-hidden", status=Product.Status.DRAFT)
        svc.add_product(collection, visible)
        svc.add_product(collection, hidden)
        resp = self.client.get(reverse("catalog:collection-detail", args=[collection.slug]))
        self.assertContains(resp, visible.name)
        self.assertNotContains(resp, hidden.name)

    def test_manual_order_preserved(self):
        collection = svc.create_collection(self.store, name="ترتیب عمومی")
        p1 = _product(self.store, "public-order-1")
        p2 = _product(self.store, "public-order-2")
        svc.add_product(collection, p1)
        svc.add_product(collection, p2)
        svc.reorder_items(collection, [item.pk for item in collection.items.order_by("-order")])
        resp = self.client.get(reverse("catalog:collection-detail", args=[collection.slug]))
        body = resp.content.decode()
        self.assertLess(body.index(p2.name), body.index(p1.name))

    def test_empty_state_when_no_visible_products(self):
        collection = svc.create_collection(self.store, name="خالی عمومی")
        resp = self.client.get(reverse("catalog:collection-detail", args=[collection.slug]))
        self.assertContains(resp, "فعلاً کالایی")

    def test_seo_fields_rendered(self):
        collection = svc.create_collection(
            self.store, name="سئو عمومی", seo_title="عنوان سئوی تست", seo_description="توضیح متای تست",
        )
        resp = self.client.get(reverse("catalog:collection-detail", args=[collection.slug]))
        self.assertContains(resp, "عنوان سئوی تست")
        self.assertContains(resp, "توضیح متای تست")

    def test_no_n_plus_one_query_growth(self):
        """با رشدِ تعدادِ کالای کالکشن، تعدادِ کوئریِ صفحه نباید رشد کند —
        رشدِ خطی یعنی select_related/prefetch_related جلویِ N+1 را نگرفته."""
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        small = svc.create_collection(self.store, name="کوئری‌بودجه کوچک")
        for i in range(3):
            svc.add_product(small, _product(self.store, f"query-budget-small-{i}"))

        large = svc.create_collection(self.store, name="کوئری‌بودجه بزرگ")
        for i in range(15):
            svc.add_product(large, _product(self.store, f"query-budget-large-{i}"))

        with CaptureQueriesContext(connection) as small_queries:
            resp_small = self.client.get(reverse("catalog:collection-detail", args=[small.slug]))
        with CaptureQueriesContext(connection) as large_queries:
            resp_large = self.client.get(reverse("catalog:collection-detail", args=[large.slug]))

        self.assertEqual(resp_small.status_code, 200)
        self.assertEqual(resp_large.status_code, 200)
        self.assertEqual(
            len(small_queries.captured_queries), len(large_queries.captured_queries),
            "تعداد کوئری با تعداد کالای کالکشن رشد کرده — احتمال N+1",
        )
