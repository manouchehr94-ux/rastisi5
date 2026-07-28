"""تست‌های صفحات محتوایی — مدل، ویو، داشبورد و فوتر."""

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.content.models import ContentPage, RESERVED_SLUGS
from apps.stores.models import Store, StoreMembership


def _grant_akhlaghi_membership(user):
    StoreMembership.objects.create(
        store=Store.objects.get(slug="akhlaghi"), user=user,
        role=StoreMembership.Role.OWNER, status=StoreMembership.MembershipStatus.ACTIVE,
        accepted_at=timezone.now(),
    )

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
        page = ContentPage.objects.create(
            title="تست", slug="test-url", status="published", published_at=timezone.now()
        )
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
        _grant_akhlaghi_membership(self.staff)
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
        self.assertIn("/admin-portal/login/", response.url)

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



class XSSSecurityTests(TestCase):
    """تست‌های امنیت XSS — اطمینان از اسکیپ خودکار HTML."""

    def setUp(self):
        self.page = ContentPage.objects.create(
            title="تست XSS", slug="xss-page", status="published",
            published_at=timezone.now(),
            body='<script>alert(1)</script><img src=x onerror=alert(1)><a href="javascript:alert(1)">click</a>',
        )

    def test_script_tag_escaped(self):
        response = self.client.get("/pages/xss-page/")
        # Body content is properly escaped
        self.assertContains(response, "&lt;script&gt;alert(1)&lt;/script&gt;")
        # The malicious script does not appear as executable HTML
        self.assertNotContains(response, "<script>alert(1)</script>")

    def test_onerror_escaped(self):
        response = self.client.get("/pages/xss-page/")
        # The raw dangerous <img> tag must not appear as real HTML
        self.assertNotContains(response, '<img src=x onerror=alert(1)>')
        # It should be text-escaped instead
        self.assertContains(response, "&lt;img src=x")

    def test_javascript_href_escaped(self):
        response = self.client.get("/pages/xss-page/")
        self.assertNotContains(response, 'href="javascript:alert(1)"')
        self.assertContains(response, "javascript:alert(1)")


class SEOMetaDescriptionTests(TestCase):
    """تست‌های رندر متا توضیحات SEO."""

    def test_meta_description_rendered_when_configured(self):
        page = ContentPage.objects.create(
            title="SEO", slug="seo-desc", status="published",
            published_at=timezone.now(),
            seo_description="توضیح تستی برای موتور جستجو",
        )
        response = self.client.get("/pages/seo-desc/")
        self.assertContains(response, '<meta name="description"')
        self.assertContains(response, "توضیح تستی برای موتور جستجو")

    def test_meta_description_not_rendered_when_empty(self):
        page = ContentPage.objects.create(
            title="No Desc", slug="no-desc", status="published",
            published_at=timezone.now(),
            seo_description="",
        )
        response = self.client.get("/pages/no-desc/")
        self.assertNotContains(response, 'name="description"')

    def test_meta_description_escapes_dangerous_content(self):
        page = ContentPage.objects.create(
            title="Danger", slug="danger-desc", status="published",
            published_at=timezone.now(),
            seo_description='"><script>alert(1)</script>',
        )
        response = self.client.get("/pages/danger-desc/")
        # Script must not appear unescaped in meta tag
        self.assertNotContains(response, '<script>alert(1)</script>')
        # The content attribute should be properly escaped
        self.assertContains(response, '&quot;&gt;&lt;script&gt;')


class DashboardValidationTests(TestCase):
    """تست‌های مدیریت خطاهای اعتبارسنجی در داشبورد."""

    def setUp(self):
        from django.contrib.auth import get_user_model
        User = get_user_model()
        self.staff = User.objects.create_user(username="staff1", password="pass!", is_staff=True)
        _grant_akhlaghi_membership(self.staff)
        self.client.login(username="staff1", password="pass!")

    def test_duplicate_slug_handled_safely(self):
        ContentPage.objects.create(title="اول", slug="duplicate")
        response = self.client.post(reverse("dashboard:page-add"), {
            "title": "دوم", "slug": "duplicate", "body": "",
            "summary": "", "seo_title": "", "seo_description": "",
            "footer_column": "", "display_order": "0",
        }, follow=True)
        # Should show error, not crash
        self.assertEqual(response.status_code, 200)
        self.assertEqual(ContentPage.objects.filter(slug="duplicate").count(), 1)


class PublicationConstraintTests(TestCase):
    """تست‌های قید دیتابیسی publication_requires_timestamp."""

    def test_published_without_timestamp_violates_constraint(self):
        """Database rejects published page without published_at."""
        from django.db import IntegrityError
        with self.assertRaises(IntegrityError):
            ContentPage.objects.create(
                title="Invalid", slug="invalid-pub",
                status="published", published_at=None,
            )

    def test_draft_without_timestamp_allowed(self):
        """Draft page without published_at is valid."""
        page = ContentPage.objects.create(
            title="Draft OK", slug="draft-ok",
            status="draft", published_at=None,
        )
        self.assertEqual(page.status, "draft")
