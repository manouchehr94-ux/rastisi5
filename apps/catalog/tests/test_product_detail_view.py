import shutil
import tempfile
from decimal import Decimal
from io import BytesIO

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from PIL import Image

from apps.catalog.models import Category, Product, ProductVariant, Review, Vendor
from apps.catalog.services.product_image_service import add_product_image
from apps.customers.models import Customer
from apps.stores.models import Store


def _akhlaghi():
    return Store.objects.get(slug="akhlaghi")

User = get_user_model()


class ProductDetailViewTests(TestCase):
    def setUp(self):
        self.store = _akhlaghi()
        self.vendor = Vendor.objects.create(store=self.store, name="فروشگاه", slug="shop-pdp")
        self.top_category = Category.objects.create(store=self.store, name="دیجیتال", slug="digital-pdp", icon="📱")
        self.category = Category.objects.create(
            store=self.store, name="موبایل", slug="mobile-pdp", icon="📱", parent=self.top_category
        )
        self.sibling_category = Category.objects.create(
            store=self.store, name="لوازم جانبی", slug="accessories-pdp", icon="🎧", parent=self.top_category
        )
        self.product = Product.objects.create(
            store=self.store, vendor=self.vendor, category=self.category, name="گوشی نمونه", slug="sample-phone-pdp",
            sku="SKU-PDP1", description="توضیح کامل محصول", price=Decimal("10000000"),
            discount_percent=10, stock=5, rating=Decimal("4.5"), reviews_count=2, views_count=100,
        )
        ProductVariant.objects.create(
            product=self.product, attribute="رنگ", value="مشکی", value_hex="#111111", stock=3
        )
        ProductVariant.objects.create(
            product=self.product, attribute="رنگ", value="آبی", value_hex="#2222ff", stock=2
        )
        ProductVariant.objects.create(
            product=self.product, attribute="حافظه", value="۱۲۸ گیگابایت", stock=5, extra_price=Decimal("500000")
        )
        self.other_product = Product.objects.create(
            store=self.store, vendor=self.vendor, category=self.category, name="گوشی دیگر", slug="other-phone-pdp",
            sku="SKU-PDP2", price=Decimal("5000000"),
        )
        self.unrelated_product = Product.objects.create(
            store=self.store, vendor=self.vendor, category=self.sibling_category, name="هندزفری نمونه",
            slug="sample-earbud-pdp", sku="SKU-PDP3", price=Decimal("1000000"),
        )

        self.user = User.objects.create_user(username="reviewer_pdp", password="pass12345")
        self.customer = Customer.objects.create(user=self.user, full_name="نیلوفر رضایی", phone="09121230099")

    def test_page_loads_and_shows_product_info(self):
        response = self.client.get(reverse("catalog:product-detail", args=[self.product.slug]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "گوشی نمونه")
        self.assertContains(response, "توضیح کامل محصول")

    def test_unknown_slug_returns_404(self):
        response = self.client.get(reverse("catalog:product-detail", args=["does-not-exist"]))
        self.assertEqual(response.status_code, 404)

    def test_views_count_increments_on_each_visit(self):
        self.client.get(reverse("catalog:product-detail", args=[self.product.slug]))
        self.product.refresh_from_db()
        self.assertEqual(self.product.views_count, 101)
        self.client.get(reverse("catalog:product-detail", args=[self.product.slug]))
        self.product.refresh_from_db()
        self.assertEqual(self.product.views_count, 102)

    def test_variant_groups_render_swatches_for_color_and_sizes_for_others(self):
        response = self.client.get(reverse("catalog:product-detail", args=[self.product.slug]))
        content = response.content.decode()
        self.assertIn('class="swatches"', content)
        self.assertIn('class="sizes"', content)
        self.assertIn("۱۲۸ گیگابایت", content)

    def test_related_products_same_category_excludes_self_and_other_categories(self):
        response = self.client.get(reverse("catalog:product-detail", args=[self.product.slug]))
        related = list(response.context["related_products"])
        self.assertIn(self.other_product, related)
        self.assertNotIn(self.product, related)
        self.assertNotIn(self.unrelated_product, related)

    def test_breadcrumb_links_to_category_and_parent(self):
        response = self.client.get(reverse("catalog:product-detail", args=[self.product.slug]))
        self.assertContains(response, f"?category={self.top_category.slug}")
        self.assertContains(response, f"?category={self.category.slug}")

    def test_rating_breakdown_reflects_approved_reviews_only(self):
        Review.objects.create(product=self.product, customer=self.customer, rating=5, text="عالی", is_approved=True)
        Review.objects.create(
            product=self.product, customer=self.customer, rating=2, text="تجربه ضعیفی بود", is_approved=False
        )
        response = self.client.get(reverse("catalog:product-detail", args=[self.product.slug]))
        self.assertEqual(response.context["review_count"], 1)
        breakdown = {row["star"]: row["count"] for row in response.context["rating_breakdown"]}
        self.assertEqual(breakdown[5], 1)
        self.assertEqual(breakdown[2], 0)
        self.assertContains(response, "عالی")
        self.assertNotContains(response, "تجربه ضعیفی بود")

    def test_rating_breakdown_query_count_does_not_grow_with_review_count(self):
        """Phase 2 — build_product_detail_context used to run one .count()
        for review_count plus five more (one per star, 5..1) — six queries
        that never changed regardless of how many reviews existed. Fixed
        via a single GROUP BY aggregate; this proves it stays a fixed cost
        whether there are 0 reviews or 30 spread across every rating."""
        from django.test.utils import CaptureQueriesContext
        from django.db import connection

        with CaptureQueriesContext(connection) as no_reviews:
            self.client.get(reverse("catalog:product-detail", args=[self.product.slug]))

        for i in range(30):
            Review.objects.create(
                product=self.product, customer=self.customer, rating=(i % 5) + 1,
                text=f"نظر {i}", is_approved=True,
            )
        with CaptureQueriesContext(connection) as many_reviews:
            self.client.get(reverse("catalog:product-detail", args=[self.product.slug]))

        self.assertEqual(
            len(no_reviews.captured_queries), len(many_reviews.captured_queries),
            "product-detail query count must not grow with review count "
            f"(0 reviews={len(no_reviews.captured_queries)}, 30 reviews={len(many_reviews.captured_queries)})",
        )

    def test_rating_breakdown_correct_across_all_five_stars(self):
        """Correctness check for the aggregate rewrite — every star bucket,
        not just the one tested in test_rating_breakdown_reflects_approved_
        reviews_only above."""
        for star, count in {5: 3, 4: 1, 3: 0, 2: 2, 1: 0}.items():
            for i in range(count):
                Review.objects.create(
                    product=self.product, customer=self.customer, rating=star,
                    text=f"star{star}-{i}", is_approved=True,
                )
        response = self.client.get(reverse("catalog:product-detail", args=[self.product.slug]))
        self.assertEqual(response.context["review_count"], 6)
        breakdown = {row["star"]: row["count"] for row in response.context["rating_breakdown"]}
        self.assertEqual(breakdown, {5: 3, 4: 1, 3: 0, 2: 2, 1: 0})
        self.assertEqual(
            {row["star"]: row["pct"] for row in response.context["rating_breakdown"]},
            {5: 50, 4: 17, 3: 0, 2: 33, 1: 0},
        )


class ProductReviewCreateTests(TestCase):
    def setUp(self):
        self.store = _akhlaghi()
        self.vendor = Vendor.objects.create(store=self.store, name="فروشگاه", slug="shop-rv")
        self.category = Category.objects.create(store=self.store, name="دیجیتال", slug="digital-rv", icon="📱")
        self.product = Product.objects.create(
            store=self.store, vendor=self.vendor, category=self.category, name="کالای نمونه", slug="sample-product-rv",
            sku="SKU-RV1", price=Decimal("100000"),
        )
        self.user = User.objects.create_user(username="reviewer_rv", password="pass12345")
        self.customer = Customer.objects.create(user=self.user, full_name="امیر حسینی", phone="09121230098")
        self.url = reverse("catalog:product-review-create", args=[self.product.slug])

    def test_anonymous_user_cannot_submit_review(self):
        response = self.client.post(self.url, {"rating": "5", "text": "متن نظر"})
        self.assertEqual(Review.objects.count(), 0)
        self.assertContains(response, "وارد حساب کاربری")

    def test_logged_in_customer_can_submit_review_pending_approval(self):
        self.client.login(username="reviewer_rv", password="pass12345")
        response = self.client.post(self.url, {"rating": "4", "text": "تجربه‌ی خوبی بود"})
        self.assertEqual(Review.objects.count(), 1)
        review = Review.objects.first()
        self.assertEqual(review.customer, self.customer)
        self.assertEqual(review.rating, 4)
        self.assertFalse(review.is_approved)
        self.assertContains(response, "ثبت شد")

    def test_empty_text_shows_validation_error_and_creates_nothing(self):
        self.client.login(username="reviewer_rv", password="pass12345")
        response = self.client.post(self.url, {"rating": "3", "text": "  "})
        self.assertEqual(Review.objects.count(), 0)
        self.assertContains(response, "متن نظر را وارد کنید")

    def test_invalid_rating_shows_validation_error(self):
        self.client.login(username="reviewer_rv", password="pass12345")
        response = self.client.post(self.url, {"rating": "9", "text": "متن معتبر"})
        self.assertEqual(Review.objects.count(), 0)
        self.assertContains(response, "امتیاز باید بین")

    def test_get_request_not_allowed(self):
        self.client.login(username="reviewer_rv", password="pass12345")
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 405)

    def test_htmx_response_has_no_full_layout(self):
        self.client.login(username="reviewer_rv", password="pass12345")
        response = self.client.post(
            self.url, {"rating": "5", "text": "متن نظر"}, HTTP_HX_REQUEST="true"
        )
        self.assertNotContains(response, "<header")


