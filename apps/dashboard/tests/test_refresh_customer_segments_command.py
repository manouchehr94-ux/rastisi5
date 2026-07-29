from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from apps.customers.models import CustomerSegment
from apps.stores.models import Store


def _akhlaghi():
    return Store.objects.get(slug="akhlaghi")


class RefreshCustomerSegmentsCommandTests(TestCase):
    def setUp(self):
        self.store = _akhlaghi()

    def test_refreshes_dynamic_segments_and_stamps_evaluation(self):
        segment = CustomerSegment.objects.create(
            store=self.store, name="پویا", segment_type=CustomerSegment.SegmentType.DYNAMIC,
        )
        segment.rules.create(field="order_count", operator="greater_than_or_equal", value="0")
        out = StringIO()
        call_command("refresh_customer_segments", stdout=out)
        segment.refresh_from_db()
        self.assertIsNotNone(segment.last_evaluated_at)
        self.assertIn("1 سگمنت تازه‌سازی شد", out.getvalue())

    def test_static_segments_are_not_touched(self):
        segment = CustomerSegment.objects.create(
            store=self.store, name="دستی", segment_type=CustomerSegment.SegmentType.STATIC,
        )
        out = StringIO()
        call_command("refresh_customer_segments", stdout=out)
        segment.refresh_from_db()
        self.assertIsNone(segment.last_evaluated_at)

    def test_inactive_segments_are_skipped(self):
        segment = CustomerSegment.objects.create(
            store=self.store, name="غیرفعال", segment_type=CustomerSegment.SegmentType.DYNAMIC, is_active=False,
        )
        call_command("refresh_customer_segments", stdout=StringIO())
        segment.refresh_from_db()
        self.assertIsNone(segment.last_evaluated_at)

    def test_store_filter_only_refreshes_that_store(self):
        other_store = Store.objects.create(name="فروشگاه دیگر", slug="refresh-seg-other-store")
        other_segment = CustomerSegment.objects.create(
            store=other_store, name="دیگری", segment_type=CustomerSegment.SegmentType.DYNAMIC,
        )
        call_command("refresh_customer_segments", "--store", self.store.slug, stdout=StringIO())
        other_segment.refresh_from_db()
        self.assertIsNone(other_segment.last_evaluated_at)

    def test_unknown_store_slug_errors_without_crash(self):
        err = StringIO()
        call_command("refresh_customer_segments", "--store", "no-such-store-slug", stderr=err)
        self.assertIn("یافت نشد", err.getvalue())
