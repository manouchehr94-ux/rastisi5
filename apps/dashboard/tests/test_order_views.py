from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.db import connection
from django.urls import reverse

from apps.catalog.models import Vendor
from apps.customers.models import Customer
from django.utils import timezone

from apps.orders.models import Order, OrderItem, PaymentGateway, ShippingMethod
from apps.orders.services.order_service import change_order_status
from apps.stores.models import Store, StoreMembership

User = get_user_model()


def _akhlaghi():
    return Store.objects.get(slug="akhlaghi")


class OrderViewsTestCase(TestCase):
    def setUp(self):
        self.store = _akhlaghi()
        user = User.objects.create_user(username="09121140001", password="pass12345")
        self.customer = Customer.objects.create(user=user, full_name="نگار مرادی", phone="09121140001")
        self.vendor = Vendor.objects.create(store=self.store, name="فروشگاه", slug="shop-ov")
        self.shipping = ShippingMethod.objects.create(store=self.store, name="پست", slug="post-ov", cost=Decimal("45000"))
        self.gateway = PaymentGateway.objects.create(store=self.store, name="زرین‌پال", slug="zarin-ov")
        self.order = Order.objects.create(
            code="DM-77777", store=self.store, customer=self.customer, vendor=self.vendor,
            address={"province": "تهران", "city": "تهران", "full_address": "خیابان ولیعصر"},
            shipping_method=self.shipping, payment_gateway=self.gateway,
            items_total=Decimal("100000"), grand_total=Decimal("109000"), tax=Decimal("9000"),
        )
        self.staff = User.objects.create_user(username="09121140099", password="pass12345", is_staff=True)
        StoreMembership.objects.create(
            store=self.store, user=self.staff, role=StoreMembership.Role.OWNER,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )
        self.client.login(username="09121140099", password="pass12345")


