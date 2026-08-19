"""Phase 1B — apps.core.services.rate_limit.client_ip_or_unknown.

Proves the one behavioral difference from a plain
``request.META.get("REMOTE_ADDR", "unknown")``: an empty-but-present
REMOTE_ADDR (documented Gunicorn behavior behind a Unix socket — the
production Nginx -> Unix socket -> Gunicorn topology) must not silently
become a shared "" bucket key."""

from django.test import RequestFactory, SimpleTestCase

from apps.core.services.rate_limit import client_ip_or_unknown


class ClientIpOrUnknownTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()

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

    def test_never_reads_x_forwarded_for_or_x_real_ip(self):
        """No trusted-proxy mechanism exists in this codebase yet — a
        client-supplied X-Forwarded-For/X-Real-IP must never be trusted."""
        request = self.factory.get("/", HTTP_X_FORWARDED_FOR="1.2.3.4", HTTP_X_REAL_IP="5.6.7.8")
        request.META["REMOTE_ADDR"] = "203.0.113.10"
        self.assertEqual(client_ip_or_unknown(request), "203.0.113.10")
