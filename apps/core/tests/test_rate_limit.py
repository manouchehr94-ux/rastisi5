"""apps.core.services.rate_limit — enforce_rate_limit atomicity and
client_ip_or_unknown's trusted-proxy handling (Phase 1B/1C)."""

from django.core.cache import caches
from django.test import RequestFactory, SimpleTestCase, override_settings

from apps.core.services.rate_limit import (
    RateLimitExceeded,
    client_ip_or_unknown,
    enforce_rate_limit,
)


class ClientIpOrUnknownTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()

    # -- Proxy trust disabled (default) -------------------------------------

    def test_normal_remote_addr_is_returned_as_is(self):
        request = self.factory.get("/")
        request.META["REMOTE_ADDR"] = "203.0.113.10"
        self.assertEqual(client_ip_or_unknown(request), "203.0.113.10")

    def test_empty_string_remote_addr_becomes_unknown_not_empty_string(self):
        """The exact Gunicorn-on-a-Unix-socket case: the key is present but
        its value is "" — a plain dict .get(key, default) would return ""
        here, not the default, silently bucketing every real user together."""
        request = self.factory.get("/")
        request.META["REMOTE_ADDR"] = ""
        self.assertEqual(client_ip_or_unknown(request), "unknown")

    def test_missing_remote_addr_becomes_unknown(self):
        request = self.factory.get("/")
        request.META.pop("REMOTE_ADDR", None)
        self.assertEqual(client_ip_or_unknown(request), "unknown")

    def test_never_reads_x_forwarded_for_or_x_real_ip_by_default(self):
        """RASTISI_TRUST_PROXY_CLIENT_IP defaults to False — a client-
        supplied X-Forwarded-For/X-Real-IP must never be trusted unless a
        deployment explicitly opts in (see the *_proxy_trust_enabled tests
        below)."""
        request = self.factory.get("/", HTTP_X_FORWARDED_FOR="1.2.3.4", HTTP_X_REAL_IP="5.6.7.8")
        request.META["REMOTE_ADDR"] = "203.0.113.10"
        self.assertEqual(client_ip_or_unknown(request), "203.0.113.10")

    def test_spoofed_x_real_ip_cannot_affect_behavior_when_trust_disabled(self):
        """Same request, only REMOTE_ADDR differs from the client-supplied
        X-Real-IP — proves the header is inert, not merely unread by
        accident of test setup."""
        request = self.factory.get("/", HTTP_X_REAL_IP="9.9.9.9")
        request.META["REMOTE_ADDR"] = "203.0.113.10"
        self.assertEqual(client_ip_or_unknown(request), "203.0.113.10")
        self.assertNotEqual(client_ip_or_unknown(request), "9.9.9.9")

    # -- Proxy trust enabled --------------------------------------------------

    @override_settings(RASTISI_TRUST_PROXY_CLIENT_IP=True)
    def test_proxy_trust_enabled_uses_valid_x_real_ip(self):
        request = self.factory.get("/", HTTP_X_REAL_IP="203.0.113.10")
        request.META["REMOTE_ADDR"] = "127.0.0.1"  # e.g. the Unix-socket-local Gunicorn peer
        self.assertEqual(client_ip_or_unknown(request), "203.0.113.10")

    @override_settings(RASTISI_TRUST_PROXY_CLIENT_IP=True)
    def test_proxy_trust_enabled_ignores_spoofed_x_forwarded_for(self):
        """X-Forwarded-For is never read, even when trust is enabled — only
        X-Real-IP, because production Nginx overwrites X-Real-IP for every
        request but X-Forwarded-For can carry a client-supplied chain."""
        request = self.factory.get(
            "/", HTTP_X_REAL_IP="203.0.113.10", HTTP_X_FORWARDED_FOR="6.6.6.6, 7.7.7.7"
        )
        self.assertEqual(client_ip_or_unknown(request), "203.0.113.10")

    @override_settings(RASTISI_TRUST_PROXY_CLIENT_IP=True)
    def test_proxy_trust_enabled_ipv4(self):
        request = self.factory.get("/", HTTP_X_REAL_IP="198.51.100.23")
        self.assertEqual(client_ip_or_unknown(request), "198.51.100.23")

    @override_settings(RASTISI_TRUST_PROXY_CLIENT_IP=True)
    def test_proxy_trust_enabled_ipv6(self):
        request = self.factory.get("/", HTTP_X_REAL_IP="2001:db8::1")
        self.assertEqual(client_ip_or_unknown(request), "2001:db8::1")

    @override_settings(RASTISI_TRUST_PROXY_CLIENT_IP=True)
    def test_proxy_trust_enabled_malformed_x_real_ip_rejected(self):
        for malformed in ("not-an-ip", "999.999.999.999", "<script>alert(1)</script>", "  "):
            with self.subTest(malformed=malformed):
                request = self.factory.get("/", HTTP_X_REAL_IP=malformed)
                self.assertEqual(client_ip_or_unknown(request), "unknown")

    @override_settings(RASTISI_TRUST_PROXY_CLIENT_IP=True)
    def test_proxy_trust_enabled_comma_separated_x_real_ip_rejected(self):
        """A single trusted header is expected to carry exactly one address
        — never blindly take the first element of a comma-separated value
        the way a naive X-Forwarded-For reader might."""
        request = self.factory.get("/", HTTP_X_REAL_IP="203.0.113.10, 198.51.100.23")
        self.assertEqual(client_ip_or_unknown(request), "unknown")

    @override_settings(RASTISI_TRUST_PROXY_CLIENT_IP=True)
    def test_proxy_trust_enabled_missing_x_real_ip_falls_back_to_unknown(self):
        """No fallback to REMOTE_ADDR in trusted-proxy mode: REMOTE_ADDR is
        the proxy/socket peer there, not the real client."""
        request = self.factory.get("/")
        request.META["REMOTE_ADDR"] = "203.0.113.10"
        self.assertEqual(client_ip_or_unknown(request), "unknown")


