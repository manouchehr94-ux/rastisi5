from django.test import TestCase

from apps.storefront_builder.models import StorefrontLayout, StorefrontLayoutVersion, StorefrontSection
from apps.storefront_builder.services import row_service
from apps.stores.models import Store


def _akhlaghi():
    return Store.objects.get(slug="akhlaghi")


class RowGroupingHelperTests(TestCase):
    """``_grouped_by_row_key`` — عمداً از طریقِ ``validate_page_row_layout``
    (رفتارِ قابل‌مشاهده) تست می‌شود، نه فراخوانیِ مستقیمِ تابعِ خصوصی."""

    def setUp(self):
        self.layout = StorefrontLayout.provision_for(_akhlaghi())
        self.version = StorefrontLayoutVersion.objects.create(layout=self.layout, version_number=1)

    def _section(self, order, row_key="", row_span=12, key="rich_text"):
        return StorefrontSection.objects.create(
            version=self.version, section_key=key, order=order, row_key=row_key, row_span=row_span,
        )


class ValidatePageRowLayoutTests(RowGroupingHelperTests):
    def test_sections_without_row_key_always_valid(self):
        self._section(0)
        self._section(1)
        row_service.validate_page_row_layout(self.version.sections.order_by("order"))  # no raise

    def test_two_thirds_one_third_row_is_valid(self):
        """دقیقاً ترکیبِ Hero (۸) + Instant Offer (۴) در V5."""
        self._section(0, row_key="hero-row", row_span=8)
        self._section(1, row_key="hero-row", row_span=4)
        row_service.validate_page_row_layout(self.version.sections.order_by("order"))  # no raise

    def test_four_equal_columns_row_is_valid(self):
        for i in range(4):
            self._section(i, row_key="banner-row", row_span=3)
        row_service.validate_page_row_layout(self.version.sections.order_by("order"))  # no raise

    def test_single_member_row_rejected(self):
        self._section(0, row_key="lonely-row", row_span=12)
        with self.assertRaises(row_service.RowAssignmentError):
            row_service.validate_page_row_layout(self.version.sections.order_by("order"))

    def test_five_member_row_rejected(self):
        for i in range(5):
            self._section(i, row_key="crowded-row", row_span=2 if i < 4 else 4)
        with self.assertRaises(row_service.RowAssignmentError):
            row_service.validate_page_row_layout(self.version.sections.order_by("order"))

    def test_spans_not_summing_to_twelve_rejected(self):
        self._section(0, row_key="short-row", row_span=4)
        self._section(1, row_key="short-row", row_span=4)
        with self.assertRaises(row_service.RowAssignmentError):
            row_service.validate_page_row_layout(self.version.sections.order_by("order"))

    def test_span_out_of_range_rejected(self):
        """۱۳ خارج از بازه‌ی مجاز (۱ تا ۱۲) است — عمداً از عددِ منفی استفاده
        نمی‌شود، چون ``PositiveSmallIntegerField`` خودش سطحِ دیتابیس مقدارِ
        منفی را رد می‌کند؛ این تست دقیقاً محدوده‌ی *معناییِ* ۱ تا ۱۲ را چک
        می‌کند، نه محدودیتِ نوعِ ستون."""
        self._section(0, row_key="bad-row", row_span=13)
        self._section(1, row_key="bad-row", row_span=0)
        with self.assertRaises(row_service.RowAssignmentError):
            row_service.validate_page_row_layout(self.version.sections.order_by("order"))

    def test_non_contiguous_same_row_key_rejected(self):
        """اگر بخشِ دیگری (بدونِ آن row_key) بینِ دو عضو قرار بگیرد، دیگر از
        نظرِ بصری یک ردیفِ واحد نیست."""
        self._section(0, row_key="split-row", row_span=6)
        self._section(1)  # standalone section wedged in the middle
        self._section(2, row_key="split-row", row_span=6)
        with self.assertRaises(row_service.RowAssignmentError):
            row_service.validate_page_row_layout(self.version.sections.order_by("order"))

    def test_two_independent_rows_on_same_page_both_valid(self):
        self._section(0, row_key="row-a", row_span=6)
        self._section(1, row_key="row-a", row_span=6)
        self._section(2, row_key="row-b", row_span=4)
        self._section(3, row_key="row-b", row_span=4)
        self._section(4, row_key="row-b", row_span=4)
        row_service.validate_page_row_layout(self.version.sections.order_by("order"))  # no raise


class IsRowMemberTests(RowGroupingHelperTests):
    def test_empty_row_key_is_not_a_member(self):
        section = self._section(0)
        self.assertFalse(row_service.is_row_member(section))

    def test_nonempty_row_key_is_a_member(self):
        section = self._section(0, row_key="x", row_span=6)
        self.assertTrue(row_service.is_row_member(section))
