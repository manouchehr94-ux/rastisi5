import shutil
import tempfile
from decimal import Decimal
from io import BytesIO

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from PIL import Image

from django.utils import timezone

from apps.catalog.models import Category, Product, ProductImage, ProductVariant, Vendor
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
        self.assertNotIn("/admin-portal/login/", response.url)
        self.assertIn("admin_return=", response.url)
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
        self.assertNotIn("/admin-portal/login/", response.url)
        self.assertIn("admin_return=", response.url)
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


class ProductImageVariantAssociationViewTests(ProductImageViewsTestCase):
    def setUp(self):
        super().setUp()
        self.variant_a = ProductVariant.objects.create(
            product=self.product, attribute="رنگ", value="قرمز", stock=3,
        )
        self.variant_b = ProductVariant.objects.create(
            product=self.product, attribute="رنگ", value="آبی", stock=3,
        )

    def test_assigns_image_to_variant(self):
        image = add_product_image(self.product, _make_image_file())
        response = self.client.post(
            reverse("dashboard:product-image-variant", args=[self.product.pk, image.pk]),
            {"variant": self.variant_a.pk},
        )
        self.assertEqual(response.status_code, 200)
        image.refresh_from_db()
        self.assertEqual(image.variant_id, self.variant_a.pk)

    def test_reassigning_to_blank_makes_image_general_again(self):
        image = add_product_image(self.product, _make_image_file())
        image.variant = self.variant_a
        image.save(update_fields=["variant"])
        self.client.post(
            reverse("dashboard:product-image-variant", args=[self.product.pk, image.pk]),
            {"variant": ""},
        )
        image.refresh_from_db()
        self.assertIsNone(image.variant_id)

    def test_deleting_variant_detaches_image_instead_of_deleting_it(self):
        image = add_product_image(self.product, _make_image_file())
        image.variant = self.variant_a
        image.save(update_fields=["variant"])
        self.variant_a.delete()
        image.refresh_from_db()
        self.assertIsNone(image.variant_id)
        self.assertTrue(ProductImage.objects.filter(pk=image.pk).exists())

    def test_variant_from_other_product_rejected(self):
        other_product = Product.objects.create(
            store=self.store, vendor=self.vendor, category=self.category, name="کالای دیگر", slug="piv-other",
            sku="SKU-PIV-OTHER", price=Decimal("100000"), stock=1,
        )
        other_variant = ProductVariant.objects.create(product=other_product, attribute="سایز", value="بزرگ")
        image = add_product_image(self.product, _make_image_file())
        response = self.client.post(
            reverse("dashboard:product-image-variant", args=[self.product.pk, image.pk]),
            {"variant": other_variant.pk},
        )
        self.assertEqual(response.status_code, 404)
        image.refresh_from_db()
        self.assertIsNone(image.variant_id)

    def test_variant_select_rendered_in_images_list(self):
        add_product_image(self.product, _make_image_file())
        response = self.client.get(reverse("dashboard:product-images", args=[self.product.pk]))
        self.assertContains(response, "رنگ: قرمز")
        self.assertContains(response, "رنگ: آبی")

    def test_display_image_falls_back_to_cover_when_variant_has_no_image(self):
        cover = add_product_image(self.product, _make_image_file())
        self.assertEqual(self.variant_a.display_image.pk, cover.pk)

    def test_display_image_prefers_variant_specific_image(self):
        add_product_image(self.product, _make_image_file("cover.jpg"))
        variant_image = add_product_image(self.product, _make_image_file("variant.jpg"))
        variant_image.variant = self.variant_a
        variant_image.save(update_fields=["variant"])
        self.assertEqual(self.variant_a.display_image.pk, variant_image.pk)

    def test_anonymous_denied(self):
        self.client.logout()
        image = add_product_image(self.product, _make_image_file())
        response = self.client.post(
            reverse("dashboard:product-image-variant", args=[self.product.pk, image.pk]),
            {"variant": self.variant_a.pk},
        )
        self.assertEqual(response.status_code, 302)
        self.assertNotIn("/admin-portal/login/", response.url)
        self.assertIn("admin_return=", response.url)
        image.refresh_from_db()
        self.assertIsNone(image.variant_id)