class EnforceRateLimitTests(SimpleTestCase):
    def setUp(self):
        caches["rate_limit"].clear()
        self.addCleanup(caches["rate_limit"].clear)

    def test_uses_rate_limit_cache_alias(self):
        enforce_rate_limit("probe_action", "probe_id", max_attempts=5, window_seconds=60)
        self.assertIsNotNone(caches["rate_limit"].get("ratelimit:probe_action:probe_id"))

    @override_settings(
        CACHES={
            "default": {
                "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
                "LOCATION": "test-default-isolated",
            },
            "rate_limit": {
                "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
                "LOCATION": "test-rate-limit-isolated",
            },
        }
    )
    def test_rate_limit_alias_is_independently_configurable_from_default(self):
        """Proves the alias is genuinely dedicated, not merely named
        differently: when "rate_limit" is given its own distinct backend
        location (exactly what a production redis:// URL does relative to
        "default"), its keys are invisible on "default" — a future,
        unrelated "default" cache use can never collide with/be coupled to
        the security rate-limit store. (The local dev/test default, where
        both fall back to LocMem with no LOCATION override and therefore
        share storage so plain `cache.clear()` keeps working across the
        rest of this test suite, is covered by test_uses_rate_limit_cache_
        alias above and documented in build_rate_limit_cache_config().)"""
        enforce_rate_limit("probe_action", "probe_id", max_attempts=5, window_seconds=60)
        self.assertIsNotNone(caches["rate_limit"].get("ratelimit:probe_action:probe_id"))
        self.assertIsNone(caches["default"].get("ratelimit:probe_action:probe_id"))

    def test_first_call_creates_window_without_losing_a_count(self):
        """The add()-then-incr() pattern must never drop the very first
        attempt — a naive `try: incr() except ValueError: set(1)` retains
        the count correctly for a single caller too, but only add()-then-
        incr() also survives two callers racing on the same brand-new key
        (see the atomicity docstring in rate_limit.py)."""
        enforce_rate_limit("first_call", "id1", max_attempts=5, window_seconds=60)
        self.assertEqual(caches["rate_limit"].get("ratelimit:first_call:id1"), 1)

    def test_counts_increment_across_calls(self):
        for _ in range(3):
            enforce_rate_limit("counting", "id2", max_attempts=5, window_seconds=60)
        self.assertEqual(caches["rate_limit"].get("ratelimit:counting:id2"), 3)

    def test_raises_once_max_attempts_exceeded(self):
        for _ in range(3):
            enforce_rate_limit("capped", "id3", max_attempts=3, window_seconds=60)
        with self.assertRaises(RateLimitExceeded):
            enforce_rate_limit("capped", "id3", max_attempts=3, window_seconds=60)

    def test_concurrent_first_creation_does_not_lose_an_attempt(self):
        """Simulates two workers racing to create the same brand-new
        rate-limit key: both see the key absent and both call add() before
        either calls incr(). With add()-then-incr(), only one add() wins
        (SETNX-equivalent), but both incr() calls still land — the counter
        ends at 2, not 1. The old `incr -> ValueError -> set(1)` pattern
        would end at 1, silently discarding one of the two attempts."""
        cache = caches["rate_limit"]
        key = "ratelimit:race:id4"

        # Both "workers" run their add() before either runs incr() — the
        # actual race window the old algorithm was vulnerable to.
        first_added = cache.add(key, 0, timeout=60)
        second_added = cache.add(key, 0, timeout=60)
        self.assertTrue(first_added)
        self.assertFalse(second_added)  # key already exists — no lost creation

        first_count = cache.incr(key)
        second_count = cache.incr(key)
        self.assertEqual({first_count, second_count}, {1, 2})
        self.assertEqual(cache.get(key), 2)
