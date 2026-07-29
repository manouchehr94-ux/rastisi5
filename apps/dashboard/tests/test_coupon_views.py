from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.cart.models import Coupon
from apps.stores.models import Store, StoreMembership

User = get_user_model()

HOST = "coupon-test.rastisi.ir"


def _akhlaghi():
    return Store.objects.get(slug="akhlaghi")


@override_settings(ALLOWED_HOSTS=[HOST, "testserver"])
class CouponViewsTestCase(TestCase):
    def setUp(self):
        self.store = _akhlaghi()
        self.store.admin_subdomain = HOST.split(".")[0]
        self.store.save(update_fields=["admin_subdomain"])
        self.owner = User.objects.create_user(username="09124400001", password="pass12345", is_staff=True)
        StoreMembership.objects.create(
            store=self.store, user=self.owner, role=StoreMembership.Role.OWNER,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )
        self.client = Client(HTTP_HOST=HOST)
        self.client.login(username="09124400001", password="pass12345")

    def _login_as(self, role, suffix):
        user = User.objects.create_user(username=f"09124400{suffix}", password="pass12345", is_staff=True)
        StoreMembership.objects.create(
            store=self.store, user=user, role=role,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )
        self.client.logout()
        self.client.login(username=user.username, password="pass12345")


class CouponListViewTests(CouponViewsTestCase):
    def test_renders_list(self):
        Coupon.objects.create(store=self.store, code="SUMMER10", type=Coupon.Type.PERCENT, value=10)
        response = self.client.get(reverse("dashboard:coupon-list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "SUMMER10")

    def test_other_store_coupon_not_listed(self):
        other_store = Store.objects.create(name="فروشگاه دیگر", slug="coupon-other", status=Store.Status.ACTIVE)
        Coupon.objects.create(store=other_store, code="OTHERCODE", type=Coupon.Type.PERCENT, value=10)
        response = self.client.get(reverse("dashboard:coupon-list"))
        self.assertNotContains(response, "OTHERCODE")

    def test_analyst_can_view_but_not_manage(self):
        self._login_as(StoreMembership.Role.ANALYST, "101")
        response = self.client.get(reverse("dashboard:coupon-list"))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "کد تخفیف جدید")

    def test_anonymous_denied(self):
        self.client.logout()
        response = self.client.get(reverse("dashboard:coupon-list"))
        self.assertEqual(response.status_code, 302)


class CouponFormViewTests(CouponViewsTestCase):
    def test_owner_can_create_coupon(self):
        response = self.client.post(reverse("dashboard:coupon-add"), {
            "code": "newcode", "type": Coupon.Type.PERCENT, "value": "15", "is_active": "on",
        }, follow=True)
        self.assertEqual(response.status_code, 200)
        coupon = Coupon.objects.get(store=self.store, code="NEWCODE")
        self.assertEqual(coupon.value, Decimal("15"))

    def test_same_code_allowed_in_different_store(self):
        other_store = Store.objects.create(name="فروشگاه دیگر", slug="coupon-other2", status=Store.Status.ACTIVE)
        Coupon.objects.create(store=other_store, code="SHARED", type=Coupon.Type.PERCENT, value=5)
        response = self.client.post(reverse("dashboard:coupon-add"), {
            "code": "SHARED", "type": Coupon.Type.PERCENT, "value": "5", "is_active": "on",
        }, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(Coupon.objects.filter(store=self.store, code="SHARED").exists())

    def test_duplicate_code_in_same_store_rejected(self):
        Coupon.objects.create(store=self.store, code="DUPCODE", type=Coupon.Type.PERCENT, value=5)
        response = self.client.post(reverse("dashboard:coupon-add"), {
            "code": "DUPCODE", "type": Coupon.Type.PERCENT, "value": "5", "is_active": "on",
        }, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Coupon.objects.filter(store=self.store, code="DUPCODE").count(), 1)

    def test_cannot_edit_coupon_from_other_store(self):
        other_store = Store.objects.create(name="فروشگاه دیگر", slug="coupon-other3", status=Store.Status.ACTIVE)
        other_coupon = Coupon.objects.create(store=other_store, code="OTHERCODE2", type=Coupon.Type.PERCENT, value=10)
        response = self.client.get(reverse("dashboard:coupon-edit", args=[other_coupon.pk]))
        self.assertEqual(response.status_code, 404)

    def test_analyst_cannot_create_coupon(self):
        self._login_as(StoreMembership.Role.ANALYST, "102")
        response = self.client.post(reverse("dashboard:coupon-add"), {
            "code": "BLOCKED", "type": Coupon.Type.PERCENT, "value": "5",
        })
        self.assertEqual(response.status_code, 403)


class CouponDeleteAndToggleViewTests(CouponViewsTestCase):
    def test_cannot_delete_coupon_from_other_store(self):
        other_store = Store.objects.create(name="فروشگاه دیگر", slug="coupon-other4", status=Store.Status.ACTIVE)
        other_coupon = Coupon.objects.create(store=other_store, code="OTHERCODE3", type=Coupon.Type.PERCENT, value=10)
        response = self.client.post(reverse("dashboard:coupon-delete", args=[other_coupon.pk]))
        self.assertEqual(response.status_code, 404)
        self.assertTrue(Coupon.objects.filter(pk=other_coupon.pk).exists())

    def test_toggle_active(self):
        coupon = Coupon.objects.create(store=self.store, code="TOGGLECODE", type=Coupon.Type.PERCENT, value=10)
        self.client.post(reverse("dashboard:coupon-toggle", args=[coupon.pk]))
        coupon.refresh_from_db()
        self.assertFalse(coupon.is_active)
