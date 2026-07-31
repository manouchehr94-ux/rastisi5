"""تست‌های نرمال‌سازیِ متعارفِ شماره موبایل — تنها منبعِ حقیقتِ این منطق
در کل کدبیس (apps.portal.phone هم فقط از همین‌جا دوباره صادر می‌کند)."""

from django.test import SimpleTestCase

from apps.core.phone import InvalidPhoneError, normalize_iranian_phone


class NormalizeIranianPhoneTests(SimpleTestCase):
    def test_local_format_passthrough(self):
        self.assertEqual(normalize_iranian_phone("09121234567"), "09121234567")

    def test_plus98_prefix(self):
        self.assertEqual(normalize_iranian_phone("+989121234567"), "09121234567")

    def test_0098_prefix(self):
        self.assertEqual(normalize_iranian_phone("00989121234567"), "09121234567")

    def test_98_prefix_without_plus(self):
        self.assertEqual(normalize_iranian_phone("989121234567"), "09121234567")

    def test_bare_9_without_leading_zero(self):
        self.assertEqual(normalize_iranian_phone("9121234567"), "09121234567")

    def test_persian_digits(self):
        self.assertEqual(normalize_iranian_phone("۰۹۱۲۱۲۳۴۵۶۷"), "09121234567")

    def test_arabic_indic_digits(self):
        self.assertEqual(normalize_iranian_phone("٠٩١٢١٢٣٤٥٦٧"), "09121234567")

    def test_whitespace_and_dashes_stripped(self):
        self.assertEqual(normalize_iranian_phone("0912 123-4567"), "09121234567")

    def test_none_rejected(self):
        with self.assertRaises(InvalidPhoneError):
            normalize_iranian_phone(None)

    def test_too_short_rejected(self):
        with self.assertRaises(InvalidPhoneError):
            normalize_iranian_phone("123")

    def test_wrong_prefix_rejected(self):
        with self.assertRaises(InvalidPhoneError):
            normalize_iranian_phone("08121234567")

    def test_landline_shaped_number_rejected(self):
        with self.assertRaises(InvalidPhoneError):
            normalize_iranian_phone("02112345678")


class BackwardCompatReExportTests(SimpleTestCase):
    def test_portal_phone_reexports_canonical_normalizer(self):
        from apps.portal.phone import InvalidPhoneError as PortalError
        from apps.portal.phone import normalize_iranian_phone as portal_normalize

        self.assertIs(portal_normalize, normalize_iranian_phone)
        self.assertIs(PortalError, InvalidPhoneError)
