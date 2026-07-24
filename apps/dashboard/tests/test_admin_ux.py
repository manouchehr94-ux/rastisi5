"""تست‌های UX پنل مدیریت."""
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

User = get_user_model()


class AdminUXTests(TestCase):
    def setUp(self):
        self.staff = User.objects.create_user(username="ux_staff", password="p!", is_staff=True)
        self.client.login(username="ux_staff", password="p!")

    def test_social_link_list_has_page_header(self):
        resp = self.client.get(reverse("dashboard:social-link-list"))
        self.assertContains(resp, "شبکه‌های اجتماعی")
        self.assertContains(resp, "page-header")

    def test_social_link_form_has_help_text(self):
        resp = self.client.get(reverse("dashboard:social-link-add"))
        self.assertContains(resp, "field-help")
        self.assertContains(resp, "https://")

    def test_menu_list_has_guidance(self):
        resp = self.client.get(reverse("dashboard:menu-list"))
        self.assertContains(resp, "guidance-panel")
        self.assertContains(resp, "محل نمایش منو")

    def test_menu_list_empty_state(self):
        resp = self.client.get(reverse("dashboard:menu-list"))
        self.assertContains(resp, "empty-state")

    def test_footer_settings_has_sections(self):
        resp = self.client.get(reverse("dashboard:footer-settings"))
        self.assertContains(resp, "form-section")
        self.assertContains(resp, "اطلاعات تماس")

    def test_footer_badges_empty_state(self):
        resp = self.client.get(reverse("dashboard:footer-trust-badge-list"))
        self.assertContains(resp, "empty-state")

    def test_menu_form_has_help_text(self):
        resp = self.client.get(reverse("dashboard:menu-add"))
        self.assertContains(resp, "field-help")

    def test_social_link_list_has_empty_state(self):
        resp = self.client.get(reverse("dashboard:social-link-list"))
        self.assertContains(resp, "empty-state")

    def test_favicon_accessible(self):
        from django.contrib.staticfiles.finders import find
        result = find("favicon.ico")
        self.assertIsNotNone(result, "favicon.ico should be found by static finders")

    def test_no_stale_heroes_route_in_sidebar(self):
        resp = self.client.get(reverse("dashboard:dashboard"))
        self.assertNotContains(resp, "/admin-panel/heroes/")
        self.assertNotContains(resp, "/admin-panel/banners/")

    def test_footer_payment_logos_empty_state(self):
        resp = self.client.get(reverse("dashboard:footer-payment-logo-list"))
        self.assertContains(resp, "empty-state")

    def test_menu_item_form_has_help_text(self):
        from apps.content.models import Menu
        menu = Menu.objects.create(title="T", location="header")
        resp = self.client.get(reverse("dashboard:menu-item-add", args=[menu.pk]))
        self.assertContains(resp, "field-help")
