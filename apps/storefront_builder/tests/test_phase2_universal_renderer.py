"""Phase 2 — Universal Storefront Renderer: HTML-level integration tests for
the two Phase 1 data-architecture pieces that were validated/stored but never
actually reached rendered output before this phase — row/grid composition
(``row_key``/``row_span``) and per-block background/spacing.

These tests deliberately assert against rendered HTML (not just Python
function return values — that coverage already exists in
``test_row_service.py``/``test_render_service.py``/``test_section_registry.py``)
because the whole point of Phase 2 is that the Phase 1 contract actually
reaches the page, through the one shared renderer, for every page type that
uses it — not a second, page-specific implementation."""

from io import BytesIO

from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from PIL import Image

from apps.content.models import MediaAsset
from apps.storefront_builder.models import StorefrontSection
from apps.storefront_builder.services import layout_service as svc
from apps.stores.models import Store, StoreDomain

HOST = "sfb-phase2-renderer.example.com"


def _akhlaghi():
    return Store.objects.get(slug="akhlaghi")


def _verified_domain(store, hostname):
    return StoreDomain.objects.create(
        store=store, hostname=hostname, is_primary=True,
        verification_status=StoreDomain.VerificationStatus.VERIFIED, verified_at=timezone.now(),
    )


def _img(name="bg.png"):
    buf = BytesIO()
    Image.new("RGB", (10, 10), (30, 60, 90)).save(buf, "PNG")
    return SimpleUploadedFile(name, buf.getvalue(), content_type="image/png")


@override_settings(ALLOWED_HOSTS=[HOST, "testserver"])
class RowGridRenderingTests(TestCase):
    """spec item 9/16/21 — 12 / 6+6 / 4+4+4 / 3+3+3+3 / 8+4, reaching real
    rendered HTML through the one shared renderer, on the public (Published)
    storefront."""

    def setUp(self):
        cache.clear()
        self.store = _akhlaghi()
        _verified_domain(self.store, HOST)

    def _publish_home_with(self, sections):
        draft = svc.get_or_create_draft(self.store)
        draft.home_page().sections.all().delete()
        for kwargs in sections:
            StorefrontSection.objects.create(version=draft, **kwargs)
        svc.publish(self.store)

    def test_standalone_sections_render_without_row_wrapper(self):
        """رفتارِ پیش‌فرض/فعلی — بدونِ هیچ row_key، هیچ ``.rsec-row``ای در
        خروجی نباید ظاهر شود (سازگاریِ کاملِ با گذشته)."""
        self._publish_home_with([
            {"section_key": "rich_text", "order": 0, "settings": {"body_html": "solo-a"}},
            {"section_key": "trust_features", "order": 1},
        ])
        resp = self.client.get(reverse("catalog:home"), HTTP_HOST=HOST)
        self.assertNotContains(resp, "rsec-row")

    def test_two_equal_columns_6_plus_6(self):
        self._publish_home_with([
            {"section_key": "rich_text", "order": 0, "row_key": "r1", "row_span": 6,
             "settings": {"body_html": "left-col"}},
            {"section_key": "trust_features", "order": 1, "row_key": "r1", "row_span": 6},
        ])
        resp = self.client.get(reverse("catalog:home"), HTTP_HOST=HOST)
        html = resp.content.decode("utf-8")
        self.assertIn('class="rsec-row"', html)
        self.assertEqual(html.count("--row-span:6"), 2)

    def test_three_equal_columns_4_plus_4_plus_4(self):
        self._publish_home_with([
            {"section_key": "rich_text", "order": 0, "row_key": "r1", "row_span": 4},
            {"section_key": "trust_features", "order": 1, "row_key": "r1", "row_span": 4},
            {"section_key": "faq", "order": 2, "row_key": "r1", "row_span": 4},
        ])
        resp = self.client.get(reverse("catalog:home"), HTTP_HOST=HOST)
        html = resp.content.decode("utf-8")
        self.assertEqual(html.count("--row-span:4"), 3)

    def test_four_equal_columns_3_plus_3_plus_3_plus_3(self):
        self._publish_home_with([
            {"section_key": "rich_text", "order": 0, "row_key": "r1", "row_span": 3},
            {"section_key": "trust_features", "order": 1, "row_key": "r1", "row_span": 3},
            {"section_key": "faq", "order": 2, "row_key": "r1", "row_span": 3},
            {"section_key": "testimonials", "order": 3, "row_key": "r1", "row_span": 3},
        ])
        resp = self.client.get(reverse("catalog:home"), HTTP_HOST=HOST)
        html = resp.content.decode("utf-8")
        self.assertEqual(html.count("--row-span:3"), 4)

    def test_asymmetric_8_plus_4(self):
        """دقیقاً ترکیبِ Hero + Instant Offer در V5 — دو ستونِ نامساوی."""
        self._publish_home_with([
            {"section_key": "hero_banner", "order": 0, "row_key": "r1", "row_span": 8},
            {"section_key": "amazing_offers", "order": 1, "row_key": "r1", "row_span": 4},
        ])
        resp = self.client.get(reverse("catalog:home"), HTTP_HOST=HOST)
        html = resp.content.decode("utf-8")
        self.assertIn("--row-span:8", html)
        self.assertIn("--row-span:4", html)

    def test_row_ordering_preserved_alongside_standalone_sections(self):
        self._publish_home_with([
            {"section_key": "rich_text", "order": 0, "settings": {"body_html": "BEFORE-ROW"}},
            {"section_key": "hero_banner", "order": 1, "row_key": "r1", "row_span": 6},
            {"section_key": "amazing_offers", "order": 2, "row_key": "r1", "row_span": 6},
            {"section_key": "trust_features", "order": 3},
        ])
        resp = self.client.get(reverse("catalog:home"), HTTP_HOST=HOST)
        html = resp.content.decode("utf-8")
        before_pos = html.index("BEFORE-ROW")
        row_pos = html.index('class="rsec-row"')
        self.assertLess(before_pos, row_pos)

    def test_draft_row_configuration_never_reaches_public_page(self):
        """تصمیمِ ۱۱ کاربر (Phase 1B) — همان تضمینِ Draft/Published، اینجا
        صریحاً برایِ کلیدِ جدیدِ ``rows``."""
        svc.get_or_create_draft(self.store)
        svc.publish(self.store)
        draft = svc.get_or_create_draft(self.store)
        draft.home_page().sections.all().delete()
        StorefrontSection.objects.create(
            version=draft, section_key="rich_text", order=0, row_key="r1", row_span=6,
            settings={"body_html": "draft-a"},
        )
        StorefrontSection.objects.create(
            version=draft, section_key="trust_features", order=1, row_key="r1", row_span=6,
        )
        resp = self.client.get(reverse("catalog:home"), HTTP_HOST=HOST)
        self.assertNotContains(resp, "rsec-row")
        self.assertNotContains(resp, "draft-a")


