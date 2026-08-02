import shutil
import tempfile
from decimal import Decimal
from io import BytesIO

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from PIL import Image

from apps.catalog.models import Product, ProductImage, ProductVariant, Vendor
from apps.catalog.services.product_image_service import (
    MAX_DIMENSION,
    MAX_UPLOAD_SIZE_BYTES,
    THUMBNAIL_DIMENSION,
    ProductImageError,
    add_product_image,
    delete_product_image,
    move_product_image,
    set_cover_image,
    set_image_option_value,
    set_image_variant,
    update_image_alt,
    validate_image_file,
)
from apps.catalog.services.variant_engine_service import add_option_value, add_product_option
from apps.stores.models import Store


def _akhlaghi():
    return Store.objects.get(slug="akhlaghi")


def _make_image_file(name="photo.jpg", size=(800, 600), fmt="JPEG", color="#ff0000"):
    buffer = BytesIO()
    Image.new("RGB", size, color).save(buffer, format=fmt)
    content_type = {"JPEG": "image/jpeg", "PNG": "image/png", "WEBP": "image/webp"}[fmt]
    return SimpleUploadedFile(name, buffer.getvalue(), content_type=content_type)


@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class ProductImageServiceTestCase(TestCase):
    @classmethod
    def tearDownClass(cls):
        from django.conf import settings

        shutil.rmtree(settings.MEDIA_ROOT, ignore_errors=True)
        super().tearDownClass()

    def setUp(self):
        self.store = _akhlaghi()
        vendor = Vendor.objects.create(store=self.store, name="فروشگاه نمونه", slug="pi-shop")
        from apps.catalog.models import Category

        category = Category.objects.create(store=self.store, name="دسته", slug="pi-cat")
        self.product = Product.objects.create(
            store=self.store, vendor=vendor, category=category, name="کالای نمونه", slug="pi-product",
            sku="PI-SKU-1", price=Decimal("100000"),
        )


class ValidateImageFileTests(ProductImageServiceTestCase):
    def test_accepts_valid_jpg(self):
        validate_image_file(_make_image_file())

    def test_accepts_valid_png(self):
        validate_image_file(_make_image_file(name="a.png", fmt="PNG"))

    def test_accepts_valid_webp(self):
        validate_image_file(_make_image_file(name="a.webp", fmt="WEBP"))

    def test_rejects_disallowed_extension(self):
        file = SimpleUploadedFile("doc.pdf", b"%PDF-1.4", content_type="application/pdf")
        with self.assertRaises(ProductImageError) as ctx:
            validate_image_file(file)
        self.assertIn("فرمت", str(ctx.exception))

    def test_rejects_oversized_file(self):
        big_content = b"\x00" * (MAX_UPLOAD_SIZE_BYTES + 1)
        file = SimpleUploadedFile("big.jpg", big_content, content_type="image/jpeg")
        with self.assertRaises(ProductImageError) as ctx:
            validate_image_file(file)
        self.assertIn("۵ مگابایت", str(ctx.exception))

    def test_rejects_corrupt_file_disguised_as_image(self):
        file = SimpleUploadedFile("fake.jpg", b"this is not a real image", content_type="image/jpeg")
        with self.assertRaises(ProductImageError) as ctx:
            validate_image_file(file)
        self.assertIn("معتبر", str(ctx.exception))


