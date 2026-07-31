from django.core.cache import cache
from django.test import TestCase, override_settings

from apps.portal.models import ContactMessage
from apps.portal.services.rate_limit import RateLimitExceeded, enforce_rate_limit

_HOST = "rastisi.localhost"


class RateLimitHelperTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_allows_up_to_max_attempts(self):
        for _ in range(3):
            enforce_rate_limit("t", "1.2.3.4", max_attempts=3, window_seconds=60)

    def test_raises_past_max_attempts(self):
        for _ in range(3):
            enforce_rate_limit("t2", "1.2.3.4", max_attempts=3, window_seconds=60)
        with self.assertRaises(RateLimitExceeded):
            enforce_rate_limit("t2", "1.2.3.4", max_attempts=3, window_seconds=60)

    def test_different_identifiers_are_independent(self):
        for _ in range(3):
            enforce_rate_limit("t3", "1.2.3.4", max_attempts=3, window_seconds=60)
        # a different identifier under the same action must not be blocked
        enforce_rate_limit("t3", "5.6.7.8", max_attempts=3, window_seconds=60)


class BackwardCompatReExportTests(TestCase):
    def test_portal_rate_limit_reexports_the_canonical_core_implementation(self):
        from apps.core.services.rate_limit import enforce_rate_limit as canonical
        from apps.portal.services.rate_limit import enforce_rate_limit as portal_version

        self.assertIs(portal_version, canonical)


@override_settings(ALLOWED_HOSTS=[_HOST, "testserver"])
class ContactFormTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_valid_submission_creates_message(self):
        response = self.client.post(
            "/contact/",
            {"full_name": "Ali", "email": "ali@example.com", "subject": "hi", "message": "hello there"},
            HTTP_HOST=_HOST,
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(ContactMessage.objects.count(), 1)

    def test_rate_limit_blocks_excessive_submissions(self):
        payload = {"full_name": "Ali", "email": "ali@example.com", "message": "hello there"}
        for _ in range(5):
            self.client.post("/contact/", payload, HTTP_HOST=_HOST)
        response = self.client.post("/contact/", payload, HTTP_HOST=_HOST)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(ContactMessage.objects.count(), 5)
