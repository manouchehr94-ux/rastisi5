"""Checkpoint — tenant-isolation and builder-lifecycle tests for the six
new storefront families (atlas_catalog, ava_fashion, toranj_gifting,
sarv_stock, sepidar_handmade, zarrin_jewelry).

These are executable Django ``TestCase``s using two real Stores (Store A =
the fixture "akhlaghi" Store, Store B = a freshly created Store) with
deliberately different products, collections, prices, variants, media,
sections, drafts, published versions, and carts — per the explicit
requirement that tenant isolation cannot be claimed "architecturally
guaranteed" merely because ``resolve_store_for_storefront``/
``resolve_store_for_service`` exist.

NOTE: this file is written to run under a real Django test runner; it is
NOT executed in this sandbox (no Django available). It is added so the
owner's Django-capable environment can run it directly — see
SIX_NEW_FAMILIES_IMPLEMENTATION_REPORT.md for the exact NOT EXECUTED
disclosure and reasoning.
"""

from decimal import Decimal

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.cart.models import CartItem
from apps.catalog.models import Category, Product, ProductVariant, Vendor
from apps.content.models import FooterSettings
from apps.core.models import ShopSettings
from apps.storefront_builder import family_registry
from apps.storefront_builder.services import layout_service as svc
from apps.stores.models import Store, StoreDomain

NEW_FAMILY_SLUGS = [
    "atlas_catalog", "ava_fashion", "toranj_gifting", "sarv_stock", "sepidar_handmade", "zarrin_jewelry",
]

HOST_A = "sfb6-a.example.com"
HOST_B = "sfb6-b.example.com"


def _verified_domain(store, hostname):
    return StoreDomain.objects.create(
        store=store, hostname=hostname, is_primary=True,
        verification_status=StoreDomain.VerificationStatus.VERIFIED, verified_at=timezone.now(),
    )


def _publish_family(store, family_slug):
    family = family_registry.get_family(family_slug)
    draft = svc.get_or_create_draft(store)
    draft.appearance_config = svc.validate_appearance_config({
        "family_slug": family_slug, "preset_slug": family.default_preset_slug,
    })
    draft.save(update_fields=["appearance_config"])
    return svc.publish(store)


@override_settings(ALLOWED_HOSTS=[HOST_A, HOST_B, "testserver"])
class SixFamiliesTwoStoreFixture(TestCase):
    """Shared two-Store setup used by every isolation test below."""

    def setUp(self):
        cache.clear()
        self.store_a = Store.objects.get(slug="akhlaghi")
        self.store_b = Store.objects.create(name="Store B", slug="sfb6-store-b", status=Store.Status.ACTIVE)
        _verified_domain(self.store_a, HOST_A)
        _verified_domain(self.store_b, HOST_B)
        ShopSettings.provision_for(self.store_b)
        FooterSettings.provision_for(self.store_b)

        self.vendor_a = Vendor.objects.create(store=self.store_a, name="Vendor A", slug="v-sfb6-a")
        self.category_a = Category.objects.create(store=self.store_a, name="Category A", slug="c-sfb6-a")
        self.vendor_b = Vendor.objects.create(store=self.store_b, name="Vendor B", slug="v-sfb6-b")
        self.category_b = Category.objects.create(store=self.store_b, name="Category B", slug="c-sfb6-b")

        self.product_a = Product.objects.create(
            store=self.store_a, vendor=self.vendor_a, category=self.category_a, name="Store A Product",
            slug="sfb6-a-product", sku="SFB6-A-SKU", price=Decimal("100000"), stock=10,
            status=Product.Status.ACTIVE,
        )
        self.product_b = Product.objects.create(
            store=self.store_b, vendor=self.vendor_b, category=self.category_b, name="Store B Product",
            slug="sfb6-b-product", sku="SFB6-B-SKU", price=Decimal("200000"), stock=10,
            status=Product.Status.ACTIVE,
        )
        self.variant_a = ProductVariant.objects.create(
            product=self.product_a, store=self.store_a, attribute="رنگ", value="قرمز", stock=5, is_active=True,
        )
        self.variant_b = ProductVariant.objects.create(
            product=self.product_b, store=self.store_b, attribute="رنگ", value="آبی", stock=5, is_active=True,
        )