class AddProductImageTests(ProductImageServiceTestCase):
    def test_creates_image_and_thumbnail(self):
        image = add_product_image(self.product, _make_image_file(), alt="عکس محصول")
        self.assertTrue(image.image.name)
        self.assertTrue(image.thumbnail.name)
        self.assertEqual(image.alt, "عکس محصول")

    def test_first_image_becomes_cover_automatically(self):
        image = add_product_image(self.product, _make_image_file())
        self.assertTrue(image.is_cover)

    def test_second_image_is_not_cover(self):
        add_product_image(self.product, _make_image_file(name="first.jpg"))
        second = add_product_image(self.product, _make_image_file(name="second.jpg"))
        self.assertFalse(second.is_cover)

    def test_order_is_sequential(self):
        first = add_product_image(self.product, _make_image_file(name="1.jpg"))
        second = add_product_image(self.product, _make_image_file(name="2.jpg"))
        self.assertEqual(first.order, 0)
        self.assertEqual(second.order, 1)

    def test_oversized_dimensions_are_shrunk(self):
        image = add_product_image(self.product, _make_image_file(name="huge.jpg", size=(3000, 2400)))
        with Image.open(image.image.path) as pil_image:
            self.assertLessEqual(pil_image.width, MAX_DIMENSION)
            self.assertLessEqual(pil_image.height, MAX_DIMENSION)

    def test_small_image_is_not_upscaled(self):
        image = add_product_image(self.product, _make_image_file(name="small.jpg", size=(300, 200)))
        with Image.open(image.image.path) as pil_image:
            self.assertEqual(pil_image.size, (300, 200))

    def test_thumbnail_is_within_thumbnail_dimension(self):
        image = add_product_image(self.product, _make_image_file(name="huge.jpg", size=(3000, 2400)))
        with Image.open(image.thumbnail.path) as pil_image:
            self.assertLessEqual(pil_image.width, THUMBNAIL_DIMENSION)
            self.assertLessEqual(pil_image.height, THUMBNAIL_DIMENSION)

    def test_invalid_file_raises_and_creates_no_row(self):
        bad = SimpleUploadedFile("bad.jpg", b"not an image", content_type="image/jpeg")
        with self.assertRaises(ProductImageError):
            add_product_image(self.product, bad)
        self.assertEqual(ProductImage.objects.count(), 0)


class DeleteProductImageTests(ProductImageServiceTestCase):
    def test_delete_removes_row(self):
        image = add_product_image(self.product, _make_image_file())
        delete_product_image(image)
        self.assertEqual(ProductImage.objects.count(), 0)

    def test_deleting_cover_promotes_next_image(self):
        first = add_product_image(self.product, _make_image_file(name="1.jpg"))
        second = add_product_image(self.product, _make_image_file(name="2.jpg"))
        self.assertTrue(first.is_cover)
        delete_product_image(first)
        second.refresh_from_db()
        self.assertTrue(second.is_cover)

    def test_deleting_last_image_leaves_no_cover(self):
        image = add_product_image(self.product, _make_image_file())
        delete_product_image(image)
        self.assertEqual(self.product.images.count(), 0)

    def test_deleting_non_cover_does_not_change_cover(self):
        first = add_product_image(self.product, _make_image_file(name="1.jpg"))
        second = add_product_image(self.product, _make_image_file(name="2.jpg"))
        delete_product_image(second)
        first.refresh_from_db()
        self.assertTrue(first.is_cover)


class SetCoverImageTests(ProductImageServiceTestCase):
    def test_set_cover_switches_exclusively(self):
        first = add_product_image(self.product, _make_image_file(name="1.jpg"))
        second = add_product_image(self.product, _make_image_file(name="2.jpg"))
        set_cover_image(self.product, second.pk)
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertFalse(first.is_cover)
        self.assertTrue(second.is_cover)

    def test_set_cover_unknown_image_raises(self):
        with self.assertRaises(ProductImageError):
            set_cover_image(self.product, 999999)


class MoveProductImageTests(ProductImageServiceTestCase):
    def test_move_up_swaps_order(self):
        first = add_product_image(self.product, _make_image_file(name="1.jpg"))
        second = add_product_image(self.product, _make_image_file(name="2.jpg"))
        move_product_image(second, "up")
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertEqual(second.order, 0)
        self.assertEqual(first.order, 1)

    def test_move_up_at_top_is_noop(self):
        first = add_product_image(self.product, _make_image_file(name="1.jpg"))
        move_product_image(first, "up")
        first.refresh_from_db()
        self.assertEqual(first.order, 0)

    def test_move_down_at_bottom_is_noop(self):
        first = add_product_image(self.product, _make_image_file(name="1.jpg"))
        second = add_product_image(self.product, _make_image_file(name="2.jpg"))
        move_product_image(second, "down")
        second.refresh_from_db()
        self.assertEqual(second.order, 1)


class UpdateImageAltTests(ProductImageServiceTestCase):
    def test_update_alt_saves_stripped_text(self):
        image = add_product_image(self.product, _make_image_file())
        updated = update_image_alt(image, "  متن جدید  ")
        self.assertEqual(updated.alt, "متن جدید")