@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class ProductDetailGalleryTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        from django.conf import settings

        shutil.rmtree(settings.MEDIA_ROOT, ignore_errors=True)
        super().tearDownClass()

    def setUp(self):
        self.store = _akhlaghi()
        self.vendor = Vendor.objects.create(store=self.store, name="فروشگاه", slug="shop-pdp-gallery")
        self.category = Category.objects.create(store=self.store, name="دسته", slug="cat-pdp-gallery")
        self.product = Product.objects.create(
            store=self.store, vendor=self.vendor, category=self.category, name="کالای گالری", slug="gallery-product",
            sku="SKU-GAL1", price=Decimal("100000"), icon="🎁", tint="#eceef3",
        )

    def _make_image_file(self, name="photo.jpg"):
        buffer = BytesIO()
        Image.new("RGB", (400, 400), "#ff0000").save(buffer, format="JPEG")
        return SimpleUploadedFile(name, buffer.getvalue(), content_type="image/jpeg")

    def test_no_images_falls_back_to_emoji_slides(self):
        response = self.client.get(reverse("catalog:product-detail", args=[self.product.slug]))
        self.assertContains(response, "🎁")
        self.assertNotContains(response, "<img data-slide")

    def test_real_images_render_in_gallery(self):
        add_product_image(self.product, self._make_image_file(), alt="عکس کالای گالری")
        response = self.client.get(reverse("catalog:product-detail", args=[self.product.slug]))
        self.assertContains(response, "عکس کالای گالری")
        self.assertContains(response, "<img data-slide")

    def test_gallery_thumbnail_strip_uses_thumbnail_url(self):
        image = add_product_image(self.product, self._make_image_file())
        response = self.client.get(reverse("catalog:product-detail", args=[self.product.slug]))
        self.assertContains(response, image.thumbnail.url)