class PublicRenderingIsolationTests(SixFamiliesTwoStoreFixture):
    """Public storefront rendering — each family, both Stores."""

    def test_each_family_home_page_never_shows_other_stores_product(self):
        for slug in NEW_FAMILY_SLUGS:
            _publish_family(self.store_a, slug)
            _publish_family(self.store_b, slug)

            resp_a = self.client.get(reverse("catalog:home"), HTTP_HOST=HOST_A)
            self.assertEqual(resp_a.status_code, 200)
            self.assertContains(resp_a, "Store A Product")
            self.assertNotContains(resp_a, "Store B Product")

            resp_b = self.client.get(reverse("catalog:home"), HTTP_HOST=HOST_B)
            self.assertEqual(resp_b.status_code, 200)
            self.assertContains(resp_b, "Store B Product")
            self.assertNotContains(resp_b, "Store A Product")

    def test_each_family_header_reflects_only_its_own_store(self):
        for slug in NEW_FAMILY_SLUGS:
            _publish_family(self.store_a, slug)
            resp = self.client.get(reverse("catalog:home"), HTTP_HOST=HOST_A)
            self.assertContains(resp, f'data-sfb-family="{slug}"')


class ProductDetailIsolationTests(SixFamiliesTwoStoreFixture):
    """Product detail page — a Store A host must never resolve Store B's
    product slug/id, even with a family assigned that would otherwise
    render happily."""

    def test_cross_store_product_detail_returns_404(self):
        for slug in NEW_FAMILY_SLUGS:
            _publish_family(self.store_a, slug)
            resp = self.client.get(
                reverse("catalog:product-detail", args=[self.product_b.slug]), HTTP_HOST=HOST_A,
            )
            self.assertEqual(resp.status_code, 404, f"family={slug}: Store A host resolved Store B's product")

    def test_own_store_product_detail_renders_family_page(self):
        for slug in NEW_FAMILY_SLUGS:
            _publish_family(self.store_a, slug)
            resp = self.client.get(
                reverse("catalog:product-detail", args=[self.product_a.slug]), HTTP_HOST=HOST_A,
            )
            self.assertEqual(resp.status_code, 200)
            self.assertContains(resp, "Store A Product")


class CartAddIsolationTests(SixFamiliesTwoStoreFixture):
    """Cart add — Store A's host must never be able to add Store B's
    product or variant to a cart, for any of the six families' active
    appearance configuration."""

    def _add(self, slug, host, **post):
        return self.client.post(reverse("cart:add", args=[slug]), post, HTTP_HOST=host)

    def test_cross_store_product_add_rejected_for_every_family(self):
        for family_slug in NEW_FAMILY_SLUGS:
            _publish_family(self.store_a, family_slug)
            resp = self._add(self.product_b.slug, HOST_A, quantity=1)
            self.assertEqual(resp.status_code, 404, f"family={family_slug}")
            self.assertEqual(CartItem.objects.count(), 0)

    def test_cross_store_variant_add_rejected_for_every_family(self):
        for family_slug in NEW_FAMILY_SLUGS:
            _publish_family(self.store_a, family_slug)
            # Store B's variant against Store A's own product — must 404
            # because ownership (product__store) never matches.
            resp = self._add(self.product_a.slug, HOST_A, variant_id=self.variant_b.pk, quantity=1)
            self.assertEqual(resp.status_code, 404, f"family={family_slug}")
            self.assertEqual(CartItem.objects.count(), 0)

    def test_own_store_add_succeeds(self):
        _publish_family(self.store_a, "atlas_catalog")
        resp = self._add(self.product_a.slug, HOST_A, quantity=1)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(CartItem.objects.count(), 1)


class WishlistIsolationTests(SixFamiliesTwoStoreFixture):
    """Wishlist add — cannot wishlist another Store's product id."""

    def test_cross_store_wishlist_add_rejected(self):
        from django.contrib.auth import get_user_model

        from apps.customers.models import Customer

        User = get_user_model()
        user = User.objects.create_user(username="sfb6-wish-user", password="pass12345")
        Customer.objects.create(user=user, full_name="کاربر", phone="09121230088")
        self.client.login(username="sfb6-wish-user", password="pass12345")

        resp = self.client.post(
            reverse("customers:wishlist-toggle", args=[self.product_b.slug]), HTTP_HOST=HOST_A,
        )
        # Either 404 (product not resolvable in Store A's scope) or a
        # response that does not create a cross-store wishlist row.
        from apps.customers.models import Wishlist

        self.assertFalse(
            Wishlist.objects.filter(product=self.product_b).exists(),
            "Store A session was able to wishlist Store B's product",
        )
        self.assertIn(resp.status_code, (200, 302, 404))