class SetImageVariantTests(ProductImageServiceTestCase):
    def setUp(self):
        super().setUp()
        self.variant = ProductVariant.objects.create(product=self.product, attribute="رنگ", value="سبز")

    def test_assigns_variant(self):
        image = add_product_image(self.product, _make_image_file())
        updated = set_image_variant(image, self.variant)
        self.assertEqual(updated.variant_id, self.variant.pk)

    def test_clears_variant_with_none(self):
        image = add_product_image(self.product, _make_image_file())
        set_image_variant(image, self.variant)
        updated = set_image_variant(image, None)
        self.assertIsNone(updated.variant_id)

    def test_rejects_variant_from_other_product(self):
        vendor = Vendor.objects.create(store=self.store, name="فروشگاه دو", slug="pi-shop-2")
        from apps.catalog.models import Category

        category = Category.objects.create(store=self.store, name="دسته دو", slug="pi-cat-2")
        other_product = Product.objects.create(
            store=self.store, vendor=vendor, category=category, name="کالای دیگر", slug="pi-product-2",
            sku="PI-SKU-2", price=Decimal("100000"),
        )
        other_variant = ProductVariant.objects.create(product=other_product, attribute="سایز", value="بزرگ")
        image = add_product_image(self.product, _make_image_file())
        with self.assertRaises(ProductImageError):
            set_image_variant(image, other_variant)
        image.refresh_from_db()
        self.assertIsNone(image.variant_id)

    def test_deleting_variant_sets_null_instead_of_cascading(self):
        image = add_product_image(self.product, _make_image_file())
        set_image_variant(image, self.variant)
        self.variant.delete()
        image.refresh_from_db()
        self.assertIsNone(image.variant_id)
        self.assertTrue(ProductImage.objects.filter(pk=image.pk).exists())


class SetImageOptionValueTests(ProductImageServiceTestCase):
    """اختصاصِ تصویر به یک مقدارِ محورِ تنوع (مثلاً «قرمز») — مستقل از یک
    ترکیبِ کاملِ تنوع؛ نگاه کنید به ``set_image_variant`` برایِ مقایسه."""

    def setUp(self):
        super().setUp()
        option = add_product_option(self.product, label="رنگ", values=["قرمز"])
        self.value = option.values.get(label="قرمز")

    def test_assigns_option_value(self):
        image = add_product_image(self.product, _make_image_file())
        updated = set_image_option_value(image, self.value)
        self.assertEqual(updated.option_value_id, self.value.pk)

    def test_clears_option_value_with_none(self):
        image = add_product_image(self.product, _make_image_file())
        set_image_option_value(image, self.value)
        updated = set_image_option_value(image, None)
        self.assertIsNone(updated.option_value_id)

    def test_rejects_option_value_from_other_product(self):
        vendor = Vendor.objects.create(store=self.store, name="فروشگاه دو", slug="pi-shop-3")
        from apps.catalog.models import Category

        category = Category.objects.create(store=self.store, name="دسته دو", slug="pi-cat-3")
        other_product = Product.objects.create(
            store=self.store, vendor=vendor, category=category, name="کالای دیگر", slug="pi-product-3",
            sku="PI-SKU-3", price=Decimal("100000"),
        )
        other_option = add_product_option(other_product, label="سایز", values=["بزرگ"])
        other_value = other_option.values.get(label="بزرگ")
        image = add_product_image(self.product, _make_image_file())
        with self.assertRaises(ProductImageError):
            set_image_option_value(image, other_value)
        image.refresh_from_db()
        self.assertIsNone(image.option_value_id)

    def test_deleting_the_option_sets_null_instead_of_cascading(self):
        """با حذفِ محور (و مقادیرش)، تصویر باقی می‌ماند و فقط اختصاصش برداشته
        می‌شود (SET_NULL) — نه این‌که خودِ تصویر هم حذف شود."""
        image = add_product_image(self.product, _make_image_file())
        set_image_option_value(image, self.value)
        self.value.option.delete()
        image.refresh_from_db()
        self.assertIsNone(image.option_value_id)
        self.assertTrue(ProductImage.objects.filter(pk=image.pk).exists())
