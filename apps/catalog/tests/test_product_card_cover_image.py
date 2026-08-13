import shutil
import tempfile
from decimal import Decimal
from io import BytesIO

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from PIL import Image

from apps.catalog.models import Category, Product, Vendor
from apps.catalog.services.product_image_service import add_product_image
from apps.stores.models import Store


def _akhlaghi():
    return Store.objects.get(slug="akhlaghi")


def _make_image_file(name="photo.jpg"):
    buffer = BytesIO()
    Image.new("RGB", (400, 400), "#0000ff").save(buffer, format="JPEG")
    return SimpleUploadedFile(name, buffer.getvalue(), content_type="image/jpeg")


@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class ProductCoverImageTestCase(TestCase):
    @classmethod
    def tearDownClass(cls):
        from django.conf import settings

        shutil.rmtree(settings.MEDIA_ROOT, ignore_errors=True)
        super().tearDownClass()

    def setUp(self):
        self.store = _akhlaghi()
        self.vendor = Vendor.objects.create(store=self.store, name="فروشگاه", slug="shop-cover")
        self.category = Category.objects.create(store=self.store, name="دسته", slug="cat-cover")
        self.product = Product.objects.create(
            store=self.store, vendor=self.vendor, category=self.category, name="کالای کاور", slug="cover-product",
            sku="SKU-COVER1", price=Decimal("150000"), icon="🧸", tint="#fde68a", status=Product.Status.ACTIVE,
        )


class ProductCoverImagePropertyTests(ProductCoverImageTestCase):
    def test_no_images_returns_none(self):
        self.assertIsNone(self.product.cover_image)

    def test_first_image_is_cover_by_default(self):
        image = add_product_image(self.product, _make_image_file())
        self.assertEqual(self.product.cover_image, image)

    def test_cover_image_wins_over_creation_order(self):
        add_product_image(self.product, _make_image_file("1.jpg"))
        second = add_product_image(self.product, _make_image_file("2.jpg"))
        from apps.catalog.services.product_image_service import set_cover_image

        set_cover_image(self.product, second.pk)
        self.product = Product.objects.get(pk=self.product.pk)
        self.assertEqual(self.product.cover_image.pk, second.pk)


class ProductCardCoverImageRenderTests(ProductCoverImageTestCase):
    def test_card_shows_icon_fallback_without_images(self):
        response = self.client.get(reverse("catalog:product-list"), {"q": "کاور"})
        self.assertContains(response, "🧸")
        self.assertNotContains(response, "cover-photo")

    def test_card_shows_real_photo_when_image_exists(self):
        image = add_product_image(self.product, _make_image_file())
        response = self.client.get(reverse("catalog:product-list"), {"q": "کاور"})
        self.assertContains(response, "cover-photo")
        self.assertContains(response, image.thumbnail.url)


class ProductCardSecondaryImageRenderTests(ProductCoverImageTestCase):
    """Phase 8 P1 — تصویرِ دومِ کارت (crossfade هنگامِ hover)، از
    ``Product.secondary_image`` که از قبل موجود بود اما هرگز به
    ``product_card.html`` وصل نشده بود (کلاسِ CSSِ هدف، ``.mf-card-img-2``،
    توسطِ هیچ templateی امروز نوشته نمی‌شد)."""

    def test_single_image_product_has_no_secondary_photo(self):
        add_product_image(self.product, _make_image_file())
        response = self.client.get(reverse("catalog:product-list"), {"q": "کاور"})
        self.assertNotContains(response, "cover-photo-2")

    def test_second_image_renders_as_secondary_photo(self):
        add_product_image(self.product, _make_image_file("1.jpg"))
        second = add_product_image(self.product, _make_image_file("2.jpg"))
        response = self.client.get(reverse("catalog:product-list"), {"q": "کاور"})
        self.assertContains(response, "cover-photo-2")
        self.assertContains(response, second.thumbnail.url)
