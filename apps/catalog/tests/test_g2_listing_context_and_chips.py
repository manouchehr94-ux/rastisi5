"""G2 (Golden — Search + Category + Listing) behavior tests.

Covers the three G2 gaps closed on top of the already-complete unified
``catalog:product-list`` view (see
``docs/superpowers/plans/2026-09-04-golden-reference-storefront-g2-plan.md``):

- G2-a: dynamic location context — a query/category/brand-aware page heading and
  breadcrumb trail (instead of the old static "خانه › فروشگاه" + no <h1>).
- G2-b: visible, removable active-filter chips with per-filter "remove one" links
  (server/query canonical) plus the existing clear-all.

These assert behavior on the real view/context, tenant-scoped, not markup trivia.
"""

from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from apps.catalog.models import Brand, Category, Product, Vendor
from apps.stores.models import Store


def _akhlaghi():
    return Store.objects.get(slug="akhlaghi")


class G2ListingContextTests(TestCase):
    def setUp(self):
        self.store = _akhlaghi()
        self.top = Category.objects.create(store=self.store, name="کفش", slug="g2-shoes", icon="👟")
        self.sub = Category.objects.create(
            store=self.store, name="کتانی رانینگ", slug="g2-running", icon="🏃", parent=self.top
        )
        self.vendor = Vendor.objects.create(store=self.store, name="فروشگاه", slug="g2-shop")
        self.brand = Brand.objects.create(store=self.store, name="نایک", slug="g2-nike")
        self.p1 = Product.objects.create(
            store=self.store, vendor=self.vendor, category=self.sub, brand=self.brand,
            name="کتانی دونده", slug="g2-runner", sku="G2-1",
            price=Decimal("2000000"), discount_percent=10, sold_count=5, rating=Decimal("4.2"),
        )

    def _ctx(self, params=None):
        response = self.client.get(reverse("catalog:product-list"), params or {})
        self.assertEqual(response.status_code, 200)
        return response

    # -------------------------------------------------- G2-a heading/breadcrumb

    def test_plain_listing_has_a_page_heading(self):
        r = self._ctx()
        self.assertTrue(r.context.get("listing_heading"), "expected a listing_heading in context")
        # A breadcrumb trail exists (list of {label,url?} items), starting at home.
        crumbs = r.context.get("listing_breadcrumbs")
        self.assertTrue(crumbs and len(crumbs) >= 1)

    def test_category_heading_and_breadcrumb_reflect_the_selected_category(self):
        r = self._ctx({"category": "g2-running"})
        self.assertEqual(r.context["listing_heading"], "کتانی رانینگ")
        labels = [c["label"] for c in r.context["listing_breadcrumbs"]]
        # parent -> child trail present
        self.assertIn("کفش", labels)
        self.assertIn("کتانی رانینگ", labels)
        self.assertContains(r, "کتانی رانینگ")

    def test_search_heading_reflects_the_persian_query(self):
        r = self._ctx({"q": "کتانی"})
        self.assertIn("کتانی", r.context["listing_heading"])
        self.assertContains(r, "کتانی")

    def test_brand_filter_heading_reflects_brand(self):
        r = self._ctx({"brand": "g2-nike"})
        self.assertIn("نایک", r.context["listing_heading"])

    # -------------------------------------------------- G2-b active-filter chips

    def test_no_chips_on_a_plain_listing(self):
        r = self._ctx()
        self.assertEqual(list(r.context.get("active_filter_chips", [])), [])

    def test_active_chips_render_for_each_active_filter(self):
        r = self._ctx({"category": "g2-running", "brand": "g2-nike", "discounted": "1"})
        chips = r.context["active_filter_chips"]
        kinds = {c["kind"] for c in chips}
        self.assertIn("category", kinds)
        self.assertIn("brand", kinds)
        self.assertIn("discounted", kinds)
        # every chip has a human label and a remove URL
        for c in chips:
            self.assertTrue(c["label"])
            self.assertIn("remove_url", c)

    def test_remove_one_chip_drops_only_that_param_and_keeps_the_rest(self):
        r = self._ctx({"category": "g2-running", "brand": "g2-nike"})
        chips = {c["kind"]: c for c in r.context["active_filter_chips"]}
        brand_remove = chips["brand"]["remove_url"]
        # removing brand keeps category, drops brand
        self.assertIn("category=g2-running", brand_remove)
        self.assertNotIn("brand=g2-nike", brand_remove)

    def test_price_chip_present_when_price_filter_active(self):
        r = self._ctx({"min_price": "100000", "max_price": "5000000"})
        kinds = {c["kind"] for c in r.context["active_filter_chips"]}
        self.assertIn("price", kinds)

    def test_search_chip_present_and_removable(self):
        r = self._ctx({"q": "کتانی"})
        chips = {c["kind"]: c for c in r.context["active_filter_chips"]}
        self.assertIn("q", chips)
        self.assertNotIn("q=", chips["q"]["remove_url"])

    def test_clear_all_url_is_the_bare_listing(self):
        r = self._ctx({"category": "g2-running", "brand": "g2-nike"})
        self.assertEqual(r.context.get("clear_all_url"), reverse("catalog:product-list"))

    # -------------------------------------------------- tenant isolation

    def test_context_is_tenant_scoped(self):
        # Tested at the service boundary (build_product_listing_context) rather
        # than the HTTP path, because the dev store-resolution fallback requires
        # exactly one Store to exist. A category slug owned by ANOTHER store must
        # never resolve to a heading/breadcrumb when building context for THIS
        # store.
        from django.test import RequestFactory

        from apps.catalog.views import build_product_listing_context

        other = Store.objects.create(name="دیگر", slug="g2-other-store", status=Store.Status.SUSPENDED)
        Category.objects.create(store=other, name="خارجی", slug="g2-foreign", icon="❌")

        request = RequestFactory().get(reverse("catalog:product-list"), {"category": "g2-foreign"})
        ctx = build_product_listing_context(request, self.store)
        # Foreign slug does not resolve -> falls back to the generic heading,
        # never the other store's category name; and no category chip is emitted.
        self.assertNotEqual(ctx["listing_heading"], "خارجی")
        self.assertEqual(ctx["listing_heading"], "همه‌ی محصولات")
        self.assertNotIn("category", {c["kind"] for c in ctx["active_filter_chips"]})
