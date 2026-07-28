import shutil
import tempfile
from decimal import Decimal
from io import BytesIO

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from PIL import Image

from django.utils import timezone

from apps.catalog.models import Category, Product, ProductImage, Vendor
from apps.catalog.services.product_image_service import add_product_image
from apps.stores.models import Store, StoreMembership

User = get_user_model()


def _make_image_file(name="photo.jpg", color="#00ff00"):
    buffer = BytesIO()
    Image.new("RGB", (400, 400), color).save(buffer, format="JPEG")
    return SimpleUploadedFile(name, buffer.getvalue(), content_type="image/jpeg")


@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class ProductImageViewsTestCase(TestCase):
    @classmethod
    def tearDownClass(cls):
        from django.conf import settings

        shutil.rmtree(settings.MEDIA_ROOT, ignore_errors=True)
        super().tearDownClass()

    def setUp(self):
        self.store = Store.objects.get(slug="akhlaghi")
        self.vendor = Vendor.objects.create(store=self.store, name="فروشگاه", slug="shop-piv")
        self.category = Category.objects.create(store=self.store, name="دسته", slug="cat-piv")
        self.product = Product.objects.create(
            store=self.store, vendor=self.vendor, category=self.category, name="کالای تصویری", slug="piv-product",
            sku="SKU-PIV1", price=Decimal("500000"), stock=5,
        )
        self.staff = User.objects.create_user(username="09121133001", password="pass12345", is_staff=True)
        StoreMembership.objects.create(
            store=self.store, user=self.staff, role=StoreMembership.Role.OWNER,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )
        self.client.login(username="09121133001", password="pass12345")


class ProductImagesModalViewTests(ProductImageViewsTestCase):
    def test_get_renders_modal_with_empty_state(self):
        response = self.client.get(reverse("dashboard:product-images", args=[self.product.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "مدیریت تصاویر")
        self.assertContains(response, "هنوز تصویری برای این کالا اضافه نشده است")

    def test_anonymous_denied(self):
        self.client.logout()
        response = self.client.get(reverse("dashboard:product-images", args=[self.product.pk]))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin-panel/login/", response.url)


class ProductImageUploadViewTests(ProductImageViewsTestCase):
    def test_uploading_single_image_creates_row(self):
        response = self.client.post(
            reverse("dashboard:product-image-upload", args=[self.product.pk]),
            {"images": [_make_image_file()]},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.product.images.count(), 1)

    def test_uploading_multiple_images_creates_multiple_rows(self):
        self.client.post(
            reverse("dashboard:product-image-upload", args=[self.product.pk]),
            {"images": [_make_image_file("a.jpg"), _make_image_file("b.jpg")]},
        )
        self.assertEqual(self.product.images.count(), 2)

    def test_first_uploaded_image_is_cover(self):
        self.client.post(
            reverse("dashboard:product-image-upload", args=[self.product.pk]),
            {"images": [_make_image_file()]},
        )
        image = self.product.images.first()
        self.assertTrue(image.is_cover)

    def test_invalid_extension_rejected_with_clear_error(self):
        bad_file = SimpleUploadedFile("doc.txt", b"hello", content_type="text/plain")
        response = self.client.post(
            reverse("dashboard:product-image-upload", args=[self.product.pk]),
            {"images": [bad_file]},
        )
        self.assertEqual(self.product.images.count(), 0)
        self.assertContains(response, "هنوز تصویری برای این کالا اضافه نشده است")

    def test_no_file_selected_does_not_create_image(self):
        response = self.client.post(reverse("dashboard:product-image-upload", args=[self.product.pk]), {})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.product.images.count(), 0)

    def test_upload_refreshes_products_table_thumb_via_oob(self):
        response = self.client.post(
            reverse("dashboard:product-image-upload", args=[self.product.pk]),
            {"images": [_make_image_file()]},
        )
        self.assertContains(response, 'id="productsTableWrap"')

    def test_anonymous_denied(self):
        self.client.logout()
        response = self.client.post(
            reverse("dashboard:product-image-upload", args=[self.product.pk]),
            {"images": [_make_image_file()]},
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin-panel/login/", response.url)
        self.assertEqual(self.product.images.count(), 0)


class ProductImageDeleteViewTests(ProductImageViewsTestCase):
    def test_deletes_image(self):
        image = add_product_image(self.product, _make_image_file())
        response = self.client.post(
            reverse("dashboard:product-image-delete", args=[self.product.pk, image.pk])
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(ProductImage.objects.filter(pk=image.pk).exists())

    def test_deleting_cover_promotes_next(self):
        first = add_product_image(self.product, _make_image_file("1.jpg"))
        second = add_product_image(self.product, _make_image_file("2.jpg"))
        self.client.post(reverse("dashboard:product-image-delete", args=[self.product.pk, first.pk]))
        second.refresh_from_db()
        self.assertTrue(second.is_cover)

    def test_get_not_allowed(self):
        image = add_product_image(self.product, _make_image_file())
        response = self.client.get(
            reverse("dashboard:product-image-delete", args=[self.product.pk, image.pk])
        )
        self.assertEqual(response.status_code, 405)


class ProductImageSetCoverViewTests(ProductImageViewsTestCase):
    def test_sets_cover_exclusively(self):
        first = add_product_image(self.product, _make_image_file("1.jpg"))
        second = add_product_image(self.product, _make_image_file("2.jpg"))
        self.client.post(reverse("dashboard:product-image-set-cover", args=[self.product.pk, second.pk]))
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertFalse(first.is_cover)
        self.assertTrue(second.is_cover)


class ProductImageMoveViewTests(ProductImageViewsTestCase):
    def test_move_up_swaps_order(self):
        first = add_product_image(self.product, _make_image_file("1.jpg"))
        second = add_product_image(self.product, _make_image_file("2.jpg"))
        self.client.post(
            reverse("dashboard:product-image-move", args=[self.product.pk, second.pk]),
            {"direction": "up"},
        )
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertEqual(second.order, 0)
        self.assertEqual(first.order, 1)

    def test_invalid_direction_is_noop(self):
        image = add_product_image(self.product, _make_image_file())
        response = self.client.post(
            reverse("dashboard:product-image-move", args=[self.product.pk, image.pk]),
            {"direction": "sideways"},
        )
        self.assertEqual(response.status_code, 200)
        image.refresh_from_db()
        self.assertEqual(image.order, 0)


class ProductImageAltUpdateViewTests(ProductImageViewsTestCase):
    def test_updates_alt_text(self):
        image = add_product_image(self.product, _make_image_file())
        self.client.post(
            reverse("dashboard:product-image-alt", args=[self.product.pk, image.pk]),
            {"alt": "توضیح جدید تصویر"},
        )
        image.refresh_from_db()
        self.assertEqual(image.alt, "توضیح جدید تصویر")
