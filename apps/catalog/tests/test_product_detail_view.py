from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.catalog.models import Category, Product, ProductVariant, Review, Vendor
from apps.customers.models import Customer

User = get_user_model()


class ProductDetailViewTests(TestCase):
    def setUp(self):
        self.vendor = Vendor.objects.create(name="فروشگاه", slug="shop-pdp")
        self.top_category = Category.objects.create(name="دیجیتال", slug="digital-pdp", icon="📱")
        self.category = Category.objects.create(
            name="موبایل", slug="mobile-pdp", icon="📱", parent=self.top_category
        )
        self.sibling_category = Category.objects.create(
            name="لوازم جانبی", slug="accessories-pdp", icon="🎧", parent=self.top_category
        )
        self.product = Product.objects.create(
            vendor=self.vendor, category=self.category, name="گوشی نمونه", slug="sample-phone-pdp",
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
            vendor=self.vendor, category=self.category, name="گوشی دیگر", slug="other-phone-pdp",
            sku="SKU-PDP2", price=Decimal("5000000"),
        )
        self.unrelated_product = Product.objects.create(
            vendor=self.vendor, category=self.sibling_category, name="هندزفری نمونه", slug="sample-earbud-pdp",
            sku="SKU-PDP3", price=Decimal("1000000"),
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


class ProductReviewCreateTests(TestCase):
    def setUp(self):
        self.vendor = Vendor.objects.create(name="فروشگاه", slug="shop-rv")
        self.category = Category.objects.create(name="دیجیتال", slug="digital-rv", icon="📱")
        self.product = Product.objects.create(
            vendor=self.vendor, category=self.category, name="کالای نمونه", slug="sample-product-rv",
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