@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class ProductDetailVariantImageSwapTests(TestCase):
    """گالریِ فروشگاه باید با انتخابِ یک تنوع (مثلاً رنگ) به تصویرِ اختصاصیِ
    همان تنوع سوییچ کند — نگاه کنید به apps.catalog.services.product_image_service.set_image_variant
    و ``.gallery``ی product_detail.html."""

    @classmethod
    def tearDownClass(cls):
        from django.conf import settings

        shutil.rmtree(settings.MEDIA_ROOT, ignore_errors=True)
        super().tearDownClass()

    def setUp(self):
        self.store = _akhlaghi()
        self.vendor = Vendor.objects.create(store=self.store, name="فروشگاه", slug="shop-pdp-swap")
        self.category = Category.objects.create(store=self.store, name="دسته", slug="cat-pdp-swap")
        self.product = Product.objects.create(
            store=self.store, vendor=self.vendor, category=self.category, name="کالای سوییچ‌پذیر",
            slug="swap-product", sku="SKU-SWAP1", price=Decimal("200000"),
        )

    def _make_image_file(self, name="photo.jpg"):
        buffer = BytesIO()
        Image.new("RGB", (400, 400), "#00ff00").save(buffer, format="JPEG")
        return SimpleUploadedFile(name, buffer.getvalue(), content_type="image/jpeg")

    def test_slide_carries_its_url_and_the_variant_selector_data_maps_the_same_url(self):
        """گالری دیگر با ``variant_id`` تطبیق نمی‌دهد؛ داده‌ی JSONِ انتخاب‌گرِ
        تنوع (``image_url`` هر مقدار) و آدرسِ اسلایدِ گالری باید یکی باشند
        تا جاوااسکریپت بتواند اسلایدِ درست را پیدا کند."""
        from apps.catalog.services.product_image_service import set_image_variant

        red = ProductVariant.objects.create(product=self.product, attribute="رنگ", value="قرمز", value_hex="#f00")
        image = add_product_image(self.product, self._make_image_file())
        set_image_variant(image, red)
        response = self.client.get(reverse("catalog:product-detail", args=[self.product.slug]))
        self.assertContains(response, f'data-slide-url="{image.image.url}"')
        self.assertContains(response, image.image.url.encode())

    def test_generic_image_still_renders_as_an_addressable_slide(self):
        image = add_product_image(self.product, self._make_image_file())
        response = self.client.get(reverse("catalog:product-detail", args=[self.product.slug]))
        self.assertContains(response, f'data-slide-url="{image.image.url}"')

    def test_cover_image_is_marked_for_client_side_fallback(self):
        add_product_image(self.product, self._make_image_file())
        response = self.client.get(reverse("catalog:product-detail", args=[self.product.slug]))
        self.assertContains(response, 'data-cover="true"')

    def test_only_the_cover_image_is_marked(self):
        add_product_image(self.product, self._make_image_file("first.jpg"))
        add_product_image(self.product, self._make_image_file("second.jpg"))
        response = self.client.get(reverse("catalog:product-detail", args=[self.product.slug]))
        self.assertEqual(response.content.decode().count('data-cover="true"'), 1)

    def test_default_selected_variant_id_is_wired_for_client_side_init(self):
        """گره‌ی اولِ گروهِ تنوع (پیش‌فرضِ انتخاب‌شده در فرانت) باید در داده‌ی
        JSONِ انتخاب‌گر (``default_key``) به‌عنوانِ تنوعِ اولیه ثبت شود."""
        variant = ProductVariant.objects.create(
            product=self.product, attribute="رنگ", value="آبی", value_hex="#00f",
        )
        response = self.client.get(reverse("catalog:product-detail", args=[self.product.slug]))
        self.assertContains(response, f'"default_key": "{variant.pk}"')

    def test_works_for_a_non_color_attribute_too(self):
        """مکانیسمِ سوییچ به نامِ محور وابسته نیست — برای هر محورِ تک‌مقداریِ
        قدیمی (نه فقط «رنگ») کار می‌کند."""
        from apps.catalog.services.product_image_service import set_image_variant

        cotton = ProductVariant.objects.create(product=self.product, attribute="جنس", value="نخی")
        image = add_product_image(self.product, self._make_image_file())
        set_image_variant(image, cotton)
        response = self.client.get(reverse("catalog:product-detail", args=[self.product.slug]))
        self.assertContains(response, f'data-slide-url="{image.image.url}"')
        self.assertContains(response, f'"variant_id": {cotton.pk}')

    def test_product_without_variants_renders_gallery_without_errors(self):
        add_product_image(self.product, self._make_image_file())
        response = self.client.get(reverse("catalog:product-detail", args=[self.product.slug]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '"mode": "none"')
