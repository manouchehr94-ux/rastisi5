from django.core.cache import cache
from django.test import TestCase, override_settings

from apps.portal.models import PlatformConfiguration


@override_settings(
    ALLOWED_HOSTS=["rastisi.localhost", "testserver"],
    RASTISI_PLATFORM_HOSTS=frozenset({"rastisi.localhost"}),
)
class PlatformEnamadVerificationRenderingTests(TestCase):
    def setUp(self):
        cache.clear()
        config, _ = PlatformConfiguration.objects.get_or_create(pk=1)
        config.enamad_verification_meta_tag = (
            '<meta name="enamad-verification" content="platform-safe-token">'
        )
        config.save()
        cache.clear()

    def test_platform_home_renders_safe_enamad_meta(self):
        response = self.client.get("/", HTTP_HOST="rastisi.localhost")
        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            '<meta name="enamad-verification" content="platform-safe-token">',
            html=True,
        )

    def test_non_home_platform_page_does_not_render_verification_meta(self):
        response = self.client.get("/features/", HTTP_HOST="rastisi.localhost")
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "platform-safe-token")

    def test_corrupt_legacy_value_fails_closed_instead_of_rendering_html(self):
        config = PlatformConfiguration.objects.get(pk=1)
        config.enamad_verification_meta_tag = '<script>alert(1)</script>'
        config.save(update_fields=["enamad_verification_meta_tag", "updated_at"])
        cache.clear()

        response = self.client.get("/", HTTP_HOST="rastisi.localhost")
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "<script>alert(1)</script>")


@override_settings(
    ALLOWED_HOSTS=["rastisi.localhost", "testserver"],
    RASTISI_PLATFORM_HOSTS=frozenset({"rastisi.localhost"}),
)
class PlatformEnamadBadgeRenderingTests(TestCase):
    """Phase 5 — the platform's own final eNamad badge: independent of the
    technical-verification meta, sitewide (not home-only), disabled by
    default even when identifiers are set (explicit on/off switch)."""

    def setUp(self):
        cache.clear()

    def _enable_badge(self, *, enamad_id="998877", auth_code="platformAuthCode123"):
        config, _ = PlatformConfiguration.objects.get_or_create(pk=1)
        config.enamad_id = enamad_id
        config.enamad_auth_code = auth_code
        config.enamad_badge_enabled = True
        config.save()
        cache.clear()

    def test_badge_renders_when_enabled_and_configured(self):
        self._enable_badge()
        response = self.client.get("/", HTTP_HOST="rastisi.localhost")
        self.assertContains(response, "https://trustseal.enamad.ir/?id=998877&amp;Code=platformAuthCode123")

    def test_badge_renders_sitewide_not_only_home(self):
        self._enable_badge()
        response = self.client.get("/features/", HTTP_HOST="rastisi.localhost")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "https://trustseal.enamad.ir/?id=998877&amp;Code=platformAuthCode123")

    def test_configured_but_disabled_switch_does_not_render(self):
        config, _ = PlatformConfiguration.objects.get_or_create(pk=1)
        config.enamad_id = "998877"
        config.enamad_auth_code = "platformAuthCode123"
        config.enamad_badge_enabled = False
        config.save()
        cache.clear()

        response = self.client.get("/", HTTP_HOST="rastisi.localhost")
        self.assertNotContains(response, "trustseal.enamad.ir")

    def test_badge_independent_of_verification_meta_state(self):
        """Badge configured and enabled; verification meta was never set."""
        self._enable_badge()
        config = PlatformConfiguration.objects.get(pk=1)
        self.assertEqual(config.enamad_verification_meta_tag, "")
        response = self.client.get("/", HTTP_HOST="rastisi.localhost")
        self.assertContains(response, "trustseal.enamad.ir")

    def test_badge_never_leaks_onto_merchant_or_admin_hosts(self):
        self._enable_badge()
        with override_settings(ALLOWED_HOSTS=["some-merchant.rastisi.localhost", "testserver"]):
            response = self.client.get("/", HTTP_HOST="some-merchant.rastisi.localhost")
        self.assertNotContains(response, "trustseal.enamad.ir")
