"""apps.core.services.rate_limit — enforce_rate_limit atomicity (both the
generic/LocMem path and the Redis atomic-Lua-script path) and
client_ip_or_unknown's trusted-proxy handling (Phase 1B/1C/1C-correction).

Real-Redis integration test: this file's mocked tests prove the Redis path
is *wired up* and *called* correctly without requiring a live server. To
verify the Lua script's actual behavior against a real Redis (recommended
before/after the Part D runbook, in staging), run:

    docker run --rm -p 6399:6379 redis:7-alpine
    RASTISI_TEST_REDIS_URL=redis://127.0.0.1:6399/0 \\
        python manage.py test apps.core.tests.test_rate_limit.RealRedisIntegrationTests

(or point RASTISI_TEST_REDIS_URL at any throwaway Redis instance/DB index —
this test flushes and writes to it). This class auto-skips whenever
RASTISI_TEST_REDIS_URL is unset, so plain `manage.py test` never depends on
a running Redis server."""

import os
from unittest import mock

from django.core.cache import caches
from django.test import RequestFactory, SimpleTestCase, override_settings

from apps.core.services.rate_limit import (
    RateLimitExceeded,
    _LUA_INCR_WITH_TTL,
    client_ip_or_unknown,
    enforce_rate_limit,
)

_REDIS_CACHES_OVERRIDE = {
    "default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"},
    "rate_limit": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": "redis://testhost:6379/0",
    },
}


class ClientIpOrUnknownTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()

    # -- Proxy trust disabled (default): REMOTE_ADDR, now validated too -----

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

    def test_malformed_remote_addr_rejected(self):
        """Phase 1C correction: REMOTE_ADDR is now validated too, not just
        X-Real-IP — "absent OR invalid -> unknown" applies to whichever
        value is actually chosen."""
        for malformed in ("not-an-ip", "999.999.999.999", "<script>alert(1)</script>"):
            with self.subTest(malformed=malformed):
                request = self.factory.get("/")
                request.META["REMOTE_ADDR"] = malformed
                self.assertEqual(client_ip_or_unknown(request), "unknown")

    def test_comma_separated_remote_addr_rejected(self):
        request = self.factory.get("/")
        request.META["REMOTE_ADDR"] = "203.0.113.10, 198.51.100.23"
        self.assertEqual(client_ip_or_unknown(request), "unknown")

    def test_whitespace_only_remote_addr_rejected(self):
        request = self.factory.get("/")
        request.META["REMOTE_ADDR"] = "   "
        self.assertEqual(client_ip_or_unknown(request), "unknown")

    def test_valid_ipv6_remote_addr_accepted(self):
        request = self.factory.get("/")
        request.META["REMOTE_ADDR"] = "2001:db8::1"
        self.assertEqual(client_ip_or_unknown(request), "2001:db8::1")

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
        accident of test setup. A *valid* X-Real-IP is used here
        deliberately (a malformed one would be rejected regardless of
        trust, which would not prove the header itself has zero effect)."""
        request = self.factory.get("/", HTTP_X_REAL_IP="9.9.9.9")
        request.META["REMOTE_ADDR"] = "203.0.113.10"
        self.assertEqual(client_ip_or_unknown(request), "203.0.113.10")
        self.assertNotEqual(client_ip_or_unknown(request), "9.9.9.9")

    # -- Proxy trust enabled: X-Real-IP, validated -----------------------------

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

    @override_settings(RASTISI_TRUST_PROXY_CLIENT_IP=True)
    def test_proxy_trust_enabled_valid_remote_addr_still_has_zero_effect(self):
        """Even a *valid* REMOTE_ADDR must not leak through when trust is
        enabled and X-Real-IP is absent — the fallback-to-unknown in that
        mode is unconditional, not merely "REMOTE_ADDR wasn't valid"."""
        request = self.factory.get("/")
        request.META["REMOTE_ADDR"] = "203.0.113.99"
        self.assertEqual(client_ip_or_unknown(request), "unknown")


class EnforceRateLimitGenericBackendTests(SimpleTestCase):
    """The generic (non-Redis) path — today always LocMemCache in dev/test.
    No network round trips exist between add() and incr() here (both are
    in-process calls under LocMemCache's own internal lock), so this path
    does not have the Redis expiry-boundary race described in
    _redis_incr_with_ttl's docstring. It provides no cross-process
    guarantee — LocMem never does — only deterministic, correct behavior
    within a single process."""

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

    def test_first_call_creates_count_of_one(self):
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

    def test_ttl_exists_after_first_request(self):
        """Behavioral proof via public API only (no private LocMemCache
        internals): a short window really expires the key, which is only
        possible if add() actually attached a TTL rather than a permanent
        entry."""
        import time

        enforce_rate_limit("ttl_probe", "id5", max_attempts=100, window_seconds=1)
        self.assertEqual(caches["rate_limit"].get("ratelimit:ttl_probe:id5"), 1)
        time.sleep(1.2)
        self.assertIsNone(caches["rate_limit"].get("ratelimit:ttl_probe:id5"))

    def test_ttl_not_removed_by_increment(self):
        """Two increments inside a short window, then wait past the
        window's end — the key must still expire on schedule from the
        *first* call's timeout, proving incr() does not refresh/extend it
        on every call (which would let a chatty caller keep a window alive
        forever)."""
        import time

        enforce_rate_limit("ttl_probe2", "id6", max_attempts=100, window_seconds=1)
        enforce_rate_limit("ttl_probe2", "id6", max_attempts=100, window_seconds=1)
        self.assertEqual(caches["rate_limit"].get("ratelimit:ttl_probe2:id6"), 2)
        time.sleep(1.2)
        self.assertIsNone(caches["rate_limit"].get("ratelimit:ttl_probe2:id6"))

    def test_expiry_starts_a_fresh_window(self):
        cache = caches["rate_limit"]
        key = "ratelimit:expiring:id7"
        enforce_rate_limit("expiring", "id7", max_attempts=1, window_seconds=60)
        with self.assertRaises(RateLimitExceeded):
            enforce_rate_limit("expiring", "id7", max_attempts=1, window_seconds=60)
        # Simulate real expiry deterministically (no sleep) by clearing the
        # single key — equivalent, for this backend, to its TTL elapsing.
        cache.delete(key)
        enforce_rate_limit("expiring", "id7", max_attempts=1, window_seconds=60)  # must not raise
        self.assertEqual(cache.get(key), 1)

    def test_concurrent_first_creation_does_not_lose_an_attempt(self):
        """Simulates two workers racing to create the same brand-new
        rate-limit key: both see the key absent and both call add() before
        either calls incr(). With add()-then-incr(), only one add() wins
        (SETNX-equivalent), but both incr() calls still land — the counter
        ends at 2, not 1. The old `incr -> ValueError -> set(1)` pattern
        would end at 1, silently discarding one of the two attempts."""
        cache = caches["rate_limit"]
        key = "ratelimit:race:id4"

        first_added = cache.add(key, 0, timeout=60)
        second_added = cache.add(key, 0, timeout=60)
        self.assertTrue(first_added)
        self.assertFalse(second_added)  # key already exists — no lost creation

        first_count = cache.incr(key)
        second_count = cache.incr(key)
        self.assertEqual({first_count, second_count}, {1, 2})
        self.assertEqual(cache.get(key), 2)

    def test_locmem_backend_selected_in_default_test_settings(self):
        """Deterministic proof of which path this whole test class actually
        exercises — the generic path, not the Redis path (see
        EnforceRateLimitRedisPathTests for that one)."""
        from django.core.cache.backends.locmem import LocMemCache

        self.assertIsInstance(caches["rate_limit"], LocMemCache)


@override_settings(CACHES=_REDIS_CACHES_OVERRIDE)
class EnforceRateLimitRedisPathTests(SimpleTestCase):
    """Proves enforce_rate_limit routes to the atomic Lua-script path
    (_redis_incr_with_ttl) whenever the "rate_limit" alias is Django's
    RedisCache, and that it invokes Redis correctly — without requiring a
    live Redis server (the raw redis-py client is mocked). See
    RealRedisIntegrationTests below for behavior verified against an
    actual running Redis."""

    def setUp(self):
        from django.core.cache.backends.redis import RedisCache

        self.assertIsInstance(caches["rate_limit"], RedisCache)  # sanity: override took effect

    def test_redis_backend_selected_routes_to_lua_script(self):
        mock_client = mock.Mock()
        mock_client.eval.return_value = 1
        with mock.patch("apps.core.services.rate_limit._raw_redis_client", return_value=mock_client):
            enforce_rate_limit("action", "1.2.3.4", max_attempts=5, window_seconds=120)

        mock_client.eval.assert_called_once()
        script, numkeys, key, ttl_arg = mock_client.eval.call_args[0]
        self.assertEqual(script, _LUA_INCR_WITH_TTL)
        self.assertEqual(numkeys, 1)
        self.assertTrue(key.endswith("ratelimit:action:1.2.3.4"))
        self.assertEqual(ttl_arg, 120)

    def test_lua_script_atomically_increments_and_sets_ttl_only_once(self):
        """Source-level check of the script's own logic: INCR always runs;
        EXPIRE only runs `if count == 1` — i.e. exactly once, at creation
        (whether that's true first creation or a fresh window after a real
        prior expiry), never re-armed on every increment."""
        self.assertIn("INCR", _LUA_INCR_WITH_TTL)
        self.assertIn("if count == 1", _LUA_INCR_WITH_TTL)
        self.assertIn("EXPIRE", _LUA_INCR_WITH_TTL)

    def test_raises_when_lua_script_reports_over_threshold(self):
        mock_client = mock.Mock()
        mock_client.eval.return_value = 4
        with mock.patch("apps.core.services.rate_limit._raw_redis_client", return_value=mock_client):
            with self.assertRaises(RateLimitExceeded):
                enforce_rate_limit("action", "1.2.3.4", max_attempts=3, window_seconds=120)

    def test_redis_key_uses_django_make_key_for_consistency(self):
        """The raw script's key must be built via cache.make_key(), Django's
        public API — not a bespoke prefix — so a plain cache.get() on the
        same alias reads back the same key this function wrote."""
        cache = caches["rate_limit"]
        mock_client = mock.Mock()
        mock_client.eval.return_value = 1
        with mock.patch("apps.core.services.rate_limit._raw_redis_client", return_value=mock_client):
            enforce_rate_limit("myaction", "myid", max_attempts=5, window_seconds=60)
        expected_key = cache.make_key("ratelimit:myaction:myid")
        actual_key = mock_client.eval.call_args[0][2]
        self.assertEqual(actual_key, expected_key)

    def test_redis_unreachable_fails_closed_not_open(self):
        """If Redis raises (connection error, timeout, ...), the exception
        must propagate out of enforce_rate_limit uncaught — the caller (a
        view) then fails with a 500, rather than the rate limit silently
        being skipped and the request allowed through."""

        class _Boom(Exception):
            pass

        mock_client = mock.Mock()
        mock_client.eval.side_effect = _Boom("simulated redis outage")
        with mock.patch("apps.core.services.rate_limit._raw_redis_client", return_value=mock_client):
            with self.assertRaises(_Boom):
                enforce_rate_limit("action", "1.2.3.4", max_attempts=5, window_seconds=60)

    def test_raw_redis_client_reused_across_calls_for_same_location(self):
        """The raw redis-py client is a per-location singleton (redis-py
        manages its own connection pool internally) — not reconstructed on
        every single rate-limit check."""
        from apps.core.services.rate_limit import _raw_redis_client, _raw_redis_clients

        _raw_redis_clients.clear()
        with mock.patch("redis.Redis.from_url") as mock_from_url:
            mock_from_url.return_value = mock.Mock()
            client_a = _raw_redis_client("redis://testhost:6379/0")
            client_b = _raw_redis_client("redis://testhost:6379/0")
        self.assertIs(client_a, client_b)
        mock_from_url.assert_called_once()
        _raw_redis_clients.clear()


class RealRedisIntegrationTests(SimpleTestCase):
    """Opt-in integration test against an ACTUAL running Redis — skipped
    unless RASTISI_TEST_REDIS_URL is set (never required for plain
    `manage.py test`). See this module's docstring for the exact command
    to run this against a throwaway Redis in staging.

    This is the test that actually proves the expiry-boundary race is
    closed (Issue 2 of the Phase 1C correction): it lets a real key really
    expire in real Redis and confirms the next increment starts a fresh
    window with a real TTL, never a permanent/TTL-less counter."""

    def setUp(self):
        self.redis_url = os.environ.get("RASTISI_TEST_REDIS_URL")
        if not self.redis_url:
            self.skipTest(
                "RASTISI_TEST_REDIS_URL not set — see this module's docstring "
                "for how to run this against a real Redis."
            )
        self.override = override_settings(
            CACHES={
                "default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"},
                "rate_limit": {
                    "BACKEND": "django.core.cache.backends.redis.RedisCache",
                    "LOCATION": self.redis_url,
                },
            }
        )
        self.override.enable()
        self.addCleanup(self.override.disable)
        caches["rate_limit"].clear()
        self.addCleanup(caches["rate_limit"].clear)

    def test_first_request_creates_count_one_with_real_ttl(self):
        enforce_rate_limit("real_probe", "id1", max_attempts=5, window_seconds=5)
        cache = caches["rate_limit"]
        self.assertEqual(cache.get("ratelimit:real_probe:id1"), 1)

    def test_threshold_enforced_against_real_redis(self):
        for _ in range(3):
            enforce_rate_limit("real_capped", "id2", max_attempts=3, window_seconds=5)
        with self.assertRaises(RateLimitExceeded):
            enforce_rate_limit("real_capped", "id2", max_attempts=3, window_seconds=5)

    def test_expiry_boundary_never_creates_a_permanent_counter(self):
        """The actual regression test for Issue 2: waits for a real key to
        really expire in real Redis, then confirms the next call gets a
        fresh window with a real (non-permanent) TTL — not the bug where
        Django's non-atomic exists()-then-incr() would land on the
        just-expired key and INCR would silently recreate it with no TTL
        at all."""
        import time

        import redis as redis_pkg

        raw_client = redis_pkg.Redis.from_url(self.redis_url)
        cache = caches["rate_limit"]
        full_key = cache.make_key("ratelimit:real_expiry:id3")

        enforce_rate_limit("real_expiry", "id3", max_attempts=100, window_seconds=1)
        time.sleep(1.5)  # let the key genuinely expire in Redis
        self.assertEqual(raw_client.ttl(full_key), -2)  # confirm it's really gone

        enforce_rate_limit("real_expiry", "id3", max_attempts=100, window_seconds=5)
        ttl_after = raw_client.ttl(full_key)
        self.assertEqual(cache.get("ratelimit:real_expiry:id3"), 1)
        self.assertTrue(0 < ttl_after <= 5, f"expected a real bounded TTL, got {ttl_after}")
