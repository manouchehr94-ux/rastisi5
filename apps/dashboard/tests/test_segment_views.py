"""View-level tests for the Customer Segment Merchant Admin UI: create/edit
with the rule builder, static membership add/remove, refresh, permissions,
and adversarial tenant isolation."""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.catalog.models import Vendor
from apps.customers.models import Customer, CustomerSegment, CustomerSegmentMembership
from apps.orders.models import Order, PaymentGateway, ShippingMethod
from apps.stores.models import Store, StoreMembership

User = get_user_model()

HOST = "seg-view-test.rastisi.ir"


def _akhlaghi():
    return Store.objects.get(slug="akhlaghi")


@override_settings(ALLOWED_HOSTS=[HOST, "testserver"])
class SegmentViewsTestCase(TestCase):
    def setUp(self):
        self.client = Client(HTTP_HOST=HOST)
        self.store = _akhlaghi()
        self.store.admin_subdomain = "seg-view-test"
        self.store.save(update_fields=["admin_subdomain"])

        self.vendor = Vendor.objects.create(store=self.store, name="فروشگاه", slug="shop-segv")
        self.shipping = ShippingMethod.objects.create(store=self.store, name="پست", slug="post-segv")
        self.gateway = PaymentGateway.objects.create(store=self.store, name="د", slug="gw-segv")

        user = User.objects.create_user(username="09121210001", password="p")
        self.customer = Customer.objects.create(user=user, full_name="مشتریِ سگمنت", phone="09121210001")
        Order.objects.create(
            code="DM-segv-1", store=self.store, customer=self.customer, vendor=self.vendor, address={},
            shipping_method=self.shipping, payment_gateway=self.gateway,
            grand_total=Decimal("300000"), payment_status=Order.PaymentStatus.PAID,
        )

        self.owner = User.objects.create_user(username="seg-owner", password="pass12345", is_staff=True)
        StoreMembership.objects.create(
            store=self.store, user=self.owner, role=StoreMembership.Role.OWNER,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )
        self.client.login(username="seg-owner", password="pass12345")

    def _login_as(self, role, suffix):
        user = User.objects.create_user(username=f"seg-role-{suffix}", password="pass12345", is_staff=True)
        StoreMembership.objects.create(
            store=self.store, user=user, role=role,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )
        self.client.logout()
        self.client.login(username=user.username, password="pass12345")


class SegmentCrudViewTests(SegmentViewsTestCase):
    def test_create_static_segment(self):
        response = self.client.post(reverse("dashboard:segment-add"), {
            "name": "مشتریانِ VIP", "description": "دستی", "segment_type": "static", "match_mode": "all",
        })
        self.assertEqual(response.status_code, 302)
        self.assertTrue(CustomerSegment.objects.filter(store=self.store, name="مشتریانِ VIP").exists())

    def test_create_dynamic_segment_with_rule(self):
        response = self.client.post(reverse("dashboard:segment-add"), {
            "name": "خریدارانِ بزرگ", "segment_type": "dynamic", "match_mode": "all",
            "rule_field": ["total_spent"], "rule_operator": ["greater_than"], "rule_value": ["100000"], "rule_value2": [""],
        })
        self.assertEqual(response.status_code, 302)
        segment = CustomerSegment.objects.get(store=self.store, name="خریدارانِ بزرگ")
        self.assertEqual(segment.rules.count(), 1)

    def test_invalid_rule_operator_shows_error_without_saving_rules(self):
        response = self.client.post(reverse("dashboard:segment-add"), {
            "name": "نامعتبر", "segment_type": "dynamic", "match_mode": "all",
            "rule_field": ["total_spent"], "rule_operator": ["contains"], "rule_value": ["1"], "rule_value2": [""],
        })
        self.assertEqual(response.status_code, 200)
        segment = CustomerSegment.objects.get(store=self.store, name="نامعتبر")
        self.assertEqual(segment.rules.count(), 0)

    def test_analyst_can_view_but_not_create(self):
        self._login_as(StoreMembership.Role.ANALYST, "1")
        response = self.client.get(reverse("dashboard:segment-list"))
        self.assertEqual(response.status_code, 200)
        response = self.client.post(reverse("dashboard:segment-add"), {"name": "x", "segment_type": "static", "match_mode": "all"})
        self.assertEqual(response.status_code, 403)

    def test_content_editor_cannot_view(self):
        self._login_as(StoreMembership.Role.CONTENT_EDITOR, "2")
        response = self.client.get(reverse("dashboard:segment-list"))
        self.assertEqual(response.status_code, 403)


class SegmentDetailAndMembershipTests(SegmentViewsTestCase):
    def test_static_segment_add_and_remove_member(self):
        segment = CustomerSegment.objects.create(store=self.store, name="دستی", segment_type="static")
        response = self.client.post(
            reverse("dashboard:segment-member-add", args=[segment.pk]), {"phone": self.customer.phone},
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(CustomerSegmentMembership.objects.filter(segment=segment, customer=self.customer).exists())

        response = self.client.post(reverse("dashboard:segment-member-remove", args=[segment.pk, self.customer.pk]))
        self.assertEqual(response.status_code, 302)
        self.assertFalse(CustomerSegmentMembership.objects.filter(segment=segment, customer=self.customer).exists())

    def test_dynamic_segment_refresh(self):
        segment = CustomerSegment.objects.create(store=self.store, name="پویا", segment_type="dynamic")
        segment.rules.create(field="total_spent", operator="greater_than", value="0")
        response = self.client.post(reverse("dashboard:segment-refresh", args=[segment.pk]))
        self.assertEqual(response.status_code, 302)
        segment.refresh_from_db()
        self.assertIsNotNone(segment.last_evaluated_at)
        self.assertEqual(segment.memberships.count(), 1)

    def test_detail_page_renders(self):
        segment = CustomerSegment.objects.create(store=self.store, name="نمایش", segment_type="static")
        response = self.client.get(reverse("dashboard:segment-detail", args=[segment.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "نمایش")


class SegmentTenantIsolationTests(SegmentViewsTestCase):
    def setUp(self):
        super().setUp()
        self.other_store = Store.objects.create(name="فروشگاه دیگر", slug="seg-other-store-view")
        self.other_segment = CustomerSegment.objects.create(store=self.other_store, name="خارجی", segment_type="static")

    def test_cannot_view_other_stores_segment(self):
        response = self.client.get(reverse("dashboard:segment-detail", args=[self.other_segment.pk]))
        self.assertEqual(response.status_code, 404)

    def test_cannot_edit_other_stores_segment(self):
        response = self.client.get(reverse("dashboard:segment-edit", args=[self.other_segment.pk]))
        self.assertEqual(response.status_code, 404)

    def test_cannot_refresh_other_stores_segment(self):
        response = self.client.post(reverse("dashboard:segment-refresh", args=[self.other_segment.pk]))
        self.assertEqual(response.status_code, 404)

    def test_cannot_add_member_to_other_stores_segment(self):
        response = self.client.post(
            reverse("dashboard:segment-member-add", args=[self.other_segment.pk]), {"phone": self.customer.phone},
        )
        self.assertEqual(response.status_code, 404)

    def test_segment_list_only_shows_own_store(self):
        response = self.client.get(reverse("dashboard:segment-list"))
        names = [s.name for s in response.context["segments"]]
        self.assertNotIn("خارجی", names)
