"""تست‌های UX پنل مدیریت."""
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.content.models import FooterSettings, FooterTrustBadge, FooterPaymentLogo, Menu, MenuItem, SocialLink

User = get_user_model()


class PageGuidanceTests(TestCase):
    """تست وجود راهنما و سرفصل‌های صفحات."""
    def setUp(self):
        self.staff = User.objects.create_user(username="ux1", password="p!", is_staff=True)
        self.client.login(username="ux1", password="p!")

    def test_social_link_list_page_header(self):
        resp = self.client.get(reverse("dashboard:social-link-list"))
        self.assertContains(resp, "page-header")
        self.assertContains(resp, "شبکه‌های اجتماعی")

    def test_menu_list_guidance_panel(self):
        resp = self.client.get(reverse("dashboard:menu-list"))
        self.assertContains(resp, "guidance-panel")
        self.assertContains(resp, "محل نمایش منو")

    def test_footer_settings_page_header(self):
        resp = self.client.get(reverse("dashboard:footer-settings"))
        self.assertContains(resp, "page-header")
        self.assertContains(resp, "تنظیمات فوتر")


class HelpTextTests(TestCase):
    """تست وجود متن راهنما در فرم‌ها."""
    def setUp(self):
        self.staff = User.objects.create_user(username="ux2", password="p!", is_staff=True)
        self.client.login(username="ux2", password="p!")

    def test_social_link_form_help(self):
        resp = self.client.get(reverse("dashboard:social-link-add"))
        self.assertContains(resp, "field-help")
        self.assertContains(resp, "https://")

    def test_menu_form_help(self):
        resp = self.client.get(reverse("dashboard:menu-add"))
        self.assertContains(resp, "field-help")

    def test_menu_item_form_help(self):
        menu = Menu.objects.create(title="T", location="header")
        resp = self.client.get(reverse("dashboard:menu-item-add", args=[menu.pk]))
        self.assertContains(resp, "field-help")

    def test_footer_settings_help(self):
        resp = self.client.get(reverse("dashboard:footer-settings"))
        self.assertContains(resp, "field-help")


class EmptyStateTests(TestCase):
    """تست وضعیت خالی."""
    def setUp(self):
        self.staff = User.objects.create_user(username="ux3", password="p!", is_staff=True)
        self.client.login(username="ux3", password="p!")

    def test_social_links_empty(self):
        resp = self.client.get(reverse("dashboard:social-link-list"))
        self.assertContains(resp, "empty-state")

    def test_menus_empty(self):
        resp = self.client.get(reverse("dashboard:menu-list"))
        self.assertContains(resp, "empty-state")

    def test_trust_badges_empty(self):
        resp = self.client.get(reverse("dashboard:footer-trust-badge-list"))
        self.assertContains(resp, "empty-state")

    def test_payment_logos_empty(self):
        resp = self.client.get(reverse("dashboard:footer-payment-logo-list"))
        self.assertContains(resp, "empty-state")


class FooterSectionsTests(TestCase):
    """تست بخش‌بندی تنظیمات فوتر."""
    def setUp(self):
        self.staff = User.objects.create_user(username="ux4", password="p!", is_staff=True)
        self.client.login(username="ux4", password="p!")

    def test_sections_present(self):
        resp = self.client.get(reverse("dashboard:footer-settings"))
        self.assertContains(resp, "form-section")
        self.assertContains(resp, "اطلاعات تماس")
        self.assertContains(resp, "خبرنامه")
        self.assertContains(resp, "کپی‌رایت")

    def test_uses_wide_card(self):
        resp = self.client.get(reverse("dashboard:footer-settings"))
        self.assertContains(resp, "form-card--wide")


class DeleteConfirmationTests(TestCase):
    """تست صفحات تأیید حذف."""
    def setUp(self):
        self.staff = User.objects.create_user(username="ux5", password="p!", is_staff=True)
        self.client.login(username="ux5", password="p!")

    def test_social_link_get_shows_confirmation(self):
        link = SocialLink.objects.create(platform="telegram", title="TG", url="https://t.me/x")
        resp = self.client.get(reverse("dashboard:social-link-delete", args=[link.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "تأیید حذف")
        self.assertContains(resp, "TG")
        self.assertTrue(SocialLink.objects.filter(pk=link.pk).exists())

    def test_social_link_post_deletes(self):
        link = SocialLink.objects.create(platform="telegram", title="TG", url="https://t.me/x")
        resp = self.client.post(reverse("dashboard:social-link-delete", args=[link.pk]))
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(SocialLink.objects.filter(pk=link.pk).exists())

    def test_menu_get_shows_confirmation(self):
        menu = Menu.objects.create(title="TestMenu", location="header")
        resp = self.client.get(reverse("dashboard:menu-delete", args=[menu.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "TestMenu")

    def test_menu_post_deletes_empty(self):
        menu = Menu.objects.create(title="Empty", location="footer_1")
        resp = self.client.post(reverse("dashboard:menu-delete", args=[menu.pk]))
        self.assertFalse(Menu.objects.filter(pk=menu.pk).exists())

    def test_anonymous_blocked(self):
        self.client.logout()
        link = SocialLink.objects.create(platform="telegram", title="X", url="https://t.me/x")
        resp = self.client.get(reverse("dashboard:social-link-delete", args=[link.pk]))
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/admin-panel/login/", resp.url)

    def test_cancel_url_present(self):
        link = SocialLink.objects.create(platform="telegram", title="X", url="https://t.me/x")
        resp = self.client.get(reverse("dashboard:social-link-delete", args=[link.pk]))
        self.assertContains(resp, reverse("dashboard:social-link-list"))


class MenuWorkflowTests(TestCase):
    """تست گردش کار ایجاد منو."""
    def setUp(self):
        self.staff = User.objects.create_user(username="ux6", password="p!", is_staff=True)
        self.client.login(username="ux6", password="p!")

    def test_create_redirects_to_item_list(self):
        resp = self.client.post(reverse("dashboard:menu-add"), {
            "title": "New Menu", "location": "footer_2", "is_active": "on",
        })
        menu = Menu.objects.get(title="New Menu")
        self.assertRedirects(resp, reverse("dashboard:menu-item-list", args=[menu.pk]))


class FaviconTests(TestCase):
    """تست فاوآیکون."""
    def test_favicon_static_exists(self):
        from django.contrib.staticfiles.finders import find
        result = find("favicon.ico")
        self.assertIsNotNone(result)

    def test_base_template_favicon_link(self):
        resp = self.client.get("/")
        self.assertContains(resp, 'rel="icon"')


class StaleRouteTests(TestCase):
    """تست عدم وجود مسیرهای منسوخ."""
    def setUp(self):
        self.staff = User.objects.create_user(username="ux7", password="p!", is_staff=True)
        self.client.login(username="ux7", password="p!")

    def test_no_stale_heroes_in_sidebar(self):
        resp = self.client.get(reverse("dashboard:dashboard"))
        self.assertNotContains(resp, "/admin-panel/heroes/")

    def test_no_stale_banners_in_sidebar(self):
        resp = self.client.get(reverse("dashboard:dashboard"))
        self.assertNotContains(resp, 'href="/admin-panel/banners/"')
