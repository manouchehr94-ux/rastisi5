"""دسترسیِ Django Admin به مدل‌های سطحِ پلتفرمِ اعتبار/بسته‌ی پیامک — فقط
superuser. همان الگویِ ``apps.billing.tests.test_billing_admin`` (بررسیِ
مستقیمِ has_module_permission/has_view_permission با RequestFactory، نه
یک درخواستِ کاملِ HTTP به ``/admin/...``)."""
from django.contrib.admin.sites import AdminSite
from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase
from django.urls import reverse

from apps.sms.admin import SmsBalanceAdmin, SmsPackageAdmin, SmsPackagePurchaseAdmin
from apps.sms.models import SmsBalance, SmsPackage, SmsPackagePurchase
from apps.sms.services.balance_service import request_purchase
from apps.stores.models import Store

User = get_user_model()


def _akhlaghi():
    return Store.objects.get(slug="akhlaghi")


class SmsAdminAccessTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.superuser = User.objects.create_superuser(username="sms-super", password="p", email="s@e.com")
        cls.staff = User.objects.create_user(username="sms-staff", password="p", is_staff=True)

    def setUp(self):
        self.site = AdminSite()
        self.factory = RequestFactory()
        self.package_admin = SmsPackageAdmin(SmsPackage, self.site)
        self.balance_admin = SmsBalanceAdmin(SmsBalance, self.site)
        self.purchase_admin = SmsPackagePurchaseAdmin(SmsPackagePurchase, self.site)

    def _req(self, user):
        req = self.factory.get("/admin/")
        req.user = user
        return req

    def test_non_superuser_denied_package_admin(self):
        req = self._req(self.staff)
        self.assertFalse(self.package_admin.has_module_permission(req))
        self.assertFalse(self.package_admin.has_view_permission(req))

    def test_non_superuser_denied_balance_admin(self):
        req = self._req(self.staff)
        self.assertFalse(self.balance_admin.has_view_permission(req))

    def test_non_superuser_denied_purchase_admin(self):
        req = self._req(self.staff)
        self.assertFalse(self.purchase_admin.has_view_permission(req))

    def test_superuser_may_view_all_three(self):
        req = self._req(self.superuser)
        self.assertTrue(self.package_admin.has_view_permission(req))
        self.assertTrue(self.balance_admin.has_view_permission(req))
        self.assertTrue(self.purchase_admin.has_view_permission(req))

    def test_balance_is_never_directly_add_change_or_delete_able(self):
        req = self._req(self.superuser)
        self.assertFalse(self.balance_admin.has_add_permission(req))
        self.assertFalse(self.balance_admin.has_change_permission(req))
        self.assertFalse(self.balance_admin.has_delete_permission(req))


class SmsPackagePurchaseAdminActionTests(TestCase):
    def setUp(self):
        self.superuser = User.objects.create_superuser(username="sms-super2", password="p", email="s2@e.com")
        self.client.login(username="sms-super2", password="p")
        self.store = _akhlaghi()
        self.package = SmsPackage.objects.create(name="P", credit_amount=100, price=90_000)
        self.purchase = request_purchase(store=self.store, package=self.package)

    def test_mark_completed_action_credits_balance(self):
        self.client.post(
            reverse("admin:sms_smspackagepurchase_changelist"),
            {"action": "mark_completed", "_selected_action": [str(self.purchase.pk)]},
        )
        self.purchase.refresh_from_db()
        self.assertEqual(self.purchase.status, SmsPackagePurchase.Status.COMPLETED)
        self.assertEqual(SmsBalance.objects.get(store=self.store).credits, 100)
