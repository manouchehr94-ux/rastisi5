"""تست‌های سرویسِ یکپارچه‌ی «مرا به خاطر بسپار» — تنها مسیرِ تنظیمِ انقضایِ
نشست پس از ورود در کلِ پلتفرم."""

from django.contrib.sessions.backends.db import SessionStore
from django.test import RequestFactory, TestCase, override_settings

from apps.portal.services.session_service import apply_remember_me


class ApplyRememberMeTests(TestCase):
    def setUp(self):
        self.request = RequestFactory().get("/")
        self.request.session = SessionStore()

    @override_settings(AUTH_SESSION_DEFAULT_EXPIRY_SECONDS=0)
    def test_unchecked_with_no_default_expires_at_browser_close(self):
        apply_remember_me(self.request, False)
        # get_expiry_age() still reports SESSION_COOKIE_AGE even when
        # expire_at_browser_close is set (Django's own semantics — that
        # flag, not the age, is what controls browser-close expiry).
        self.assertTrue(self.request.session.get_expire_at_browser_close())

    @override_settings(AUTH_SESSION_DEFAULT_EXPIRY_SECONDS=3600)
    def test_unchecked_with_a_configured_default_uses_it(self):
        apply_remember_me(self.request, False)
        self.assertFalse(self.request.session.get_expire_at_browser_close())
        # get_expiry_age() is computed from a stored absolute datetime, so
        # allow a small tolerance rather than asserting an exact second.
        self.assertAlmostEqual(self.request.session.get_expiry_age(), 3600, delta=5)

    @override_settings(AUTH_SESSION_REMEMBER_ME_EXPIRY_SECONDS=60 * 60 * 24 * 30)
    def test_checked_uses_the_remember_me_duration(self):
        apply_remember_me(self.request, True)
        self.assertFalse(self.request.session.get_expire_at_browser_close())
        self.assertAlmostEqual(self.request.session.get_expiry_age(), 60 * 60 * 24 * 30, delta=5)

    @override_settings(AUTH_SESSION_DEFAULT_EXPIRY_SECONDS=3600, AUTH_SESSION_REMEMBER_ME_EXPIRY_SECONDS=60 * 60 * 24 * 30)
    def test_checked_always_wins_over_any_default(self):
        apply_remember_me(self.request, True)
        self.assertAlmostEqual(self.request.session.get_expiry_age(), 60 * 60 * 24 * 30, delta=5)


class BackwardCompatReExportTests(TestCase):
    def test_portal_session_service_reexports_the_canonical_core_implementation(self):
        from apps.core.services.session_service import apply_remember_me as canonical
        from apps.portal.services.session_service import apply_remember_me as portal_version

        self.assertIs(portal_version, canonical)