class ProductImageOptionValueAssociationViewTests(ProductImageViewsTestCase):
    """اختصاصِ تصویر به یک مقدارِ محورِ تنوع (مستقل از سایرِ محورها) — نگاه
    کنید به ``ProductImageVariantAssociationViewTests`` برایِ مقایسه با
    اختصاص به یک ترکیبِ کاملِ تنوع."""

    def setUp(self):
        super().setUp()
        from apps.catalog.models import Attribute
        from apps.catalog.services.variant_engine_service import add_product_option

        self.image_driving_attr = Attribute.objects.create(
            store=self.store, label="رنگ", code="color-piov", data_type="color", is_variant_axis=True,
            is_image_driving=True,
        )
        self.option = add_product_option(self.product, label="رنگ", attribute=self.image_driving_attr, values=["قرمز", "آبی"])
        self.red = self.option.values.get(label="قرمز")
        self.blue = self.option.values.get(label="آبی")

    def test_assigns_image_to_option_value(self):
        image = add_product_image(self.product, _make_image_file())
        response = self.client.post(
            reverse("dashboard:product-image-option-value", args=[self.product.pk, image.pk]),
            {"option_value": self.red.pk},
        )
        self.assertEqual(response.status_code, 200)
        image.refresh_from_db()
        self.assertEqual(image.option_value_id, self.red.pk)

    def test_reassigning_to_blank_clears_it(self):
        image = add_product_image(self.product, _make_image_file())
        image.option_value = self.red
        image.save(update_fields=["option_value"])
        self.client.post(
            reverse("dashboard:product-image-option-value", args=[self.product.pk, image.pk]),
            {"option_value": ""},
        )
        image.refresh_from_db()
        self.assertIsNone(image.option_value_id)

    def test_option_value_from_other_product_rejected(self):
        from apps.catalog.services.variant_engine_service import add_product_option

        other_product = Product.objects.create(
            store=self.store, vendor=self.vendor, category=self.category, name="کالای دیگر", slug="piov-other",
            sku="SKU-PIOV-OTHER", price=Decimal("100000"), stock=1,
        )
        other_option = add_product_option(other_product, label="سایز", values=["بزرگ"])
        other_value = other_option.values.get(label="بزرگ")
        image = add_product_image(self.product, _make_image_file())
        response = self.client.post(
            reverse("dashboard:product-image-option-value", args=[self.product.pk, image.pk]),
            {"option_value": other_value.pk},
        )
        self.assertEqual(response.status_code, 404)
        image.refresh_from_db()
        self.assertIsNone(image.option_value_id)

    def test_option_value_select_only_offered_for_image_driving_attributes(self):
        """اگر ویژگیِ محور «تصویرمحور» نباشد، این گزینه در فرم اصلاً نمایش داده نمی‌شود."""
        from apps.catalog.models import Attribute
        from apps.catalog.services.variant_engine_service import add_product_option

        plain_attr = Attribute.objects.create(
            store=self.store, label="جنس", code="material-piov", data_type="text", is_variant_axis=True,
            is_image_driving=False,
        )
        add_product_option(self.product, label="جنس", attribute=plain_attr, values=["چرم"])
        add_product_image(self.product, _make_image_file())
        response = self.client.get(reverse("dashboard:product-images", args=[self.product.pk]))
        self.assertContains(response, "رنگ: قرمز")
        self.assertNotContains(response, "جنس: چرم")

    def test_anonymous_denied(self):
        self.client.logout()
        image = add_product_image(self.product, _make_image_file())
        response = self.client.post(
            reverse("dashboard:product-image-option-value", args=[self.product.pk, image.pk]),
            {"option_value": self.red.pk},
        )
        self.assertEqual(response.status_code, 302)
        image.refresh_from_db()
        self.assertIsNone(image.option_value_id)

    def test_other_store_product_404s(self):
        other_store = Store.objects.create(name="فروشگاه دیگر", slug="piov-other-store", status=Store.Status.ACTIVE)
        other_vendor = Vendor.objects.create(store=other_store, name="ف2", slug="piov-other-v")
        other_category = Category.objects.create(store=other_store, name="د2", slug="piov-other-c")
        other_product = Product.objects.create(
            store=other_store, vendor=other_vendor, category=other_category, name="کالای دیگر",
            slug="piov-other-tenant", sku="SKU-PIOV-TENANT", price=Decimal("1000"),
        )
        response = self.client.post(
            reverse("dashboard:product-image-option-value", args=[other_product.pk, 1]),
            {"option_value": self.red.pk},
        )
        self.assertEqual(response.status_code, 404)

    def test_get_not_allowed(self):
        image = add_product_image(self.product, _make_image_file())
        response = self.client.get(
            reverse("dashboard:product-image-option-value", args=[self.product.pk, image.pk])
        )
        self.assertEqual(response.status_code, 405)


class ProductImageReorderViewTests(ProductImageViewsTestCase):
    def test_reorders_by_posted_sequence(self):
        first = add_product_image(self.product, _make_image_file("a.jpg"))
        second = add_product_image(self.product, _make_image_file("b.jpg"))
        third = add_product_image(self.product, _make_image_file("c.jpg"))
        response = self.client.post(reverse("dashboard:product-image-reorder", args=[self.product.pk]), {
            "image_ids": [third.pk, first.pk, second.pk],
        })
        self.assertEqual(response.status_code, 200)
        third.refresh_from_db()
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertEqual(third.order, 0)
        self.assertEqual(first.order, 1)
        self.assertEqual(second.order, 2)

    def test_get_not_allowed(self):
        response = self.client.get(reverse("dashboard:product-image-reorder", args=[self.product.pk]))
        self.assertEqual(response.status_code, 405)


