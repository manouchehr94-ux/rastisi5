from django.test import TestCase

from apps.core.utils import format_toman, normalization_key, normalize_digits, normalize_text, to_fa_digits


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

    def test_converts_arabic_indic_digits_to_latin(self):
        self.assertEqual(normalize_digits("٠٩١٢٣"), "09123")

    def test_none_returns_empty_string(self):
        self.assertEqual(normalize_digits(None), "")

    def test_roundtrip_with_to_fa_digits(self):
        self.assertEqual(normalize_digits(to_fa_digits("09121234567")), "09121234567")


class NormalizeTextTests(TestCase):
    def test_converts_persian_and_arabic_digits(self):
        self.assertEqual(normalize_text("۳۰ و ٤٠"), "30 و 40")

    def test_converts_common_arabic_letters_to_persian(self):
        self.assertEqual(normalize_text("مشکي"), "مشکی")
        self.assertEqual(normalize_text("كتاب"), "کتاب")

    def test_collapses_extra_whitespace_and_trims(self):
        self.assertEqual(normalize_text("  سایز    بزرگ  "), "سایز بزرگ")

    def test_none_returns_empty_string(self):
        self.assertEqual(normalize_text(None), "")


class NormalizationKeyTests(TestCase):
    def test_case_insensitive_for_latin_values(self):
        self.assertEqual(normalization_key("Large"), normalization_key("large"))

    def test_digit_and_letter_variants_produce_same_key(self):
        self.assertEqual(normalization_key("۱۲۸ گیگابایت"), normalization_key("128 گيگابايت"))

    def test_whitespace_differences_produce_same_key(self):
        self.assertEqual(normalization_key("سایز  بزرگ"), normalization_key(" سایز بزرگ "))


class FormatTomanTests(TestCase):
    def test_formats_with_thousands_separator_and_unit(self):
        self.assertEqual(format_toman(1250000), "۱٬۲۵۰٬۰۰۰ تومان")

    def test_without_unit(self):
        self.assertEqual(format_toman(1250000, with_unit=False), "۱٬۲۵۰٬۰۰۰")

    def test_none_returns_empty_string(self):
        self.assertEqual(format_toman(None), "")
