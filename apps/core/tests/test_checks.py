"""Fast, direct unit tests for apps.core.checks — calls the check functions
in-process with override_settings. See shop_core/tests/test_production_
settings.py for the slower end-to-end proof that these are actually wired
up via `manage.py check --deploy`."""

from django.test import SimpleTestCase, override_settings

from apps.core.checks import rate_limit_backend_check, trust_proxy_debug_check


class RateLimitBackendCheckTests(SimpleTestCase):
    @override_settings(DEBUG=False)
    def test_debug_false_locmem_warns(self):
        messages = rate_limit_backend_check(None)
        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0].id, "rastisi.core.W001")

    @override_settings(DEBUG=True)
    def test_debug_true_no_warning(self):
        self.assertEqual(rate_limit_backend_check(None), [])

    @override_settings(
        DEBUG=False,
        CACHES={
            "default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"},
            "rate_limit": {"BACKEND": "django.core.cache.backends.redis.RedisCache", "LOCATION": "redis://x/0"},
        },
    )
    def test_debug_false_non_locmem_backend_no_warning(self):
        self.assertEqual(rate_limit_backend_check(None), [])


class TrustProxyDebugCheckTests(SimpleTestCase):
    @override_settings(DEBUG=True, RASTISI_TRUST_PROXY_CLIENT_IP=True)
    def test_debug_true_trust_enabled_warns(self):
        messages = trust_proxy_debug_check(None)
        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0].id, "rastisi.core.W002")

    @override_settings(DEBUG=True, RASTISI_TRUST_PROXY_CLIENT_IP=False)
    def test_debug_true_trust_disabled_no_warning(self):
        self.assertEqual(trust_proxy_debug_check(None), [])

    @override_settings(DEBUG=False, RASTISI_TRUST_PROXY_CLIENT_IP=True)
    def test_debug_false_trust_enabled_no_warning(self):
        self.assertEqual(trust_proxy_debug_check(None), [])
