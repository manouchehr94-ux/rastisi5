"""تست‌های لینک‌های شبکه‌های اجتماعی — مدل، داشبورد، فروشگاه."""

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from apps.content.models import SOCIAL_ICON_MAP, SocialLink, validate_social_url

User = get_user_model()


# ============================================================ MODEL TESTS


class SocialLinkModelTests(TestCase):
    """تست‌های مدل SocialLink."""

    def test_valid_creation(self):
        link = SocialLink.objects.create(
            platform="instagram", title="اینستاگرام ما",
            url="https://instagram.com/myshop", is_active=True,
        )
        self.assertTrue(link.pk)
        self.assertEqual(link.icon_name, "instagram")

    def test_title_required(self):
        link = SocialLink(platform="telegram", title="", url="https://t.me/myshop")
        with self.assertRaises(ValidationError):
            link.full_clean()

    def test_url_required(self):
        link = SocialLink(platform="telegram", title="تلگرام", url="")
        with self.assertRaises(ValidationError):
            link.full_clean()

    def test_https_accepted(self):
        link = SocialLink(platform="instagram", title="T", url="https://instagram.com/x")
        link.full_clean()  # OK

    def test_http_accepted(self):
        link = SocialLink(platform="custom", title="T", url="http://example.com")
        link.full_clean()  # OK

    def test_javascript_rejected(self):
        link = SocialLink(platform="custom", title="T", url="javascript:alert(1)")
        with self.assertRaises(ValidationError):
            link.full_clean()

    def test_data_scheme_rejected(self):
        link = SocialLink(platform="custom", title="T", url="data:text/html,test")
        with self.assertRaises(ValidationError):
            link.full_clean()

    def test_vbscript_rejected(self):
        link = SocialLink(platform="custom", title="T", url="vbscript:MsgBox")
        with self.assertRaises(ValidationError):
            link.full_clean()

    def test_protocol_relative_rejected(self):
        link = SocialLink(platform="custom", title="T", url="//evil.com")
        with self.assertRaises(ValidationError):
            link.full_clean()

    def test_malformed_url_rejected(self):
        link = SocialLink(platform="custom", title="T", url="not a url")
        with self.assertRaises(ValidationError):
            link.full_clean()

    def test_stable_ordering(self):
        SocialLink.objects.create(platform="telegram", title="B", url="https://t.me/b", display_order=2)
        SocialLink.objects.create(platform="instagram", title="A", url="https://instagram.com/a", display_order=1)
        titles = list(SocialLink.objects.values_list("title", flat=True))
        self.assertEqual(titles, ["A", "B"])

    def test_ordering_tiebreaker_by_id(self):
        a = SocialLink.objects.create(platform="telegram", title="First", url="https://t.me/a", display_order=0)
        b = SocialLink.objects.create(platform="instagram", title="Second", url="https://instagram.com/b", display_order=0)
        titles = list(SocialLink.objects.values_list("title", flat=True))
        self.assertEqual(titles, ["First", "Second"])

    def test_persian_platform_labels(self):
        link = SocialLink(platform="instagram", title="T", url="https://x.com")
        self.assertEqual(link.get_platform_display(), "اینستاگرام")

    def test_custom_platform(self):
        link = SocialLink.objects.create(
            platform="custom", title="وبسایت", url="https://example.com"
        )
        self.assertEqual(link.effective_icon_name, "link")

    def test_icon_mapping_safety_valid(self):
        link = SocialLink(platform="custom", title="T", url="https://x.com", icon_name="telegram")
        link.full_clean()  # OK — telegram is in allowed values

    def test_icon_mapping_safety_invalid(self):
        link = SocialLink(platform="custom", title="T", url="https://x.com", icon_name="<script>alert(1)</script>")
        with self.assertRaises(ValidationError) as ctx:
            link.full_clean()
        self.assertIn("icon_name", ctx.exception.message_dict)

    def test_effective_icon_from_platform(self):
        link = SocialLink(platform="youtube", title="T", url="https://youtube.com", icon_name="")
        self.assertEqual(link.effective_icon_name, "youtube")

    def test_str_representation(self):
        link = SocialLink(platform="telegram", title="تلگرام فروشگاه", url="https://t.me/x")
        self.assertIn("تلگرام فروشگاه", str(link))

    def test_all_platforms_have_icons(self):
        for platform_val, _ in SocialLink.Platform.choices:
            self.assertIn(platform_val, SOCIAL_ICON_MAP)


