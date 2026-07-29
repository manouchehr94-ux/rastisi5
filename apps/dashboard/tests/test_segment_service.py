"""Tests for the Checkpoint 4 Customer Segment rule engine
(``apps.dashboard.services.segment_service``): field/operator allowlisting,
each supported field's DB-query-based matching, match-all/match-any
combination, static-segment manual membership, and tenant isolation."""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.catalog.models import Brand, Category, Product, Vendor
from apps.customers.models import Customer, CustomerSegment, CustomerSegmentRule, CustomerTag, CustomerProfile
from apps.dashboard.services import customer_crm_service, segment_service
from apps.orders.models import Order, OrderItem, PaymentGateway, ShippingMethod
from apps.stores.models import Store

User = get_user_model()


def _akhlaghi():
    return Store.objects.get(slug="akhlaghi")


class SegmentServiceTestCase(TestCase):
    def setUp(self):
        self.store = _akhlaghi()
        self.vendor = Vendor.objects.create(store=self.store, name="فروشگاه", slug="shop-seg")
        self.category = Category.objects.create(store=self.store, name="دسته", slug="cat-seg")
        self.product = Product.objects.create(
            store=self.store, vendor=self.vendor, category=self.category,
            name="کالای سگمنت", slug="seg-product", sku="SKU-SEG-1", price=Decimal("200000"), stock=10,
        )
        self.shipping = ShippingMethod.objects.create(store=self.store, name="پست", slug="post-seg")
        self.gateway = PaymentGateway.objects.create(store=self.store, name="د", slug="gw-seg")

        self.big_spender_user = User.objects.create_user(username="09121200001", password="p")
        self.big_spender = Customer.objects.create(user=self.big_spender_user, full_name="خریدارِ بزرگ", phone="09121200001")
        order = Order.objects.create(
            code="DM-seg-1", store=self.store, customer=self.big_spender, vendor=self.vendor, address={},
            shipping_method=self.shipping, payment_gateway=self.gateway,
            grand_total=Decimal("1000000"), payment_status=Order.PaymentStatus.PAID,
        )
        OrderItem.objects.create(
            order=order, product=self.product, product_name=self.product.name,
            quantity=1, unit_price=Decimal("1000000"), line_total=Decimal("1000000"),
        )

        self.small_spender_user = User.objects.create_user(username="09121200002", password="p")
        self.small_spender = Customer.objects.create(user=self.small_spender_user, full_name="خریدارِ کوچک", phone="09121200002")
        Order.objects.create(
            code="DM-seg-2", store=self.store, customer=self.small_spender, vendor=self.vendor, address={},
            shipping_method=self.shipping, payment_gateway=self.gateway,
            grand_total=Decimal("50000"), payment_status=Order.PaymentStatus.PAID,
        )

    def _dynamic_segment(self, *, match_mode=CustomerSegment.MatchMode.ALL):
        return CustomerSegment.objects.create(
            store=self.store, name="سگمنتِ تست", segment_type=CustomerSegment.SegmentType.DYNAMIC,
            match_mode=match_mode,
        )


class FieldValidationTests(SegmentServiceTestCase):
    def test_unknown_field_rejected(self):
        segment = self._dynamic_segment()
        rule = CustomerSegmentRule.objects.create(segment=segment, field="not_a_real_field", operator="equals", value="1")
        with self.assertRaises(segment_service.SegmentError):
            segment_service.evaluate_segment(segment)

    def test_operator_not_allowed_for_field_rejected(self):
        segment = self._dynamic_segment()
        rule = CustomerSegmentRule.objects.create(segment=segment, field="order_count", operator="contains", value="1")
        with self.assertRaises(segment_service.SegmentError):
            segment_service.evaluate_segment(segment)


class TotalSpentRuleTests(SegmentServiceTestCase):
    def test_greater_than_matches_big_spender_only(self):
        segment = self._dynamic_segment()
        CustomerSegmentRule.objects.create(segment=segment, field="total_spent", operator="greater_than", value="500000")
        ids = segment_service.evaluate_segment(segment)
        self.assertEqual(ids, {self.big_spender.pk})

    def test_less_than_matches_small_spender_only(self):
        segment = self._dynamic_segment()
        CustomerSegmentRule.objects.create(segment=segment, field="total_spent", operator="less_than", value="500000")
        ids = segment_service.evaluate_segment(segment)
        self.assertEqual(ids, {self.small_spender.pk})


class HasPurchasedProductRuleTests(SegmentServiceTestCase):
    def test_matches_only_customer_who_bought_that_product(self):
        segment = self._dynamic_segment()
        CustomerSegmentRule.objects.create(
            segment=segment, field="has_purchased_product", operator="contains", value=str(self.product.pk),
        )
        ids = segment_service.evaluate_segment(segment)
        self.assertEqual(ids, {self.big_spender.pk})


