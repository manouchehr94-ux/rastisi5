from decimal import Decimal

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.catalog.models import Category, Product, Vendor
from apps.customers.models import Customer
from apps.orders.models import (
    Order, OrderItem, PaymentGateway, Refund, ReturnRequest, ShippingMethod,
)
from apps.orders.services.return_service import create_return_request
from apps.stores.models import Store, StoreMembership

User = get_user_model()

HOST = f"return-test.{settings.RASTISI_ADMIN_DOMAIN_SUFFIX}"


def _akhlaghi():
    return Store.objects.get(slug="akhlaghi")


@override_settings(ALLOWED_HOSTS=[HOST, "testserver"])
class ReturnRefundViewsTestCase(TestCase):
    def setUp(self):
        self.store = _akhlaghi()
        self.store.admin_subdomain = HOST.split(".")[0]
        self.store.save(update_fields=["admin_subdomain"])
        self.owner = User.objects.create_user(username="09125500001", password="pass12345", is_staff=True)
        StoreMembership.objects.create(
            store=self.store, user=self.owner, role=StoreMembership.Role.OWNER,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )
        self.user = User.objects.create_user(username="09125500002", password="pass12345")
        self.customer = Customer.objects.create(user=self.user, full_name="یاسمن کریمی", phone="09125500002")
        self.vendor = Vendor.objects.create(store=self.store, name="فروشگاه", slug="shop-rrv")
        self.category = Category.objects.create(store=self.store, name="دیجیتال", slug="digital-rrv")
        self.product = Product.objects.create(
            store=self.store, vendor=self.vendor, category=self.category, name="تبلت", slug="tablet-rrv",
            sku="SKU-RRV1", price=Decimal("2000000"), stock=10,
        )
        self.shipping = ShippingMethod.objects.create(store=self.store, name="پست", slug="post-rrv", cost=Decimal("50000"))
        self.gateway = PaymentGateway.objects.create(store=self.store, name="زرین‌پال", slug="zarin-rrv")
        self.order = Order.objects.create(
            code="DM-RRV1", store=self.store, customer=self.customer, vendor=self.vendor, address={},
            shipping_method=self.shipping, payment_gateway=self.gateway,
            items_total=Decimal("2000000"), grand_total=Decimal("2050000"),
            payment_status=Order.PaymentStatus.PAID,
        )
        self.item = OrderItem.objects.create(
            order=self.order, product=self.product, product_name=self.product.name,
            quantity=1, unit_price=Decimal("2000000"), line_total=Decimal("2000000"),
        )
        self.client = Client(HTTP_HOST=HOST)
        self.client.login(username="09125500001", password="pass12345")

    def _login_as(self, role, suffix):
        user = User.objects.create_user(username=f"09125500{suffix}", password="pass12345", is_staff=True)
        StoreMembership.objects.create(
            store=self.store, user=user, role=role,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )
        self.client.logout()
        self.client.login(username=user.username, password="pass12345")