class SocialURLValidatorTests(TestCase):
    """تست‌های اعتبارسنجی URL شبکه اجتماعی."""

    def test_https_valid(self):
        validate_social_url("https://instagram.com/shop")

    def test_http_valid(self):
        validate_social_url("http://example.com")

    def test_empty_rejected(self):
        with self.assertRaises(ValidationError):
            validate_social_url("")

    def test_whitespace_only_rejected(self):
        with self.assertRaises(ValidationError):
            validate_social_url("   ")

    def test_javascript_rejected(self):
        with self.assertRaises(ValidationError):
            validate_social_url("javascript:void(0)")

    def test_data_rejected(self):
        with self.assertRaises(ValidationError):
            validate_social_url("data:text/html,<h1>X</h1>")

    def test_vbscript_rejected(self):
        with self.assertRaises(ValidationError):
            validate_social_url("vbscript:MsgBox")

    def test_protocol_relative_rejected(self):
        with self.assertRaises(ValidationError):
            validate_social_url("//evil.com/path")

    def test_ftp_rejected(self):
        with self.assertRaises(ValidationError):
            validate_social_url("ftp://files.example.com")

    def test_mailto_rejected(self):
        """Social links must be http/https only, not mailto."""
        with self.assertRaises(ValidationError):
            validate_social_url("mailto:x@x.com")


# ============================================================ DASHBOARD ACCESS TESTS


