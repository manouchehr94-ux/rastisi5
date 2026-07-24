"""تست‌های صفحات محتوایی — مدل، ویو، داشبورد و فوتر."""

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.content.models import ContentPage, RESERVED_SLUGS

User = get_user_model()


class ContentPageModelTests(TestCase):
    """تست‌های مدل ContentPage."""

    def test_slug_uniqueness(self):
        ContentPage.objects.create(title="صفحه ۱", slug="page-1", status="draft")
        with self.assertRaises(Exception):
            ContentPage.objects.create(title="صفحه ۲", slug="page-1", status="draft")

    def test_reserved_slug_rejected(self):
        page = ContentPage(title="تست", slug="admin")
        with self.assertRaises(ValidationError):
            page.full_clean()

    def test_reserved_slug_products_rejected(self):
        page = ContentPage(title="تست", slug="products")
        with self.assertRaises(ValidationError):
            page.full_clean()

    def test_valid_slug_accepted(self):
        page = ContentPage(title="حریم خصوصی", slug="privacy-policy", body="متن")
        page.full_clean()  # Should not raise

    def test_persian_slug_accepted(self):
        page = ContentPage(title="درباره ما", slug="درباره-ما", body="متن")
        page.full_clean()

    def test_seo_fallback_to_title(self):
        page = ContentPage(title="تست عنوان", slug="test-seo")
        self.assertEqual(page.effective_seo_title, "تست عنوان")
        self.assertEqual(page.effective_seo_description, "")

    def test_seo_uses_explicit_values(self):
        page = ContentPage(title="عنوان", slug="s", seo_title="SEO Title", seo_description="SEO Desc")
        self.assertEqual(page.effective_seo_title, "SEO Title")
        self.assertEqual(page.effective_seo_description, "SEO Desc")

    def test_get_absolute_url(self):
        page = ContentPage.objects.create(title="تست", slug="test-url", status="published")
        self.assertEqual(page.get_absolute_url(), "/pages/test-url/")


class ContentPageStorefrontViewTests(TestCase):
    """تست‌های ویوی فروشگاه."""

    def setUp(self):
        self.published = ContentPage.objects.create(
            title="حریم خصوصی", slug="privacy", body="متن حریم خصوصی",
            status=ContentPage.Status.PUBLISHED, published_at=timezone.now(),
        )
        self.draft = ContentPage.objects.create(
            title="پیش‌نویس", slug="draft-page", body="پیش‌نویس",
            status=ContentPage.Status.DRAFT,
        )

    def test_published_page_visible(self):
        response = self.client.get("/pages/privacy/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "حریم خصوصی")
        self.assertContains(response, "متن حریم خصوصی")

    def test_draft_page_returns_404(self):
        response = self.client.get("/pages/draft-page/")
        self.assertEqual(response.status_code, 404)

    def test_nonexistent_slug_returns_404(self):
        response = self.client.get("/pages/does-not-exist/")
        self.assertEqual(response.status_code, 404)

    def test_seo_title_in_html(self):
        page = ContentPage.objects.create(
            title="عنوان", slug="seo-test", seo_title="Custom SEO",
            status="published", published_at=timezone.now(),
        )
        response = self.client.get("/pages/seo-test/")
        self.assertContains(response, "Custom SEO")


class ContentPageDashboardTests(TestCase):
    """تست‌های CRUD داشبورد."""

    def setUp(self):
        self.staff = User.objects.create_user(username="admin1", password="pass123!", is_staff=True)
        self.client.login(username="admin1", password="pass123!")

    def test_page_list_accessible(self):
        response = self.client.get(reverse("dashboard:page-list"))
        self.assertEqual(response.status_code, 200)

    def test_create_page(self):
        response = self.client.post(reverse("dashboard:page-add"), {
            "title": "صفحه جدید", "slug": "new-page", "body": "متن",
            "summary": "", "seo_title": "", "seo_description": "",
            "footer_column": "", "display_order": "0",
        })
        self.assertRedirects(response, reverse("dashboard:page-list"))
        self.assertTrue(ContentPage.objects.filter(slug="new-page").exists())

    def test_edit_page(self):
        page = ContentPage.objects.create(title="قدیم", slug="old-page")
        response = self.client.post(reverse("dashboard:page-edit", args=[page.pk]), {
            "title": "جدید", "slug": "old-page", "body": "محتوای جدید",
            "summary": "", "seo_title": "", "seo_description": "",
            "footer_column": "", "display_order": "0",
        })
        self.assertRedirects(response, reverse("dashboard:page-list"))
        page.refresh_from_db()
        self.assertEqual(page.title, "جدید")

    def test_delete_page(self):
        page = ContentPage.objects.create(title="حذفی", slug="to-delete")
        response = self.client.post(reverse("dashboard:page-delete", args=[page.pk]))
        self.assertRedirects(response, reverse("dashboard:page-list"))
        self.assertFalse(ContentPage.objects.filter(pk=page.pk).exists())

    def test_publish_page(self):
        page = ContentPage.objects.create(title="پیش‌نویس", slug="to-publish", status="draft")
        self.client.post(reverse("dashboard:page-publish", args=[page.pk]))
        page.refresh_from_db()
        self.assertEqual(page.status, ContentPage.Status.PUBLISHED)
        self.assertIsNotNone(page.published_at)

    def test_unpublish_page(self):
        page = ContentPage.objects.create(
            title="منتشر", slug="to-unpublish",
            status="published", published_at=timezone.now(),
        )
        self.client.post(reverse("dashboard:page-publish", args=[page.pk]))
        page.refresh_from_db()
        self.assertEqual(page.status, ContentPage.Status.DRAFT)

    def test_anonymous_denied(self):
        self.client.logout()
        response = self.client.get(reverse("dashboard:page-list"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin-panel/login/", response.url)

    def test_reserved_slug_rejected_in_dashboard(self):
        response = self.client.post(reverse("dashboard:page-add"), {
            "title": "Admin", "slug": "admin", "body": "",
            "summary": "", "seo_title": "", "seo_description": "",
            "footer_column": "", "display_order": "0",
        })
        # Should show error, not create page
        self.assertFalse(ContentPage.objects.filter(slug="admin").exists())


class FooterIntegrationTests(TestCase):
    """تست‌های یکپارچگی فوتر."""

    def test_published_page_in_footer(self):
        ContentPage.objects.create(
            title="قوانین", slug="terms", status="published",
            published_at=timezone.now(), show_in_footer=True,
            footer_column="customer_service",
        )
        response = self.client.get("/")
        self.assertContains(response, "/pages/terms/")
        self.assertContains(response, "قوانین")

    def test_unpublished_page_not_in_footer(self):
        ContentPage.objects.create(
            title="پیش‌نویس", slug="hidden", status="draft",
            show_in_footer=True, footer_column="customer_service",
        )
        response = self.client.get("/")
        self.assertNotContains(response, "/pages/hidden/")

    def test_footer_never_renders_hash_for_managed_pages(self):
        ContentPage.objects.create(
            title="حریم", slug="priv", status="published",
            published_at=timezone.now(), show_in_footer=True,
            footer_column="quick_access",
        )
        response = self.client.get("/")
        # The managed page link should use real URL
        self.assertContains(response, "/pages/priv/")