class OrderListViewTests(OrderViewsTestCase):
    def test_renders_order_table(self):
        response = self.client.get(reverse("dashboard:order-list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "DM-77777")
        self.assertContains(response, "نگار مرادی")

    def test_anonymous_denied(self):
        self.client.logout()
        response = self.client.get(reverse("dashboard:order-list"))
        self.assertEqual(response.status_code, 302)
        self.assertNotIn("/admin-portal/login/", response.url)
        self.assertIn("admin_return=", response.url)
    def test_status_filter(self):
        change_order_status(self.order, Order.Status.PROCESSING, store=self.store)
        response = self.client.get(reverse("dashboard:order-table"), {"status": Order.Status.PENDING})
        self.assertNotContains(response, "DM-77777")

    def test_search_by_code(self):
        response = self.client.get(reverse("dashboard:order-table"), {"q": "77777"})
        self.assertContains(response, "DM-77777")


class OrderDetailViewTests(OrderViewsTestCase):
    def test_shows_order_items_and_address(self):
        response = self.client.get(reverse("dashboard:order-detail", args=[self.order.code]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "خیابان ولیعصر")

    def test_shows_ordered_variant_label(self):
        """پنلِ فروشنده هم باید تنوعِ سفارش‌داده‌شده (مثلاً «کشور سازنده:
        ایتالیایی») را کنارِ نامِ کالا نشان دهد، نه فقط خودِ کالا را."""
        from apps.orders.models import OrderItem

        OrderItem.objects.create(
            order=self.order, product_name="قیچی", variant_label="کشور سازنده: ایتالیایی",
            quantity=1, unit_price=Decimal("800000"), line_total=Decimal("800000"),
        )
        response = self.client.get(reverse("dashboard:order-detail", args=[self.order.code]))
        self.assertContains(response, "کشور سازنده: ایتالیایی")

    def test_shows_status_change_form_for_non_final_order(self):
        response = self.client.get(reverse("dashboard:order-detail", args=[self.order.code]))
        self.assertContains(response, "ثبت تغییرات")

    def test_valid_status_change_redirects_and_updates(self):
        response = self.client.post(
            reverse("dashboard:order-detail", args=[self.order.code]), {"status": Order.Status.PROCESSING}
        )
        self.assertRedirects(response, reverse("dashboard:order-detail", args=[self.order.code]))
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.PROCESSING)
        self.assertEqual(self.order.status_history.count(), 1)

    def test_invalid_status_transition_shows_error_without_changing_status(self):
        response = self.client.post(
            reverse("dashboard:order-detail", args=[self.order.code]), {"status": Order.Status.DELIVERED}
        )
        self.assertEqual(response.status_code, 200)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.PENDING)
        self.assertContains(response, "مجاز نیست")

    def test_shipping_with_tracking_code_saves_it_on_order(self):
        change_order_status(self.order, Order.Status.PROCESSING, store=self.store)
        response = self.client.post(
            reverse("dashboard:order-detail", args=[self.order.code]),
            {"status": Order.Status.SHIPPED, "tracking_code": "TRACK-ABC123"},
        )
        self.assertRedirects(response, reverse("dashboard:order-detail", args=[self.order.code]))
        self.order.refresh_from_db()
        self.assertEqual(self.order.tracking_code, "TRACK-ABC123")

    def test_final_order_hides_status_change_form(self):
        change_order_status(self.order, Order.Status.CANCELED, store=self.store)
        response = self.client.get(reverse("dashboard:order-detail", args=[self.order.code]))
        self.assertNotContains(response, "ثبت تغییرات")

    def test_status_history_displayed(self):
        change_order_status(self.order, Order.Status.PROCESSING, note="بررسی شد", store=self.store)
        response = self.client.get(reverse("dashboard:order-detail", args=[self.order.code]))
        self.assertContains(response, "بررسی شد")

    def test_anonymous_denied(self):
        self.client.logout()
        response = self.client.get(reverse("dashboard:order-detail", args=[self.order.code]))
        self.assertEqual(response.status_code, 302)
        self.assertNotIn("/admin-portal/login/", response.url)
        self.assertIn("admin_return=", response.url)
    def test_404_for_unknown_code(self):
        response = self.client.get(reverse("dashboard:order-detail", args=["DM-00000"]))
        self.assertEqual(response.status_code, 404)


class OrderListPerformanceTests(OrderViewsTestCase):
    """Phase 2 — the order list used to (a) render the *entire* Store order
    history unpaginated, and (b) run a separate ``order.items.count()``
    query per rendered row (N+1). Both are fixed via
    ``_order_list_context``'s ``Paginator`` and ``filtered_orders``'
    ``items_count`` annotation. These tests prove the fix with query-count
    evidence rather than trusting the diff — see
    ``apps.dashboard.services.orders_admin_service.filtered_orders``.

    Fixture size: this class creates its own additional orders (25, each
    with 2 items) on top of the single order from ``OrderViewsTestCase.
    setUp`` — 26 total, comfortably past ``ORDERS_PER_PAGE`` (20), so the
    list must actually paginate, not merely stay small enough to dodge the
    old N+1 by accident."""

    def _create_orders(self, count, items_per_order=2):
        for i in range(count):
            order = Order.objects.create(
                code=f"DM-PERF{i:04d}", store=self.store, customer=self.customer, vendor=self.vendor,
                address={"province": "تهران", "city": "تهران", "full_address": "خیابان ولیعصر"},
                shipping_method=self.shipping, payment_gateway=self.gateway,
                items_total=Decimal("100000"), grand_total=Decimal("109000"), tax=Decimal("9000"),
            )
            for j in range(items_per_order):
                OrderItem.objects.create(
                    order=order, product_name=f"کالای {i}-{j}", quantity=1,
                    unit_price=Decimal("50000"), line_total=Decimal("50000"),
                )

    def test_query_count_does_not_grow_with_order_or_item_count(self):
        """The regression this guards against: query count must stay the
        same whether the page has 1 order with 0 items or many orders each
        with several items — proving items_count is a single annotated
        query, not one COUNT per row."""
        with CaptureQueriesContext(connection) as small:
            self.client.get(reverse("dashboard:order-table"))
        self._create_orders(25, items_per_order=3)
        with CaptureQueriesContext(connection) as large:
            self.client.get(reverse("dashboard:order-table"))
        self.assertEqual(
            len(small.captured_queries), len(large.captured_queries),
            "order-table query count must not grow with order/item count "
            f"(small={len(small.captured_queries)}, large={len(large.captured_queries)})",
        )

    def test_order_list_is_paginated_not_unbounded(self):
        """26 total orders (1 from setUp + 25 created here), ORDERS_PER_PAGE
        = 20 — the first page must show exactly 20, not all 26, and a
        "next page" control must be present."""
        self._create_orders(25)
        response = self.client.get(reverse("dashboard:order-list"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["page_obj"].object_list), 20)
        self.assertEqual(response.context["paginator"].count, 26)
        self.assertContains(response, "بعدی")

    def test_second_page_reachable_and_shows_remaining_orders(self):
        self._create_orders(25)
        response = self.client.get(reverse("dashboard:order-table"), {"page": 2})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["page_obj"].object_list), 6)

    def test_items_count_annotation_matches_actual_item_count(self):
        """Correctness, not just query count: the annotated value must
        still be the right number."""
        OrderItem.objects.create(
            order=self.order, product_name="قیچی", quantity=1,
            unit_price=Decimal("800000"), line_total=Decimal("800000"),
        )
        OrderItem.objects.create(
            order=self.order, product_name="چاقو", quantity=2,
            unit_price=Decimal("400000"), line_total=Decimal("800000"),
        )
        response = self.client.get(reverse("dashboard:order-table"))
        rendered_order = next(
            o for o in response.context["page_obj"].object_list if o.pk == self.order.pk
        )
        self.assertEqual(rendered_order.items_count, 2)