class SocialLinkDashboardAccessTests(TestCase):
    """تست‌های دسترسی به داشبورد شبکه‌های اجتماعی."""

    def setUp(self):
        self.staff = User.objects.create_user(username="staff_sl", password="pass!", is_staff=True)
        self.non_staff = User.objects.create_user(username="user_sl", password="pass!", is_staff=False)

    def test_anonymous_redirected(self):
        response = self.client.get(reverse("dashboard:social-link-list"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin-panel/login/", response.url)

    def test_non_staff_rejected(self):
        self.client.login(username="user_sl", password="pass!")
        response = self.client.get(reverse("dashboard:social-link-list"))
        self.assertEqual(response.status_code, 302)

    def test_staff_allowed(self):
        self.client.login(username="staff_sl", password="pass!")
        response = self.client.get(reverse("dashboard:social-link-list"))
        self.assertEqual(response.status_code, 200)

    def test_list_page_accessible(self):
        self.client.login(username="staff_sl", password="pass!")
        response = self.client.get(reverse("dashboard:social-link-list"))
        self.assertContains(response, "شبکه‌های اجتماعی")

    def test_add_page_accessible(self):
        self.client.login(username="staff_sl", password="pass!")
        response = self.client.get(reverse("dashboard:social-link-add"))
        self.assertEqual(response.status_code, 200)

    def test_edit_page_accessible(self):
        self.client.login(username="staff_sl", password="pass!")
        link = SocialLink.objects.create(platform="telegram", title="T", url="https://t.me/x")
        response = self.client.get(reverse("dashboard:social-link-edit", args=[link.pk]))
        self.assertEqual(response.status_code, 200)

    def test_delete_requires_post(self):
        self.client.login(username="staff_sl", password="pass!")
        link = SocialLink.objects.create(platform="telegram", title="T", url="https://t.me/x")
        response = self.client.get(reverse("dashboard:social-link-delete", args=[link.pk]))
        self.assertEqual(response.status_code, 405)

    def test_toggle_requires_post(self):
        self.client.login(username="staff_sl", password="pass!")
        link = SocialLink.objects.create(platform="telegram", title="T", url="https://t.me/x")
        response = self.client.get(reverse("dashboard:social-link-toggle", args=[link.pk]))
        self.assertEqual(response.status_code, 405)

    def test_csrf_required(self):
        """CSRF enforcement is consistent with Django middleware defaults."""
        from django.test import Client
        client = Client(enforce_csrf_checks=True)
        client.login(username="staff_sl", password="pass!")
        link = SocialLink.objects.create(platform="telegram", title="T", url="https://t.me/x")
        response = client.post(reverse("dashboard:social-link-delete", args=[link.pk]))
        self.assertEqual(response.status_code, 403)


# ============================================================ DASHBOARD CRUD TESTS


class SocialLinkDashboardCRUDTests(TestCase):
    """تست‌های CRUD داشبورد شبکه‌های اجتماعی."""

    def setUp(self):
        self.staff = User.objects.create_user(username="staff_crud", password="pass!", is_staff=True)
        self.client.login(username="staff_crud", password="pass!")

    def test_create(self):
        response = self.client.post(reverse("dashboard:social-link-add"), {
            "platform": "instagram", "title": "اینستاگرام فروشگاه",
            "url": "https://instagram.com/myshop", "display_order": "1",
            "is_active": "on", "show_in_footer": "on",
        })
        self.assertRedirects(response, reverse("dashboard:social-link-list"))
        self.assertTrue(SocialLink.objects.filter(title="اینستاگرام فروشگاه").exists())

    def test_edit(self):
        link = SocialLink.objects.create(platform="telegram", title="Old", url="https://t.me/old")
        response = self.client.post(reverse("dashboard:social-link-edit", args=[link.pk]), {
            "platform": "telegram", "title": "New Title",
            "url": "https://t.me/new", "display_order": "5",
            "is_active": "on", "show_in_footer": "on",
        })
        self.assertRedirects(response, reverse("dashboard:social-link-list"))
        link.refresh_from_db()
        self.assertEqual(link.title, "New Title")
        self.assertEqual(link.url, "https://t.me/new")

    def test_delete(self):
        link = SocialLink.objects.create(platform="telegram", title="Del", url="https://t.me/del")
        response = self.client.post(reverse("dashboard:social-link-delete", args=[link.pk]))
        self.assertRedirects(response, reverse("dashboard:social-link-list"))
        self.assertFalse(SocialLink.objects.filter(pk=link.pk).exists())

    def test_activate(self):
        link = SocialLink.objects.create(platform="telegram", title="T", url="https://t.me/x", is_active=False)
        self.client.post(reverse("dashboard:social-link-toggle", args=[link.pk]))
        link.refresh_from_db()
        self.assertTrue(link.is_active)

    def test_deactivate(self):
        link = SocialLink.objects.create(platform="telegram", title="T", url="https://t.me/x", is_active=True)
        self.client.post(reverse("dashboard:social-link-toggle", args=[link.pk]))
        link.refresh_from_db()
        self.assertFalse(link.is_active)

    def test_header_visibility_saved(self):
        response = self.client.post(reverse("dashboard:social-link-add"), {
            "platform": "linkedin", "title": "لینکدین",
            "url": "https://linkedin.com/company/x", "display_order": "0",
            "is_active": "on", "show_in_header": "on", "show_in_footer": "on",
        })
        link = SocialLink.objects.get(title="لینکدین")
        self.assertTrue(link.show_in_header)

    def test_footer_visibility_saved(self):
        response = self.client.post(reverse("dashboard:social-link-add"), {
            "platform": "youtube", "title": "یوتیوب",
            "url": "https://youtube.com/c/x", "display_order": "0",
            "is_active": "on", "show_in_footer": "on",
        })
        link = SocialLink.objects.get(title="یوتیوب")
        self.assertTrue(link.show_in_footer)

    def test_display_order_saved(self):
        self.client.post(reverse("dashboard:social-link-add"), {
            "platform": "aparat", "title": "آپارات",
            "url": "https://aparat.com/x", "display_order": "42",
            "is_active": "on", "show_in_footer": "on",
        })
        link = SocialLink.objects.get(title="آپارات")
        self.assertEqual(link.display_order, 42)

    def test_invalid_url_rejected(self):
        response = self.client.post(reverse("dashboard:social-link-add"), {
            "platform": "custom", "title": "Bad",
            "url": "javascript:alert(1)", "display_order": "0",
            "is_active": "on", "show_in_footer": "on",
        })
        # Should not redirect — stays on form with error
        self.assertEqual(response.status_code, 200)
        self.assertFalse(SocialLink.objects.filter(title="Bad").exists())

    def test_invalid_edit_preserves_record(self):
        link = SocialLink.objects.create(platform="telegram", title="Keep", url="https://t.me/keep")
        self.client.post(reverse("dashboard:social-link-edit", args=[link.pk]), {
            "platform": "telegram", "title": "",  # Invalid: blank title
            "url": "https://t.me/new", "display_order": "0",
            "is_active": "on", "show_in_footer": "on",
        })
        link.refresh_from_db()
        self.assertEqual(link.title, "Keep")  # Not modified


# ============================================================ STOREFRONT TESTS


class SocialLinkStorefrontTests(TestCase):
    """تست‌های نمایش لینک‌های اجتماعی در فروشگاه."""

    def test_active_footer_link_renders(self):
        SocialLink.objects.create(
            platform="telegram", title="تلگرام ما",
            url="https://t.me/myshop", is_active=True, show_in_footer=True,
        )
        response = self.client.get("/")
        self.assertContains(response, "https://t.me/myshop")
        self.assertContains(response, 'aria-label="تلگرام ما"')

    def test_inactive_link_hidden(self):
        SocialLink.objects.create(
            platform="telegram", title="Hidden",
            url="https://t.me/hidden", is_active=False, show_in_footer=True,
        )
        response = self.client.get("/")
        self.assertNotContains(response, "https://t.me/hidden")

    def test_header_only_absent_from_footer(self):
        SocialLink.objects.create(
            platform="instagram", title="IG",
            url="https://instagram.com/ig", is_active=True,
            show_in_header=True, show_in_footer=False,
        )
        response = self.client.get("/")
        # The footer .socials section should not contain this link
        self.assertNotContains(response, "https://instagram.com/ig")

    def test_footer_only_link_renders_in_footer(self):
        SocialLink.objects.create(
            platform="facebook", title="فیسبوک",
            url="https://facebook.com/fb", is_active=True,
            show_in_header=False, show_in_footer=True,
        )
        response = self.client.get("/")
        self.assertContains(response, "https://facebook.com/fb")

    def test_correct_ordering(self):
        SocialLink.objects.create(platform="telegram", title="Second", url="https://t.me/b", is_active=True, show_in_footer=True, display_order=2)
        SocialLink.objects.create(platform="instagram", title="First", url="https://instagram.com/a", is_active=True, show_in_footer=True, display_order=1)
        response = self.client.get("/")
        content = response.content.decode()
        pos_first = content.find("https://instagram.com/a")
        pos_second = content.find("https://t.me/b")
        self.assertGreater(pos_first, -1)
        self.assertGreater(pos_second, -1)
        self.assertLess(pos_first, pos_second)

    def test_safe_target_and_rel(self):
        SocialLink.objects.create(
            platform="telegram", title="T",
            url="https://t.me/x", is_active=True, show_in_footer=True,
        )
        response = self.client.get("/")
        self.assertContains(response, 'target="_blank"')
        self.assertContains(response, 'rel="noopener noreferrer"')

    def test_title_escaped(self):
        SocialLink.objects.create(
            platform="custom", title='<script>alert("xss")</script>',
            url="https://example.com", is_active=True, show_in_footer=True,
        )
        response = self.client.get("/")
        self.assertNotContains(response, '<script>alert("xss")</script>')
        self.assertContains(response, "&lt;script&gt;")

    def test_empty_state_omits_wrapper(self):
        """No active social links → socials div should be empty."""
        response = self.client.get("/")
        content = response.content.decode()
        # The socials div should have no <a> children
        import re
        socials_match = re.search(r'<div class="socials">(.*?)</div>', content, re.DOTALL)
        if socials_match:
            inner = socials_match.group(1).strip()
            self.assertEqual(inner, "")

    def test_no_hardcoded_fallback(self):
        """No social links → no hardcoded href='#' social links appear."""
        response = self.client.get("/")
        content = response.content.decode()
        # Find the .socials section and ensure no href="#"
        import re
        socials_match = re.search(r'<div class="socials">(.*?)</div>', content, re.DOTALL)
        if socials_match:
            self.assertNotIn('href="#"', socials_match.group(1))
