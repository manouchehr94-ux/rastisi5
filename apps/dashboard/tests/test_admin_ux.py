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


class FaviconEndpointTests(TestCase):
    """تست endpoint فاوآیکون."""
    def test_favicon_ico_not_404(self):
        resp = self.client.get("/favicon.ico")
        self.assertIn(resp.status_code, [301, 302])

    def test_favicon_redirects_to_static(self):
        resp = self.client.get("/favicon.ico")
        self.assertIn("favicon", resp.url or resp.get("Location", ""))


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



class DeleteConfirmationFullTests(TestCase):
    """تست کامل صفحات تأیید حذف برای همه منابع."""
    def setUp(self):
        from io import BytesIO
        from PIL import Image
        from django.core.files.uploadedfile import SimpleUploadedFile

        from apps.stores.models import Store

        self.staff = User.objects.create_user(username="ux_del", password="p!", is_staff=True)
        self.client.login(username="ux_del", password="p!")
        self.store = Store.objects.get(slug="akhlaghi")

        buf = BytesIO()
        Image.new("RGB", (10, 10)).save(buf, "PNG")
        self.img = SimpleUploadedFile("t.png", buf.getvalue(), content_type="image/png")

    def _assert_delete_flow(self, get_url, post_url, model_class, pk, name, list_url):
        # GET shows confirmation, doesn't delete
        resp = self.client.get(get_url)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, name)
        self.assertContains(resp, "تأیید حذف")
        self.assertTrue(model_class.objects.filter(pk=pk).exists())
        # Cancel URL present
        self.assertContains(resp, list_url)
        # POST deletes
        resp = self.client.post(post_url)
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(model_class.objects.filter(pk=pk).exists())

    def test_social_link_full_flow(self):
        link = SocialLink.objects.create(platform="telegram", title="SL-Del", url="https://t.me/x")
        url = reverse("dashboard:social-link-delete", args=[link.pk])
        self._assert_delete_flow(url, url, SocialLink, link.pk, "SL-Del", reverse("dashboard:social-link-list"))

    def test_menu_full_flow(self):
        menu = Menu.objects.create(title="Menu-Del", location="footer_3")
        url = reverse("dashboard:menu-delete", args=[menu.pk])
        self._assert_delete_flow(url, url, Menu, menu.pk, "Menu-Del", reverse("dashboard:menu-list"))

    def test_menu_item_full_flow(self):
        from apps.catalog.models import Category
        cat = Category.objects.create(name="DC", slug="dc-del")
        menu = Menu.objects.create(title="M", location="header")
        item = MenuItem.objects.create(menu=menu, title="Item-Del", destination_type="category", destination_category=cat)
        url = reverse("dashboard:menu-item-delete", args=[item.pk])
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Item-Del")
        resp = self.client.post(url)
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(MenuItem.objects.filter(pk=item.pk).exists())

    def test_trust_badge_full_flow(self):
        badge = FooterTrustBadge.objects.create(store=self.store, title="Badge-Del", image=self.img)
        url = reverse("dashboard:footer-trust-badge-delete", args=[badge.pk])
        self._assert_delete_flow(url, url, FooterTrustBadge, badge.pk, "Badge-Del", reverse("dashboard:footer-trust-badge-list"))

    def test_payment_logo_full_flow(self):
        from io import BytesIO
        from PIL import Image
        from django.core.files.uploadedfile import SimpleUploadedFile

        buf = BytesIO()
        Image.new("RGB", (10, 10)).save(buf, "PNG")
        img2 = SimpleUploadedFile("t2.png", buf.getvalue(), content_type="image/png")
        logo = FooterPaymentLogo.objects.create(store=self.store, title="Logo-Del", image=img2)
        url = reverse("dashboard:footer-payment-logo-delete", args=[logo.pk])
        self._assert_delete_flow(url, url, FooterPaymentLogo, logo.pk, "Logo-Del", reverse("dashboard:footer-payment-logo-list"))

    def test_anonymous_blocked_all(self):
        self.client.logout()
        link = SocialLink.objects.create(platform="telegram", title="X", url="https://t.me/x")
        for url in [
            reverse("dashboard:social-link-delete", args=[link.pk]),
        ]:
            resp = self.client.get(url)
            self.assertEqual(resp.status_code, 302)
            self.assertIn("/admin-panel/login/", resp.url)



class AriaInvalidTests(TestCase):
    """تست aria-invalid برای فیلدهای نامعتبر."""
    def setUp(self):
        self.staff = User.objects.create_user(username="ux_aria", password="p!", is_staff=True)
        self.client.login(username="ux_aria", password="p!")

    def test_invalid_social_link_url_renders_aria_invalid(self):
        resp = self.client.post(reverse("dashboard:social-link-add"), {
            "platform": "custom", "title": "Test",
            "url": "javascript:alert(1)", "display_order": "0",
            "is_active": "on", "show_in_footer": "on",
        })
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'aria-invalid="true"')

    def test_invalid_menu_location_renders_aria_invalid(self):
        Menu.objects.create(title="Exists", location="header")
        resp = self.client.post(reverse("dashboard:menu-add"), {
            "title": "Dup", "location": "header", "is_active": "on",
        })
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'aria-invalid="true"')

    def test_invalid_footer_phone_renders_aria_invalid(self):
        resp = self.client.post(reverse("dashboard:footer-settings"), {
            "is_enabled": "on", "show_branding": "on", "show_contact": "on",
            "phone": "<script>alert(1)</script>",
            "show_navigation": "on", "show_social_links": "on",
        })
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'aria-invalid="true"')

    def test_aria_describedby_includes_error_id(self):
        resp = self.client.post(reverse("dashboard:social-link-add"), {
            "platform": "custom", "title": "Test",
            "url": "not-a-url", "display_order": "0",
            "is_active": "on", "show_in_footer": "on",
        })
        self.assertContains(resp, "error_url")

    def test_valid_fields_no_aria_invalid(self):
        resp = self.client.get(reverse("dashboard:social-link-add"))
        self.assertNotContains(resp, 'aria-invalid="true"')
