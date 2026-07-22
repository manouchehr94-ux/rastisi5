from django.test import TestCase

from apps.core.utils import format_toman, normalize_digits, to_fa_digits


class ToFaDigitsTests(TestCase):
    def test_converts_latin_digits(self):
        self.assertEqual(to_fa_digits(123), "۱۲۳")

    def test_none_returns_empty_string(self):
        self.assertEqual(to_fa_digits(None), "")

    def test_leaves_non_digit_characters_untouched(self):
        self.assertEqual(to_fa_digits("12-34"), "۱۲-۳۴")


class NormalizeDigitsTests(TestCase):
    def test_converts_persian_digits_to_latin(self):
        self.assertEqual(normalize_digits("۰۹۱۲۳"), "09123")

    def test_none_returns_empty_string(self):
        self.assertEqual(normalize_digits(None), "")

    def test_roundtrip_with_to_fa_digits(self):
        self.assertEqual(normalize_digits(to_fa_digits("09121234567")), "09121234567")


class FormatTomanTests(TestCase):
    def test_formats_with_thousands_separator_and_unit(self):
        self.assertEqual(format_toman(1250000), "۱٬۲۵۰٬۰۰۰ تومان")

    def test_without_unit(self):
        self.assertEqual(format_toman(1250000, with_unit=False), "۱٬۲۵۰٬۰۰۰")

    def test_none_returns_empty_string(self):
        self.assertEqual(format_toman(None), "")
