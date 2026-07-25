from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.customers.models import Customer
from apps.catalog.models import Vendor
from apps.orders.models import Order, PaymentGateway, ShippingMethod, Transaction
from apps.orders.services.payment_service import detect_bank, simulate_payment
from apps.sms.models import SmsLog, SmsTemplate
from apps.stores.models import Store

User = get_user_model()


def _akhlaghi():
    return Store.objects.get(slug="akhlaghi")


class DetectBankTests(TestCase):
    def test_known_bin_returns_bank_name(self):
        self.assertEqual(detect_bank("6037991234567890"), "بانک ملی ایران")

    def test_known_bin_with_spaces_and_dashes(self):
        self.assertEqual(detect_bank("6104-3312-3456-7890"), "بانک ملت")
        self.assertEqual(detect_bank("6104 3312 3456 7890"), "بانک ملت")

    def test_unknown_bin_returns_fallback_label(self):
        self.assertEqual(detect_bank("9999991234567890"), "کارت بانکی نامشخص")

    def test_too_short_number_returns_fallback_label(self):
        self.assertEqual(detect_bank("123"), "کارت بانکی نامشخص")

    def test_empty_or_none_returns_fallback_label(self):
        self.assertEqual(detect_bank(""), "کارت بانکی نامشخص")
        self.assertEqual(detect_bank(None), "کارت بانکی نامشخص")


class SimulatePaymentTests(TestCase):
    def setUp(self):
        self.store = _akhlaghi()
        self.user = User.objects.create_user(username="vahid", password="pass12345")
        self.customer = Customer.objects.create(user=self.user, full_name="وحید نوری", phone="09127770000")
        self.vendor = Vendor.objects.create(store=self.store, name="فروشگاه", slug="shop-pay")
        self.shipping = ShippingMethod.objects.create(name="پست", slug="post-pay", cost=Decimal("45000"))
        self.gateway = PaymentGateway.objects.create(name="زرین‌پال", slug="zarin-pay")
        self.order = Order.objects.create(
            code="DM-77777", customer=self.customer, vendor=self.vendor, address={},
            shipping_method=self.shipping, payment_gateway=self.gateway,
            items_total=Decimal("500000"), grand_total=Decimal("545000"),
        )

    def test_successful_payment_creates_ok_transaction_and_advances_order(self):
        tx = simulate_payment(self.order, True, store=self.store)
        self.order.refresh_from_db()

        self.assertEqual(tx.status, Transaction.Status.OK)
        self.assertEqual(tx.amount, Decimal("545000"))
        self.assertTrue(tx.ref_id)
        self.assertEqual(self.order.payment_status, Order.PaymentStatus.PAID)
        self.assertEqual(self.order.status, Order.Status.PROCESSING)
        self.assertEqual(self.order.status_history.count(), 1)

    def test_failed_payment_creates_fail_transaction_and_keeps_order_pending(self):
        tx = simulate_payment(self.order, False, store=self.store)
        self.order.refresh_from_db()

        self.assertEqual(tx.status, Transaction.Status.FAIL)
        self.assertEqual(self.order.payment_status, Order.PaymentStatus.FAILED)
        self.assertEqual(self.order.status, Order.Status.PENDING)
        self.assertEqual(self.order.status_history.count(), 0)

    def test_transaction_code_is_unique_across_payments(self):
        tx1 = simulate_payment(self.order, False, store=self.store)
        self.order.payment_status = Order.PaymentStatus.PENDING
        self.order.save(update_fields=["payment_status"])
        tx2 = simulate_payment(self.order, False, store=self.store)
        self.assertNotEqual(tx1.code, tx2.code)

    def test_cannot_pay_an_already_paid_order(self):
        simulate_payment(self.order, True, store=self.store)
        with self.assertRaises(ValueError):
            simulate_payment(self.order, True, store=self.store)

    def test_successful_payment_sends_payment_success_sms(self):
        SmsTemplate.ensure_defaults()
        with self.captureOnCommitCallbacks(execute=True):
            simulate_payment(self.order, True, store=self.store)
        self.assertTrue(
            SmsLog.objects.filter(event_key="payment_success", recipient=self.customer.phone).exists()
        )
        # پرداخت موفق باعث گذار به «در حال پردازش» هم می‌شود؛ آن پیامک هم باید جدا ارسال شود.
        self.assertTrue(
            SmsLog.objects.filter(event_key="order_processing", recipient=self.customer.phone).exists()
        )

    def test_failed_payment_sends_payment_failed_sms(self):
        SmsTemplate.ensure_defaults()
        with self.captureOnCommitCallbacks(execute=True):
            simulate_payment(self.order, False, store=self.store)
        self.assertTrue(
            SmsLog.objects.filter(event_key="payment_failed", recipient=self.customer.phone).exists()
        )