class OrderRefundFormViewTests(ReturnRefundViewsTestCase):
    def test_owner_can_submit_refund(self):
        response = self.client.post(reverse("dashboard:order-refund", args=[self.order.code]), {
            f"quantity_{self.item.pk}": "1", "shipping_amount": "0", "reason": Refund.Reason.CUSTOMER_REQUEST,
        }, follow=True)
        self.assertEqual(response.status_code, 200)
        refund = Refund.objects.get(order=self.order)
        self.assertEqual(refund.approved_amount, Decimal("2000000"))

    def test_browser_supplied_amount_is_ignored_server_recalculates(self):
        """حتی اگر مرورگر تلاش کند مبلغی ارسال کند، سرور فقط از رویِ
        تعداد×قیمتِ واحدِ واقعیِ سفارش محاسبه می‌کند — هیچ فیلدِ amount
        مستقیمی در فرم وجود ندارد که بتوان دستکاری کرد."""
        response = self.client.post(reverse("dashboard:order-refund", args=[self.order.code]), {
            f"quantity_{self.item.pk}": "1", "shipping_amount": "0", "reason": Refund.Reason.CUSTOMER_REQUEST,
            "amount": "1",  # not a real field this view reads
        }, follow=True)
        self.assertEqual(response.status_code, 200)
        refund = Refund.objects.get(order=self.order)
        self.assertEqual(refund.approved_amount, Decimal("2000000"))

    def test_order_manager_can_refund_catalog_manager_cannot(self):
        self._login_as(StoreMembership.Role.ORDER_MANAGER, "101")
        response = self.client.get(reverse("dashboard:order-refund", args=[self.order.code]))
        self.assertEqual(response.status_code, 200)

        self._login_as(StoreMembership.Role.CATALOG_MANAGER, "102")
        response = self.client.post(reverse("dashboard:order-refund", args=[self.order.code]), {
            f"quantity_{self.item.pk}": "1", "shipping_amount": "0",
        })
        self.assertEqual(response.status_code, 403)

    def test_cannot_refund_order_from_other_store(self):
        other_store = Store.objects.create(
            name="فروشگاه دیگر", slug="rrv-other", status=Store.Status.ACTIVE, admin_subdomain="rrv-other-sub",
        )
        response = self.client.get(reverse("dashboard:order-refund", args=["DM-NONEXISTENT"]))
        self.assertEqual(response.status_code, 404)


