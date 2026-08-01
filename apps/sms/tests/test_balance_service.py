from django.test import TestCase

from apps.sms.models import SmsBalance, SmsPackage, SmsPackagePurchase
from apps.sms.services.balance_service import (
    PurchaseNotPendingError,
    cancel_purchase,
    complete_purchase,
    deduct_credit,
    get_or_create_balance,
    list_active_packages,
    request_purchase,
)
from apps.stores.models import Store


def _akhlaghi():
    return Store.objects.get(slug="akhlaghi")


class GetOrCreateBalanceTests(TestCase):
    def test_creates_zero_balance_for_new_store(self):
        balance = get_or_create_balance(store=_akhlaghi())
        self.assertEqual(balance.credits, 0)

    def test_returns_existing_balance(self):
        store = _akhlaghi()
        SmsBalance.objects.create(store=store, credits=42)
        balance = get_or_create_balance(store=store)
        self.assertEqual(balance.credits, 42)


class DeductCreditTests(TestCase):
    def test_deducts_one_credit(self):
        store = _akhlaghi()
        SmsBalance.objects.create(store=store, credits=10)
        deduct_credit(store=store)
        self.assertEqual(SmsBalance.objects.get(store=store).credits, 9)

    def test_creates_balance_row_if_missing_then_deducts(self):
        store = _akhlaghi()
        deduct_credit(store=store)
        self.assertEqual(SmsBalance.objects.get(store=store).credits, -1)

    def test_never_blocks_at_zero_credits_yet(self):
        """TODO documented in balance_service.deduct_credit: enforcing a hard
        stop at zero credits is a separate product decision."""
        store = _akhlaghi()
        SmsBalance.objects.create(store=store, credits=0)
        deduct_credit(store=store)
        self.assertEqual(SmsBalance.objects.get(store=store).credits, -1)


class ListActivePackagesTests(TestCase):
    def test_only_active_packages_returned_in_order(self):
        # سه بسته‌ی پیش‌فرض از migration 0006 از قبل موجودند — این تست فقط
        # ترتیبِ نسبیِ بسته‌های خودش و کنارگذاشتنِ غیرفعال‌ها را بررسی می‌کند.
        SmsPackage.objects.create(name="Z-custom-b", credit_amount=200, price=150_000, display_order=100, is_active=True)
        SmsPackage.objects.create(name="Z-custom-a", credit_amount=50, price=50_000, display_order=99, is_active=True)
        SmsPackage.objects.create(name="Z-custom-off", credit_amount=999, price=1, display_order=98, is_active=False)
        names = list(list_active_packages().values_list("name", flat=True))
        self.assertNotIn("Z-custom-off", names)
        self.assertLess(names.index("Z-custom-a"), names.index("Z-custom-b"))


class RequestPurchaseTests(TestCase):
    def setUp(self):
        self.store = _akhlaghi()
        self.package = SmsPackage.objects.create(name="P", credit_amount=100, price=90_000)

    def test_creates_pending_purchase_with_snapshotted_values(self):
        purchase = request_purchase(store=self.store, package=self.package)
        self.assertEqual(purchase.status, SmsPackagePurchase.Status.PENDING)
        self.assertEqual(purchase.credit_amount, 100)
        self.assertEqual(purchase.price, 90_000)

    def test_does_not_grant_credit_immediately(self):
        request_purchase(store=self.store, package=self.package)
        self.assertFalse(SmsBalance.objects.filter(store=self.store, credits__gt=0).exists())

    def test_snapshot_survives_later_package_price_changes(self):
        purchase = request_purchase(store=self.store, package=self.package)
        self.package.price = 999_999
        self.package.save(update_fields=["price"])
        purchase.refresh_from_db()
        self.assertEqual(purchase.price, 90_000)


class CompletePurchaseTests(TestCase):
    def setUp(self):
        self.store = _akhlaghi()
        self.package = SmsPackage.objects.create(name="P", credit_amount=100, price=90_000)
        self.purchase = request_purchase(store=self.store, package=self.package)

    def test_completes_and_credits_balance(self):
        complete_purchase(purchase=self.purchase)
        self.purchase.refresh_from_db()
        self.assertEqual(self.purchase.status, SmsPackagePurchase.Status.COMPLETED)
        self.assertIsNotNone(self.purchase.completed_at)
        self.assertEqual(SmsBalance.objects.get(store=self.store).credits, 100)

    def test_adds_to_existing_balance_rather_than_overwriting(self):
        SmsBalance.objects.create(store=self.store, credits=50)
        complete_purchase(purchase=self.purchase)
        self.assertEqual(SmsBalance.objects.get(store=self.store).credits, 150)

    def test_completing_twice_is_rejected(self):
        complete_purchase(purchase=self.purchase)
        with self.assertRaises(PurchaseNotPendingError):
            complete_purchase(purchase=self.purchase)
        # Balance must not be double-credited by the rejected second call.
        self.assertEqual(SmsBalance.objects.get(store=self.store).credits, 100)

    def test_canceled_purchase_cannot_be_completed(self):
        cancel_purchase(purchase=self.purchase)
        with self.assertRaises(PurchaseNotPendingError):
            complete_purchase(purchase=self.purchase)


class CancelPurchaseTests(TestCase):
    def setUp(self):
        self.store = _akhlaghi()
        self.package = SmsPackage.objects.create(name="P", credit_amount=100, price=90_000)
        self.purchase = request_purchase(store=self.store, package=self.package)

    def test_cancels_pending_purchase(self):
        cancel_purchase(purchase=self.purchase)
        self.purchase.refresh_from_db()
        self.assertEqual(self.purchase.status, SmsPackagePurchase.Status.CANCELED)

    def test_completed_purchase_cannot_be_canceled(self):
        complete_purchase(purchase=self.purchase)
        with self.assertRaises(PurchaseNotPendingError):
            cancel_purchase(purchase=self.purchase)
