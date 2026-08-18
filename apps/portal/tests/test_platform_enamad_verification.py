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