class ReturnCreateViewTests(ReturnRefundViewsTestCase):
    def test_creates_return_request(self):
        response = self.client.post(reverse("dashboard:return-create", args=[self.order.code]), {
            f"quantity_{self.item.pk}": "1", "reason": ReturnRequest.Reason.DEFECTIVE_ITEM,
            "customer_explanation": "شکسته رسید",
        }, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(ReturnRequest.objects.filter(order=self.order).exists())

    def test_analyst_cannot_create_return(self):
        self._login_as(StoreMembership.Role.ANALYST, "201")
        response = self.client.post(reverse("dashboard:return-create", args=[self.order.code]), {
            f"quantity_{self.item.pk}": "1",
        })
        self.assertEqual(response.status_code, 403)


class ReturnListAndDetailViewTests(ReturnRefundViewsTestCase):
    def _create_return(self):
        return create_return_request(
            self.order, store=self.store, customer=self.customer, reason=ReturnRequest.Reason.DEFECTIVE_ITEM,
            line_requests=[{"order_item_id": self.item.pk, "quantity": 1}], actor=self.owner,
        )

    def test_list_shows_return(self):
        rr = self._create_return()
        response = self.client.get(reverse("dashboard:return-list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, rr.return_number)

    def test_detail_renders(self):
        rr = self._create_return()
        response = self.client.get(reverse("dashboard:return-detail", args=[rr.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, rr.return_number)

    def test_other_store_return_404s(self):
        other_store = Store.objects.create(name="فروشگاه دیگر", slug="rrv-other2", status=Store.Status.ACTIVE)
        other_owner = User.objects.create_user(username="09125500301", password="pass12345", is_staff=True)
        other_customer = Customer.objects.create(user=other_owner, full_name="کاربر دیگر", phone="09125500301")
        other_vendor = Vendor.objects.create(store=other_store, name="فروشگاه دیگر", slug="shop-rrv-other")
        other_category = Category.objects.create(store=other_store, name="دیجیتال", slug="digital-rrv-other")
        other_product = Product.objects.create(
            store=other_store, vendor=other_vendor, category=other_category, name="گوشی", slug="phone-rrv-other",
            sku="SKU-RRV-OTHER", price=Decimal("1000000"), stock=5,
        )
        other_shipping = ShippingMethod.objects.create(store=other_store, name="پست", slug="post-rrv-other", cost=Decimal("10000"))
        other_gateway = PaymentGateway.objects.create(store=other_store, name="زرین‌پال", slug="zarin-rrv-other")
        other_order = Order.objects.create(
            code="DM-RRV-OTHER", store=other_store, customer=other_customer, vendor=other_vendor, address={},
            shipping_method=other_shipping, payment_gateway=other_gateway,
            grand_total=Decimal("1000000"), payment_status=Order.PaymentStatus.PAID,
        )
        other_item = OrderItem.objects.create(
            order=other_order, product=other_product, product_name=other_product.name,
            quantity=1, unit_price=Decimal("1000000"), line_total=Decimal("1000000"),
        )
        other_return = create_return_request(
            other_order, store=other_store, customer=other_customer, reason=ReturnRequest.Reason.OTHER,
            line_requests=[{"order_item_id": other_item.pk, "quantity": 1}],
        )
        response = self.client.get(reverse("dashboard:return-detail", args=[other_return.pk]))
        self.assertEqual(response.status_code, 404)

    def test_analyst_can_view_but_not_manage(self):
        rr = self._create_return()
        self._login_as(StoreMembership.Role.ANALYST, "401")
        response = self.client.get(reverse("dashboard:return-detail", args=[rr.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "شروعِ بررسی")

    def test_anonymous_denied(self):
        rr = self._create_return()
        self.client.logout()
        response = self.client.get(reverse("dashboard:return-detail", args=[rr.pk]))
        self.assertEqual(response.status_code, 302)


class ReturnActionViewTests(ReturnRefundViewsTestCase):
    def _create_return(self):
        return create_return_request(
            self.order, store=self.store, customer=self.customer, reason=ReturnRequest.Reason.DEFECTIVE_ITEM,
            line_requests=[{"order_item_id": self.item.pk, "quantity": 1}], actor=self.owner,
        )

    def test_review_transitions_status(self):
        rr = self._create_return()
        self.client.post(reverse("dashboard:return-review", args=[rr.pk]))
        rr.refresh_from_db()
        self.assertEqual(rr.status, ReturnRequest.Status.UNDER_REVIEW)

    def test_approve_sets_quantities(self):
        rr = self._create_return()
        item = rr.items.first()
        self.client.post(reverse("dashboard:return-approve", args=[rr.pk]), {f"approved_{item.pk}": "1"})
        item.refresh_from_db()
        self.assertEqual(item.quantity_approved, 1)

    def test_reject_requires_post_with_reason(self):
        rr = self._create_return()
        response = self.client.get(reverse("dashboard:return-reject", args=[rr.pk]))
        self.assertEqual(response.status_code, 200)
        self.client.post(reverse("dashboard:return-reject", args=[rr.pk]), {"rejection_reason": "غیرقابل قبول"})
        rr.refresh_from_db()
        self.assertEqual(rr.status, ReturnRequest.Status.REJECTED)

    def test_full_flow_via_views_restocks_and_refunds(self):
        self.product.stock = 5
        self.product.save(update_fields=["stock"])
        rr = self._create_return()
        item = rr.items.first()

        self.client.post(reverse("dashboard:return-approve", args=[rr.pk]), {f"approved_{item.pk}": "1"})
        self.client.post(reverse("dashboard:return-receive", args=[rr.pk]), {f"received_{item.pk}": "1"})
        self.client.post(reverse("dashboard:return-inspect", args=[rr.pk]), {
            f"item_{item.pk}_present": "on", f"item_{item.pk}_condition": "opened",
            f"item_{item.pk}_restockable": "on", f"item_{item.pk}_resolution": "refund",
        })
        self.client.post(reverse("dashboard:return-complete", args=[rr.pk]))

        rr.refresh_from_db()
        self.assertEqual(rr.status, ReturnRequest.Status.COMPLETED)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 6)
        self.assertIsNotNone(rr.refund)

    def test_analyst_cannot_approve(self):
        rr = self._create_return()
        self._login_as(StoreMembership.Role.ANALYST, "501")
        response = self.client.post(reverse("dashboard:return-approve", args=[rr.pk]))
        self.assertEqual(response.status_code, 403)
