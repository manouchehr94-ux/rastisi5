"""پوششِ تست برایِ ورودِ موبایل+رمزِ عبور (Section 3.B — تکمیلِ احرازِ هویتِ
مالک). از همان سرویسِ کانونیکالِ ``authenticate_owner_by_identifier`` عبور
می‌کند که ورودِ ایمیل+رمز هم استفاده می‌کند — این‌جا فقط فرمت‌هایِ مختلفِ
شماره و رفتارِ کاربرِ غیرفعال را در سطحِ HTTP تأیید می‌کند."""

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from apps.portal.services import owner_auth_service

User = get_user_model()
_HOST = "rastisi.localhost"
_STRONG_PASSWORD = "Str0ng!Passw0rd"


@override_settings(ALLOWED_HOSTS=[_HOST, "testserver"])
class MobilePasswordLoginTests(TestCase):
    def setUp(self):
        from django.core.cache import cache

        cache.clear()
        self.user, _ = owner_auth_service.get_or_create_owner_by_phone(
            phone="09121234599", full_name="Mobile Owner",
        )
        owner_auth_service.set_new_password(user=self.user, password=_STRONG_PASSWORD)

    def _login(self, identifier):
        return self.client.post(
            "/login/password/", {"identifier": identifier, "password": _STRONG_PASSWORD}, HTTP_HOST=_HOST,
        )

    def test_login_with_canonical_mobile_format(self):
        response = self._login("09121234599")
        self.assertEqual(response.status_code, 302)
        self.assertIn("_auth_user_id", self.client.session)

    def test_login_with_plus98_format(self):
        response = self._login("+989121234599")
        self.assertIn("_auth_user_id", self.client.session)
        self.assertEqual(response.status_code, 302)

    def test_login_with_0098_format(self):
        response = self._login("00989121234599")
        self.assertIn("_auth_user_id", self.client.session)
        self.assertEqual(response.status_code, 302)

    def test_login_with_persian_digits(self):
        response = self._login("۰۹۱۲۱۲۳۴۵۹۹")
        self.assertIn("_auth_user_id", self.client.session)
        self.assertEqual(response.status_code, 302)

    def test_login_with_wrong_password_gives_generic_error(self):
        response = self.client.post(
            "/login/password/", {"identifier": "09121234599", "password": "totally-wrong"}, HTTP_HOST=_HOST,
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertContains(response, owner_auth_service.GENERIC_LOGIN_ERROR)

    def test_inactive_mobile_owner_cannot_login_with_password(self):
        self.user.is_active = False
        self.user.save(update_fields=["is_active"])
        response = self._login("09121234599")
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertContains(response, owner_auth_service.GENERIC_LOGIN_ERROR)

    def test_unknown_mobile_gives_the_same_generic_error_as_wrong_password(self):
        response = self._login("09190000000")
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertContains(response, owner_auth_service.GENERIC_LOGIN_ERROR)