class RowGridPreviewTests(TestCase):
    """Preview (Draft, staff-only) must show the same row composition the
    public page would show once published — same renderer, same partial."""

    def setUp(self):
        cache.clear()
        from django.contrib.auth import get_user_model

        from apps.stores.models import StoreMembership

        self.store = _akhlaghi()
        User = get_user_model()
        self.staff = User.objects.create_user(username="p2_owner", password="pass12345", is_staff=True)
        StoreMembership.objects.create(
            store=self.store, user=self.staff, role=StoreMembership.Role.OWNER,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )
        self.store.admin_subdomain = "sfb-phase2-preview"
        self.store.save(update_fields=["admin_subdomain"])
        self.client.login(username="p2_owner", password="pass12345")

    def test_preview_shows_row_configured_only_in_draft(self):
        draft = svc.get_or_create_draft(self.store)
        draft.home_page().sections.all().delete()
        StorefrontSection.objects.create(
            version=draft, section_key="hero_banner", order=0, row_key="r1", row_span=8,
        )
        StorefrontSection.objects.create(
            version=draft, section_key="amazing_offers", order=1, row_key="r1", row_span=4,
        )
        resp = self.client.get(
            reverse("dashboard:storefront-builder-preview"),
            HTTP_HOST="sfb-phase2-preview.rastisi.localhost",
        )
        self.assertEqual(resp.status_code, 200)
        html = resp.content.decode("utf-8")
        self.assertIn("--row-span:8", html)
        self.assertIn("--row-span:4", html)


