"""Dashboard catalog cross-Store adversarial tests — real two-Store isolation.

Uses two real ``Store`` rows, each with its own real, verified
``StoreDomain``, and distinct ``Host`` headers on real HTTP requests through
``apps.stores.resolution.resolve_store_for_service`` (the same authoritative
resolver the dashboard's ``_resolve_dashboard_store`` delegates to). No
``request.store`` mocking. Proves every catalog dashboard endpoint denies
cross-Store view/edit/delete/toggle/media/variant operations, and that
crafted POSTs cannot attach another Store's relation objects.
"""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.catalog.models import Brand, Category, Product, ProductImage, ProductVariant, Vendor
from apps.catalog.services.variant_service import create_variant, set_product_type
from apps.content.models import FooterSettings
from apps.core.models import ShopSettings
from apps.stores.models import Store, StoreDomain

User = get_user_model()

HOST_A = "dash-a.example.com"
HOST_B = "dash-b.example.com"


def _verified_domain(store, hostname):
    return StoreDomain.objects.create(
        store=store,
        hostname=hostname,
        is_primary=True,
        verification_status=StoreDomain.VerificationStatus.VERIFIED,
        verified_at=timezone.now(),
    )


@override_settings(ALLOWED_HOSTS=[HOST_A, HOST_B, "testserver"])
class DashboardCatalogTwoStoreIsolationTests(TestCase):
    def setUp(self):
        self.store_a = Store.objects.get(slug="akhlaghi")
        self.store_b = Store.objects.create(name="Store B", slug="dash-store-b", status=Store.Status.ACTIVE)
        _verified_domain(self.store_a, HOST_A)
        _verified_domain(self.store_b, HOST_B)
        ShopSettings.provision_for(self.store_b)
        FooterSettings.provision_for(self.store_b)

        self.staff = User.objects.create_user(username="dash-staff", password="pass12345", is_staff=True)
        self.client.login(username="dash-staff", password="pass12345")

        self.vendor_a = Vendor.objects.create(store=self.store_a, name="Vendor A", slug="vendor-dsi-a")
        self.category_a = Category.objects.create(store=self.store_a, name="Cat A", slug="cat-dsi-a")
        self.brand_a = Brand.objects.create(store=self.store_a, name="Brand A", slug="brand-dsi-a")
        self.product_a = Product.objects.create(
            store=self.store_a, vendor=self.vendor_a, category=self.category_a, brand=self.brand_a,
            name="Product A", slug="product-dsi-a", sku="SKU-DSI-A", price=Decimal("100000"),
        )
        self.variant_a = create_variant(self.product_a, attribute="رنگ", value="قرمز")

        self.vendor_b = Vendor.objects.create(store=self.store_b, name="Vendor B", slug="vendor-dsi-b")
        self.category_b = Category.objects.create(store=self.store_b, name="Cat B", slug="cat-dsi-b")
        self.brand_b = Brand.objects.create(store=self.store_b, name="Brand B", slug="brand-dsi-b")
        self.product_b = Product.objects.create(
            store=self.store_b, vendor=self.vendor_b, category=self.category_b, brand=self.brand_b,
            name="Product B", slug="product-dsi-b", sku="SKU-DSI-B", price=Decimal("200000"),
        )
        self.variant_b = create_variant(self.product_b, attribute="رنگ", value="آبی")

    def _get(self, url_name, *args):
        return self.client.get(reverse(f"dashboard:{url_name}", args=args), HTTP_HOST=HOST_B)

    def _post(self, url_name, *args, data=None):
        return self.client.post(reverse(f"dashboard:{url_name}", args=args), data or {}, HTTP_HOST=HOST_B)

    # ------------------------------------------------------------ product list scoping

    def test_product_list_excludes_other_store_product(self):
        response = self.client.get(reverse("dashboard:product-list"), HTTP_HOST=HOST_B)
        self.assertContains(response, "Product B")
        self.assertNotContains(response, "Product A")

    # ------------------------------------------------------------ product view/edit/delete

    def test_product_edit_get_cross_store_returns_404(self):
        response = self._get("product-edit", self.product_a.pk)
        self.assertEqual(response.status_code, 404)

    def test_product_edit_post_cross_store_returns_404_and_does_not_mutate(self):
        response = self._post("product-edit", self.product_a.pk, data={
            "name": "Hacked Name", "sku": self.product_a.sku, "category": self.category_a.id,
            "price": "999", "discount_percent": "0", "stock": "0", "status": "active",
            "icon": "", "description": "",
        })
        self.assertEqual(response.status_code, 404)
        self.product_a.refresh_from_db()
        self.assertEqual(self.product_a.name, "Product A")

    def test_product_delete_cross_store_returns_404_and_does_not_delete(self):
        response = self._post("product-delete", self.product_a.pk)
        self.assertEqual(response.status_code, 404)
        self.assertTrue(Product.objects.filter(pk=self.product_a.pk).exists())

    # ------------------------------------------------------------ crafted POST: relation from another Store

    def test_product_create_with_other_stores_category_id_rejected(self):
        """POSTing a real category PK that belongs to another Store must be rejected —
        not silently attached, and not a 500."""
        response = self.client.post(reverse("dashboard:product-add"), {
            "name": "Cross Store Product", "sku": "SKU-CROSS-1", "category": self.category_a.id,
            "price": "50000", "discount_percent": "0", "stock": "0", "status": "active",
            "icon": "", "description": "",
        }, HTTP_HOST=HOST_B)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Product.objects.filter(sku="SKU-CROSS-1").exists())

    def test_product_edit_with_other_stores_category_id_rejected(self):
        response = self._post("product-edit", self.product_b.pk, data={
            "name": self.product_b.name, "sku": self.product_b.sku, "category": self.category_a.id,
            "price": "200000", "discount_percent": "0", "stock": "0", "status": "active",
            "icon": "", "description": "",
        })
        self.assertEqual(response.status_code, 200)
        self.product_b.refresh_from_db()
        self.assertEqual(self.product_b.category_id, self.category_b.pk)

    def test_category_add_sub_with_other_stores_parent_rejected(self):
        response = self._post("category-add-sub", data={
            "parent": self.category_a.id, "name": "Sneaky Sub", "icon": "",
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Category.objects.filter(name="Sneaky Sub").exists())

    # ------------------------------------------------------------ category view/edit/delete

    def test_category_edit_get_cross_store_returns_404(self):
        response = self._get("category-edit", self.category_a.pk)
        self.assertEqual(response.status_code, 404)

    def test_category_delete_cross_store_returns_404_and_does_not_delete(self):
        response = self._post("category-delete", self.category_a.pk)
        self.assertEqual(response.status_code, 404)
        self.assertTrue(Category.objects.filter(pk=self.category_a.pk).exists())

    # ------------------------------------------------------------ product media

    def test_product_images_modal_cross_store_returns_404(self):
        response = self._get("product-images", self.product_a.pk)
        self.assertEqual(response.status_code, 404)

    def test_product_image_upload_cross_store_returns_404(self):
        response = self._post("product-image-upload", self.product_a.pk)
        self.assertEqual(response.status_code, 404)

    def test_product_image_delete_cross_store_returns_404(self):
        response = self._post("product-image-delete", self.product_a.pk, 1)
        self.assertEqual(response.status_code, 404)

    # ------------------------------------------------------------ product variants

    def test_product_variants_page_cross_store_returns_404(self):
        response = self._get("product-variants", self.product_a.pk)
        self.assertEqual(response.status_code, 404)

    def test_product_variant_bulk_add_cross_store_returns_404(self):
        response = self._post("product-variant-bulk-add", self.product_a.pk, data={
            "attribute": "رنگ", "raw_values": "سبز", "default_stock": "0", "default_extra_price": "0",
        })
        self.assertEqual(response.status_code, 404)
        self.assertEqual(self.product_a.variants.count(), 1)

    def test_product_variant_edit_cross_store_returns_404(self):
        response = self._get("product-variant-edit", self.product_a.pk, self.variant_a.pk)
        self.assertEqual(response.status_code, 404)

    def test_product_variant_toggle_cross_store_returns_404_and_does_not_mutate(self):
        response = self._post("product-variant-toggle", self.product_a.pk, self.variant_a.pk)
        self.assertEqual(response.status_code, 404)
        self.variant_a.refresh_from_db()
        self.assertTrue(self.variant_a.is_active)

    def test_product_variant_delete_cross_store_returns_404_and_does_not_delete(self):
        response = self._post("product-variant-delete", self.product_a.pk, self.variant_a.pk)
        self.assertEqual(response.status_code, 404)
        self.assertTrue(ProductVariant.objects.filter(pk=self.variant_a.pk).exists())

    def test_product_variant_move_cross_store_returns_404(self):
        response = self._post("product-variant-move", self.product_a.pk, self.variant_a.pk, data={"direction": "up"})
        self.assertEqual(response.status_code, 404)

    def test_variant_from_other_store_cannot_be_reached_even_through_own_product(self):
        """A variant that belongs to Store A's product cannot be operated on
        even when addressed via Store A's own product pk while browsing as Store B —
        the product itself is already unreachable, so the variant is unreachable too."""
        response = self._get("product-variant-edit", self.product_a.pk, self.variant_a.pk)
        self.assertEqual(response.status_code, 404)
        self.variant_a.refresh_from_db()
        self.assertEqual(self.variant_a.value, "قرمز")


@override_settings(ALLOWED_HOSTS=[HOST_A, HOST_B, "testserver"])
class DashboardProductMediaTwoStoreLifecycleTests(TestCase):
    """Step 14 — media isolation with a real uploaded ProductImage, not just
    a modal-open check: Store B must not be able to replace/delete/reorder/
    set-cover an image that belongs to a Store A product."""

    @classmethod
    def tearDownClass(cls):
        import shutil
        from django.conf import settings

        shutil.rmtree(settings.MEDIA_ROOT, ignore_errors=True)
        super().tearDownClass()

    def setUp(self):
        import tempfile
        from django.test import override_settings as _override

        self._media_override = _override(MEDIA_ROOT=tempfile.mkdtemp())
        self._media_override.enable()

        self.store_a = Store.objects.get(slug="akhlaghi")
        self.store_b = Store.objects.create(name="Store B", slug="dash-media-store-b", status=Store.Status.ACTIVE)
        _verified_domain(self.store_a, HOST_A)
        _verified_domain(self.store_b, HOST_B)
        ShopSettings.provision_for(self.store_b)
        FooterSettings.provision_for(self.store_b)

        self.staff = User.objects.create_user(username="dash-media-staff", password="pass12345", is_staff=True)
        self.client.login(username="dash-media-staff", password="pass12345")

        vendor_a = Vendor.objects.create(store=self.store_a, name="Vendor A", slug="vendor-media-a")
        category_a = Category.objects.create(store=self.store_a, name="Cat A", slug="cat-media-a")
        self.product_a = Product.objects.create(
            store=self.store_a, vendor=vendor_a, category=category_a,
            name="Media Product A", slug="media-product-a", sku="SKU-MEDIA-A", price=Decimal("100000"),
        )

        from apps.catalog.services.product_image_service import add_product_image
        from io import BytesIO
        from django.core.files.uploadedfile import SimpleUploadedFile
        from PIL import Image

        buf = BytesIO()
        Image.new("RGB", (400, 400), "#112233").save(buf, format="JPEG")
        file = SimpleUploadedFile("a.jpg", buf.getvalue(), content_type="image/jpeg")
        self.image_a = add_product_image(self.product_a, file, alt="Store A image")

    def tearDown(self):
        self._media_override.disable()
        super().tearDown()

    def test_cross_store_image_delete_returns_404_and_image_survives(self):
        response = self.client.post(
            reverse("dashboard:product-image-delete", args=[self.product_a.pk, self.image_a.pk]),
            HTTP_HOST=HOST_B,
        )
        self.assertEqual(response.status_code, 404)
        self.assertTrue(ProductImage.objects.filter(pk=self.image_a.pk).exists())

    def test_cross_store_image_set_cover_returns_404(self):
        response = self.client.post(
            reverse("dashboard:product-image-set-cover", args=[self.product_a.pk, self.image_a.pk]),
            HTTP_HOST=HOST_B,
        )
        self.assertEqual(response.status_code, 404)

    def test_cross_store_image_move_returns_404(self):
        response = self.client.post(
            reverse("dashboard:product-image-move", args=[self.product_a.pk, self.image_a.pk]),
            HTTP_HOST=HOST_B,
        )
        self.assertEqual(response.status_code, 404)

    def test_cross_store_image_alt_update_returns_404_and_alt_unchanged(self):
        response = self.client.post(
            reverse("dashboard:product-image-alt", args=[self.product_a.pk, self.image_a.pk]),
            {"alt": "hijacked"}, HTTP_HOST=HOST_B,
        )
        self.assertEqual(response.status_code, 404)
        self.image_a.refresh_from_db()
        self.assertEqual(self.image_a.alt, "Store A image")

    def test_own_store_image_delete_succeeds(self):
        response = self.client.post(
            reverse("dashboard:product-image-delete", args=[self.product_a.pk, self.image_a.pk]),
            HTTP_HOST=HOST_A,
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(ProductImage.objects.filter(pk=self.image_a.pk).exists())
