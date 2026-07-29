"""Tests for the checkpoint 4B CSV-import utilities added to
``apps.core.services.csv_utils``: safe upload validation, bounded/streaming
row parsing, and Persian-digit/Decimal/boolean value normalization."""

import io
from decimal import Decimal
from types import SimpleNamespace

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase

from apps.core.services.csv_utils import (
    CsvRowLimitExceededError,
    CsvUploadError,
    parse_import_bool,
    parse_import_decimal,
    parse_import_int,
    read_csv_rows_bounded,
    validate_csv_upload,
)


class ValidateCsvUploadTests(SimpleTestCase):
    def _upload(self, name="file.csv", content=b"a,b\n1,2\n", content_type="text/csv", size=None):
        upload = SimpleUploadedFile(name, content, content_type=content_type)
        if size is not None:
            upload.size = size
        return upload

    def test_valid_csv_passes(self):
        validate_csv_upload(self._upload())

    def test_non_csv_extension_rejected(self):
        with self.assertRaises(CsvUploadError):
            validate_csv_upload(self._upload(name="file.xlsx"))

    def test_path_traversal_filename_rejected(self):
        # Django's own UploadedFile already strips directory components from
        # ``.name`` (SimpleUploadedFile normalizes this before our code ever
        # sees it) — a plain namespace exercises validate_csv_upload's own
        # defense directly, as defense-in-depth for any caller that doesn't
        # go through Django's multipart upload parser.
        upload = SimpleNamespace(name="../../etc/passwd.csv", size=10, content_type="text/csv")
        with self.assertRaises(CsvUploadError):
            validate_csv_upload(upload)

    def test_null_byte_in_filename_rejected(self):
        upload = SimpleNamespace(name="file\x00.exe.csv", size=10, content_type="text/csv")
        with self.assertRaises(CsvUploadError):
            validate_csv_upload(upload)

    def test_oversized_file_rejected(self):
        with self.assertRaises(CsvUploadError):
            validate_csv_upload(self._upload(size=999_999_999))

    def test_disallowed_content_type_rejected(self):
        with self.assertRaises(CsvUploadError):
            validate_csv_upload(self._upload(content_type="application/x-msdownload"))


class ReadCsvRowsBoundedTests(SimpleTestCase):
    def _stream(self, text: str):
        return io.BytesIO(text.encode("utf-8"))

    def test_reads_rows_with_bom(self):
        content = "﻿name,sku\nکالا۱,SKU1\n".encode("utf-8")
        rows = list(read_csv_rows_bounded(io.BytesIO(content)))
        self.assertEqual(rows, [{"name": "کالا۱", "sku": "SKU1"}])

    def test_row_limit_enforced(self):
        rows = "a\n" + "".join(f"{i}\n" for i in range(5))
        with self.assertRaises(CsvRowLimitExceededError):
            list(read_csv_rows_bounded(self._stream(rows), max_rows=3))

    def test_field_length_truncated(self):
        long_value = "x" * 50
        content = f"a\n{long_value}\n"
        rows = list(read_csv_rows_bounded(self._stream(content), max_field_length=10))
        self.assertEqual(len(rows[0]["a"]), 10)

    def test_null_bytes_stripped(self):
        content = "a\nvalue\x00with\x00nulls\n"
        rows = list(read_csv_rows_bounded(self._stream(content)))
        self.assertEqual(rows[0]["a"], "valuewithnulls")

    def test_empty_row_produces_none_values(self):
        content = "a,b\n1,\n"
        rows = list(read_csv_rows_bounded(self._stream(content)))
        self.assertEqual(rows[0]["b"], "")


class ParseImportDecimalTests(SimpleTestCase):
    def test_plain_decimal(self):
        self.assertEqual(parse_import_decimal("150000"), Decimal("150000"))

    def test_persian_digits_normalized(self):
        self.assertEqual(parse_import_decimal("۱۵۰۰۰۰"), Decimal("150000"))

    def test_empty_returns_none(self):
        self.assertIsNone(parse_import_decimal(""))
        self.assertIsNone(parse_import_decimal(None))

    def test_invalid_decimal_raises(self):
        with self.assertRaises(ValueError):
            parse_import_decimal("not-a-number")


class ParseImportIntTests(SimpleTestCase):
    def test_plain_int(self):
        self.assertEqual(parse_import_int("42"), 42)

    def test_arabic_digits_normalized(self):
        self.assertEqual(parse_import_int("٤٢"), 42)

    def test_invalid_int_raises(self):
        with self.assertRaises(ValueError):
            parse_import_int("abc")


class ParseImportBoolTests(SimpleTestCase):
    def test_persian_true_values(self):
        self.assertTrue(parse_import_bool("بله"))
        self.assertTrue(parse_import_bool("فعال"))

    def test_persian_false_values(self):
        self.assertFalse(parse_import_bool("خیر"))
        self.assertFalse(parse_import_bool("غیرفعال"))

    def test_english_values(self):
        self.assertTrue(parse_import_bool("true"))
        self.assertFalse(parse_import_bool("false"))

    def test_empty_uses_default(self):
        self.assertTrue(parse_import_bool("", default=True))

    def test_empty_without_default_raises(self):
        with self.assertRaises(ValueError):
            parse_import_bool("")

    def test_unrecognized_value_raises(self):
        with self.assertRaises(ValueError):
            parse_import_bool("maybe")