@override_settings(ALLOWED_HOSTS=[HOST, "testserver"])
class BackgroundRenderingTests(TestCase):
    """spec item 12 — Store-scoped MediaAsset only, never an arbitrary URL;
    foreign-store references must fail closed all the way to rendered HTML."""

    def setUp(self):
        cache.clear()
        self.store = _akhlaghi()
        _verified_domain(self.store, HOST)

    def _publish_home_with_one_section(self, settings):
        draft = svc.get_or_create_draft(self.store)
        draft.home_page().sections.all().delete()
        StorefrontSection.objects.create(
            version=draft, section_key="rich_text", order=0, settings=settings,
        )
        svc.publish(self.store)

    def test_theme_mode_renders_no_background_override(self):
        self._publish_home_with_one_section({"body_html": "x", "background": {"mode": "theme"}})
        resp = self.client.get(reverse("catalog:home"), HTTP_HOST=HOST)
        self.assertNotContains(resp, "data-bg-mode")

    def test_color_mode_renders_inline_background_color(self):
        self._publish_home_with_one_section(
            {"body_html": "x", "background": {"mode": "color", "color": "#E62B35"}},
        )
        resp = self.client.get(reverse("catalog:home"), HTTP_HOST=HOST)
        self.assertContains(resp, 'data-bg-mode="color"')
        self.assertContains(resp, "background-color:#E62B35")

    def test_own_store_media_asset_resolves_and_renders(self):
        asset = MediaAsset.objects.create(store=self.store, image=_img())
        self._publish_home_with_one_section(
            {"body_html": "x", "background": {"mode": "image", "media_asset_id": asset.pk}},
        )
        resp = self.client.get(reverse("catalog:home"), HTTP_HOST=HOST)
        self.assertContains(resp, 'data-bg-mode="image"')
        self.assertContains(resp, "background-image:url(")
        self.assertContains(resp, "media-assets")

    def test_foreign_store_media_asset_never_renders_as_background(self):
        """قلبِ تصمیمِ ایمنیِ مستأجرِ Phase 1 — تا سطحِ HTMLِ واقعی."""
        other_store = Store.objects.create(name="فروشگاه ب", slug="p2-cross-bg", admin_subdomain="p2-cross-bg")
        foreign_asset = MediaAsset.objects.create(store=other_store, image=_img())
        self._publish_home_with_one_section(
            {"body_html": "x", "background": {"mode": "image", "media_asset_id": foreign_asset.pk}},
        )
        resp = self.client.get(reverse("catalog:home"), HTTP_HOST=HOST)
        html = resp.content.decode("utf-8")
        self.assertNotIn("background-image:url(", html)

    def test_nonexistent_media_asset_never_crashes_or_renders(self):
        self._publish_home_with_one_section(
            {"body_html": "x", "background": {"mode": "image", "media_asset_id": 9999999}},
        )
        resp = self.client.get(reverse("catalog:home"), HTTP_HOST=HOST)
        self.assertEqual(resp.status_code, 200)
        self.assertNotContains(resp, "background-image:url(")


@override_settings(ALLOWED_HOSTS=[HOST, "testserver"])
class SpacingRenderingTests(TestCase):
    def setUp(self):
        cache.clear()
        self.store = _akhlaghi()
        _verified_domain(self.store, HOST)

    def _publish_home_with_one_section(self, settings):
        draft = svc.get_or_create_draft(self.store)
        draft.home_page().sections.all().delete()
        StorefrontSection.objects.create(
            version=draft, section_key="rich_text", order=0, settings=settings,
        )
        svc.publish(self.store)

    def test_normal_spacing_renders_no_data_attribute(self):
        self._publish_home_with_one_section({"body_html": "x", "spacing": {"vertical_spacing": "normal"}})
        resp = self.client.get(reverse("catalog:home"), HTTP_HOST=HOST)
        self.assertNotContains(resp, "data-spacing")

    def test_large_spacing_renders_data_attribute(self):
        self._publish_home_with_one_section({"body_html": "x", "spacing": {"vertical_spacing": "large"}})
        resp = self.client.get(reverse("catalog:home"), HTTP_HOST=HOST)
        self.assertContains(resp, 'data-spacing="large"')

    def test_advanced_padding_override_renders_inline_style(self):
        self._publish_home_with_one_section({
            "body_html": "x",
            "spacing": {"vertical_spacing": "normal", "advanced": {"padding_top": 64, "padding_bottom": None, "margin_top": None, "margin_bottom": None}},
        })
        resp = self.client.get(reverse("catalog:home"), HTTP_HOST=HOST)
        self.assertContains(resp, "padding-top:64px")


@override_settings(ALLOWED_HOSTS=[HOST, "testserver"])
class SharedRendererCssLoadedEverywhereTests(TestCase):
    """Phase 2: ``storefront_builder.css`` (که ``.rsec-row``/``data-bg-mode``/
    ``data-spacing`` را تعریف می‌کند) قبل از این فاز فقط رویِ صفحه‌ی اصلی و
    Preview بارگذاری می‌شد — یعنی رویِ چهار صفحه‌ی دیگر (لیست/جزئیاتِ محصول/
    کالکشن/سبد) نوشته می‌شد اما هیچ اثرِ بصری‌ای نداشت. یک رندررِ واقعاً
    universal باید این قواعد را رویِ هر شش نوع صفحه اعمال کند."""

    def setUp(self):
        cache.clear()
        self.store = _akhlaghi()
        _verified_domain(self.store, HOST)

    def test_home_loads_shared_css(self):
        """صفحه‌ی اصلی فقط بعد از اولین Publish از ``home_visual.html``
        (که این CSS را دارد) استفاده می‌کند — قبل از آن مسیرِ قدیمیِ
        ``catalog/home.html`` است (نگاه کنید به
        ``test_public_homepage_integration.py``)."""
        svc.get_or_create_draft(self.store)
        svc.publish(self.store)
        resp = self.client.get(reverse("catalog:home"), HTTP_HOST=HOST)
        self.assertContains(resp, "storefront_builder.css")

    def test_product_list_loads_shared_css(self):
        resp = self.client.get(reverse("catalog:product-list"), HTTP_HOST=HOST)
        self.assertContains(resp, "storefront_builder.css")

    def test_cart_loads_shared_css(self):
        resp = self.client.get(reverse("cart:detail"), HTTP_HOST=HOST)
        self.assertContains(resp, "storefront_builder.css")
