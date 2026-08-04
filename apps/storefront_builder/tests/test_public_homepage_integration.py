"""صفحه اصلی عمومی و سازنده بصری — تصمیم ۳ و ۱۱ کاربر: فروشگاه‌های موجود
تا اولین Publish دستی بدون تغییر از مسیر قدیمی رندر می‌شوند؛ بعد از آن،
صفحه‌ی عمومی همیشه نسخه‌ی منتشرشده را می‌بیند — هرگز Draft را."""

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.storefront_builder.models import StorefrontSection
from apps.storefront_builder.services import layout_service as svc
from apps.stores.models import Store, StoreDomain

HOST = "sfb-public-home.example.com"


def _verified_domain(store, hostname):
    return StoreDomain.objects.create(
        store=store, hostname=hostname, is_primary=True,
        verification_status=StoreDomain.VerificationStatus.VERIFIED, verified_at=timezone.now(),
    )


@override_settings(ALLOWED_HOSTS=[HOST, "testserver"])
class PublicHomepageIntegrationTests(TestCase):
    def setUp(self):
        cache.clear()
        self.store = Store.objects.get(slug="akhlaghi")
        _verified_domain(self.store, HOST)

    def test_legacy_homepage_used_when_never_published(self):
        resp = self.client.get(reverse("catalog:home"), HTTP_HOST=HOST)
        self.assertEqual(resp.status_code, 200)
        template_names = [t.name for t in resp.templates if t.name]
        self.assertIn("catalog/home.html", template_names)
        self.assertNotIn("catalog/home_visual.html", template_names)

    def test_legacy_homepage_still_used_while_draft_exists_but_unpublished(self):
        svc.get_or_create_draft(self.store)
        resp = self.client.get(reverse("catalog:home"), HTTP_HOST=HOST)
        template_names = [t.name for t in resp.templates if t.name]
        self.assertIn("catalog/home.html", template_names)

    def test_visual_homepage_used_after_first_publish(self):
        svc.get_or_create_draft(self.store)
        svc.publish(self.store)
        resp = self.client.get(reverse("catalog:home"), HTTP_HOST=HOST)
        self.assertEqual(resp.status_code, 200)
        template_names = [t.name for t in resp.templates if t.name]
        self.assertIn("catalog/home_visual.html", template_names)
        self.assertNotIn("catalog/home.html", template_names)

    def test_public_page_shows_published_content_not_later_draft_edits(self):
        """تصمیم ۱۱ کاربر: صفحه عمومی هرگز Draft را نمی‌بیند — ویرایش‌های
        بعد از Publish تا Publish دوباره روی صفحه عمومی ظاهر نمی‌شوند."""
        svc.get_or_create_draft(self.store)
        svc.publish(self.store)
        draft = svc.get_or_create_draft(self.store)
        StorefrontSection.objects.create(
            version=draft, section_key="rich_text", order=999,
            settings={"body_html": "PUBLIC-SHOULD-NEVER-SEE-THIS-DRAFT-MARKER"},
        )
        resp = self.client.get(reverse("catalog:home"), HTTP_HOST=HOST)
        self.assertNotContains(resp, "PUBLIC-SHOULD-NEVER-SEE-THIS-DRAFT-MARKER")

    def test_header_config_toggle_hides_cart_icon(self):
        draft = svc.get_or_create_draft(self.store)
        draft.header_config = {**(draft.header_config or {}), "show_cart": False}
        draft.save(update_fields=["header_config"])
        svc.publish(self.store)
        resp = self.client.get(reverse("catalog:home"), HTTP_HOST=HOST)
        self.assertNotContains(resp, 'id="cart-count"')

    def test_footer_config_toggle_hides_copyright(self):
        draft = svc.get_or_create_draft(self.store)
        draft.footer_config = {**(draft.footer_config or {}), "show_copyright": False}
        draft.save(update_fields=["footer_config"])
        svc.publish(self.store)
        resp = self.client.get(reverse("catalog:home"), HTTP_HOST=HOST)
        self.assertNotContains(resp, 'class="copy"')

    def test_unknown_section_type_in_published_version_never_crashes_public_page(self):
        draft = svc.get_or_create_draft(self.store)
        StorefrontSection.objects.create(version=draft, section_key="a_removed_legacy_type", order=999)
        svc.publish(self.store)
        resp = self.client.get(reverse("catalog:home"), HTTP_HOST=HOST)
        self.assertEqual(resp.status_code, 200)