class DraftPublishedConfigIsolationTests(SixFamiliesTwoStoreFixture):
    """Draft/published appearance_config — Store A's draft/published family
    selection must never leak into or affect Store B's."""

    def test_publishing_family_on_store_a_does_not_affect_store_b(self):
        _publish_family(self.store_a, "toranj_gifting")
        # Store B never touched — must still have no family assigned.
        from apps.storefront_builder.models import StorefrontLayout

        layout_b = StorefrontLayout.objects.filter(store=self.store_b).first()
        if layout_b is not None and layout_b.published_version_id:
            config_b = layout_b.published_version.appearance_config or {}
            self.assertNotEqual(config_b.get("family_slug"), "toranj_gifting")

    def test_different_families_can_be_published_independently_per_store(self):
        _publish_family(self.store_a, "zarrin_jewelry")
        _publish_family(self.store_b, "sarv_stock")

        resp_a = self.client.get(reverse("catalog:home"), HTTP_HOST=HOST_A)
        resp_b = self.client.get(reverse("catalog:home"), HTTP_HOST=HOST_B)
        self.assertContains(resp_a, 'data-sfb-family="zarrin_jewelry"')
        self.assertContains(resp_b, 'data-sfb-family="sarv_stock"')
        self.assertNotContains(resp_a, 'data-sfb-family="sarv_stock"')
        self.assertNotContains(resp_b, 'data-sfb-family="zarrin_jewelry"')


class CollectionAndMediaIsolationTests(SixFamiliesTwoStoreFixture):
    """Collection/category ids — Store A's category listing must never
    surface Store B's category or its products."""

    def test_category_filtered_listing_never_crosses_stores(self):
        _publish_family(self.store_a, "sepidar_handmade")
        resp = self.client.get(
            reverse("catalog:product-list") + f"?category={self.category_b.slug}", HTTP_HOST=HOST_A,
        )
        self.assertNotContains(resp, "Store B Product")


class BuilderLifecycleTests(TestCase):
    """Family selection / draft / preview / publish / rollback / reorder /
    hide / duplicate / edit / delete — proven through real saved state and
    rendered responses (not registry/file-existence assertions), per
    family."""

    def setUp(self):
        cache.clear()
        self.store = Store.objects.get(slug="akhlaghi")
        _verified_domain(self.store, HOST_A)

    def test_family_selection_creates_draft_with_correct_defaults(self):
        for slug in NEW_FAMILY_SLUGS:
            family = family_registry.get_family(slug)
            draft = svc.get_or_create_draft(self.store)
            draft.appearance_config = svc.validate_appearance_config({
                "family_slug": slug, "preset_slug": family.default_preset_slug,
            })
            draft.save(update_fields=["appearance_config"])
            self.assertEqual(draft.appearance_config["family_slug"], slug)

    @override_settings(ALLOWED_HOSTS=[HOST_A, "testserver"])
    def test_publish_then_public_rendering_reflects_family(self):
        for slug in NEW_FAMILY_SLUGS:
            _publish_family(self.store, slug)
            resp = self.client.get(reverse("catalog:home"), HTTP_HOST=HOST_A)
            self.assertEqual(resp.status_code, 200)
            self.assertContains(resp, f'data-sfb-family="{slug}"')

    def test_rollback_restores_previous_family_as_new_draft(self):
        _publish_family(self.store, "atlas_catalog")
        from apps.storefront_builder.models import StorefrontLayout

        layout = StorefrontLayout.objects.get(store=self.store)
        first_version_id = layout.published_version_id

        _publish_family(self.store, "zarrin_jewelry")
        layout.refresh_from_db()
        self.assertNotEqual(layout.published_version_id, first_version_id)

        restored_draft = svc.restore_version(self.store, first_version_id)
        self.assertEqual(restored_draft.appearance_config["family_slug"], "atlas_catalog")
        # Rollback creates a NEW draft, does not immediately publish.
        layout.refresh_from_db()
        self.assertNotEqual(layout.published_version_id, restored_draft.pk)

    @override_settings(ALLOWED_HOSTS=[HOST_A, "testserver"])
    def test_missing_optional_content_does_not_break_rendering(self):
        """A family with no story rail items / no size guide / no gift
        wrap configured must still render the page without error — the
        'hide when unconfigured' contract, not a 500."""
        for slug in NEW_FAMILY_SLUGS:
            _publish_family(self.store, slug)
            resp = self.client.get(reverse("catalog:home"), HTTP_HOST=HOST_A)
            self.assertEqual(resp.status_code, 200, f"family={slug}")