class CustomerTagRuleTests(SegmentServiceTestCase):
    def test_matches_customer_with_tag(self):
        tag = CustomerTag.objects.create(store=self.store, name="VIP", code="vip-seg")
        customer_crm_service.bulk_add_tag(self.store, [self.big_spender.pk], tag.pk)
        segment = self._dynamic_segment()
        CustomerSegmentRule.objects.create(segment=segment, field="customer_tag", operator="in", value=str(tag.pk))
        ids = segment_service.evaluate_segment(segment)
        self.assertEqual(ids, {self.big_spender.pk})

    def test_tag_from_other_store_never_matches(self):
        other_store = Store.objects.create(name="فروشگاه دیگر", slug="seg-other-store")
        other_tag = CustomerTag.objects.create(store=other_store, name="خارجی", code="foreign-seg")
        segment = self._dynamic_segment()
        CustomerSegmentRule.objects.create(segment=segment, field="customer_tag", operator="in", value=str(other_tag.pk))
        ids = segment_service.evaluate_segment(segment)
        self.assertEqual(ids, set())


class MatchModeTests(SegmentServiceTestCase):
    def test_match_all_intersects(self):
        segment = self._dynamic_segment(match_mode=CustomerSegment.MatchMode.ALL)
        CustomerSegmentRule.objects.create(segment=segment, field="total_spent", operator="greater_than", value="0")
        CustomerSegmentRule.objects.create(
            segment=segment, field="has_purchased_product", operator="contains", value=str(self.product.pk),
        )
        ids = segment_service.evaluate_segment(segment)
        self.assertEqual(ids, {self.big_spender.pk})

    def test_match_any_unions(self):
        segment = self._dynamic_segment(match_mode=CustomerSegment.MatchMode.ANY)
        CustomerSegmentRule.objects.create(segment=segment, field="total_spent", operator="greater_than", value="500000")
        CustomerSegmentRule.objects.create(segment=segment, field="total_spent", operator="less_than", value="100000")
        ids = segment_service.evaluate_segment(segment)
        self.assertEqual(ids, {self.big_spender.pk, self.small_spender.pk})


class RefreshMembershipTests(SegmentServiceTestCase):
    def test_refresh_materializes_membership_and_stamps_evaluation_metadata(self):
        segment = self._dynamic_segment()
        CustomerSegmentRule.objects.create(segment=segment, field="total_spent", operator="greater_than", value="500000")
        count = segment_service.refresh_segment_membership(segment)
        segment.refresh_from_db()
        self.assertEqual(count, 1)
        self.assertEqual(segment.memberships.count(), 1)
        self.assertIsNotNone(segment.last_evaluated_at)
        self.assertIsNotNone(segment.last_evaluation_duration_ms)

    def test_refresh_removes_members_no_longer_matching(self):
        segment = self._dynamic_segment()
        CustomerSegmentRule.objects.create(segment=segment, field="total_spent", operator="greater_than", value="500000")
        segment_service.refresh_segment_membership(segment)
        self.assertEqual(segment.memberships.count(), 1)

        rule = segment.rules.first()
        rule.value = "50000000"
        rule.save()
        segment_service.refresh_segment_membership(segment)
        self.assertEqual(segment.memberships.count(), 0)


class StaticSegmentTests(SegmentServiceTestCase):
    def test_add_and_remove_static_member(self):
        segment = CustomerSegment.objects.create(
            store=self.store, name="دستی", segment_type=CustomerSegment.SegmentType.STATIC,
        )
        added = segment_service.add_static_member(segment, self.big_spender.pk)
        self.assertTrue(added)
        self.assertEqual(segment.memberships.count(), 1)
        removed = segment_service.remove_static_member(segment, self.big_spender.pk)
        self.assertTrue(removed)
        self.assertEqual(segment.memberships.count(), 0)

    def test_cannot_add_customer_with_no_orders_in_store(self):
        stranger_user = User.objects.create_user(username="09121200099", password="p")
        stranger = Customer.objects.create(user=stranger_user, full_name="غریبه", phone="09121200099")
        segment = CustomerSegment.objects.create(
            store=self.store, name="دستی", segment_type=CustomerSegment.SegmentType.STATIC,
        )
        added = segment_service.add_static_member(segment, stranger.pk)
        self.assertFalse(added)
        self.assertEqual(segment.memberships.count(), 0)

    def test_refresh_is_noop_for_static_segment(self):
        segment = CustomerSegment.objects.create(
            store=self.store, name="دستی", segment_type=CustomerSegment.SegmentType.STATIC,
        )
        segment_service.add_static_member(segment, self.big_spender.pk)
        count = segment_service.refresh_segment_membership(segment)
        self.assertEqual(count, 1)
        self.assertEqual(segment.memberships.count(), 1)