class ProductImageCaptionAnd360Tests(ProductImageViewsTestCase):
    def test_updates_caption(self):
        image = add_product_image(self.product, _make_image_file())
        response = self.client.post(
            reverse("dashboard:product-image-caption", args=[self.product.pk, image.pk]),
            {"caption": "نمای جلو"},
        )
        self.assertEqual(response.status_code, 200)
        image.refresh_from_db()
        self.assertEqual(image.caption, "نمای جلو")

    def test_toggles_360_flag(self):
        image = add_product_image(self.product, _make_image_file())
        self.assertFalse(image.is_360)
        self.client.post(reverse("dashboard:product-image-360-toggle", args=[self.product.pk, image.pk]))
        image.refresh_from_db()
        self.assertTrue(image.is_360)
        self.client.post(reverse("dashboard:product-image-360-toggle", args=[self.product.pk, image.pk]))
        image.refresh_from_db()
        self.assertFalse(image.is_360)

    def test_360_toggle_still_works_even_though_hidden_from_the_ui(self):
        """گزینه‌ی ۳۶۰ از رابطِ کاربری مخفی شده (هنوز پیاده‌سازی نشده)، اما ویو و مدلِ
        زیرینش دست‌نخورده باقی مانده‌اند — برایِ وقتی که این قابلیت کامل شود."""
        image = add_product_image(self.product, _make_image_file())
        response = self.client.get(reverse("dashboard:product-images", args=[self.product.pk]))
        self.assertNotContains(response, "بخشی از مجموعه‌ی ۳۶۰")
        self.assertNotContains(response, "product-image-360-toggle")
        response = self.client.post(reverse("dashboard:product-image-360-toggle", args=[self.product.pk, image.pk]))
        self.assertEqual(response.status_code, 200)
        image.refresh_from_db()
        self.assertTrue(image.is_360)


class ProductImageDragHintAndCoverLabelTests(ProductImageViewsTestCase):
    def test_drag_hint_hidden_when_no_images(self):
        response = self.client.get(reverse("dashboard:product-images", args=[self.product.pk]))
        self.assertNotContains(response, "برای تغییرِ ترتیب بکشید")

    def test_drag_hint_shown_once_images_exist(self):
        add_product_image(self.product, _make_image_file())
        response = self.client.get(reverse("dashboard:product-images", args=[self.product.pk]))
        self.assertContains(response, "برای تغییرِ ترتیب بکشید")

    def test_cover_action_has_a_clear_label(self):
        add_product_image(self.product, _make_image_file())  # becomes cover automatically
        add_product_image(self.product, _make_image_file(name="second.jpg"))  # not the cover
        response = self.client.get(reverse("dashboard:product-images", args=[self.product.pk]))
        self.assertContains(response, "⭐ تعیینِ کاور")
        self.assertContains(response, "⭐ کاورِ کالا")


class ProductVideoViewTests(ProductImageViewsTestCase):
    def test_adds_youtube_video(self):
        response = self.client.post(reverse("dashboard:product-video-add", args=[self.product.pk]), {
            "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ", "title": "معرفی کالا",
        })
        self.assertEqual(response.status_code, 200)
        video = self.product.videos.get()
        self.assertEqual(video.provider, "youtube")
        self.assertEqual(video.embed_url, "https://www.youtube.com/embed/dQw4w9WgXcQ")

    def test_adds_aparat_video(self):
        response = self.client.post(reverse("dashboard:product-video-add", args=[self.product.pk]), {
            "url": "https://www.aparat.com/v/abc123",
        })
        self.assertEqual(response.status_code, 200)
        video = self.product.videos.get()
        self.assertEqual(video.provider, "aparat")
        self.assertIn("abc123", video.embed_url)

    def test_rejects_unknown_provider(self):
        import json

        response = self.client.post(reverse("dashboard:product-video-add", args=[self.product.pk]), {
            "url": "https://vimeo.com/12345",
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(self.product.videos.exists())
        trigger = json.loads(response.headers["HX-Trigger"])
        self.assertIn("شناخته‌شده نیست", trigger["toast"]["message"])

    def test_deletes_video(self):
        self.client.post(reverse("dashboard:product-video-add", args=[self.product.pk]), {
            "url": "https://youtu.be/dQw4w9WgXcQ",
        })
        video = self.product.videos.get()
        response = self.client.post(reverse("dashboard:product-video-delete", args=[self.product.pk, video.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(self.product.videos.exists())

    def test_other_store_product_404s(self):
        other_store = Store.objects.create(name="فروشگاه دیگر", slug="piv-other-video", status=Store.Status.ACTIVE)
        other_vendor = Vendor.objects.create(store=other_store, name="ف", slug="piv-other-v")
        other_category = Category.objects.create(store=other_store, name="د", slug="piv-other-c")
        other_product = Product.objects.create(
            store=other_store, vendor=other_vendor, category=other_category, name="کالای دیگر",
            slug="piv-other-p", sku="PIV-OTHER-SKU", price=Decimal("1000"),
        )
        response = self.client.post(reverse("dashboard:product-video-add", args=[other_product.pk]), {
            "url": "https://youtu.be/dQw4w9WgXcQ",
        })
        self.assertEqual(response.status_code, 404)
