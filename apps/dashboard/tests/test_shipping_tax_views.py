from decimal import Decimal

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.core.models import ShopSettings, ShopSettingsNotProvisionedError
from apps.orders.models import ShippingMethod, ShippingRateRule, ShippingZone, TaxClass, TaxRate
from apps.stores.models import Store, StoreMembership

User = get_user_model()

HOST = f"shipping-tax-test.{settings.RASTISI_ADMIN_DOMAIN_SUFFIX}"


def _akhlaghi():
    return Store.objects.get(slug="akhlaghi")


@override_settings(ALLOWED_HOSTS=[HOST, "testserver"])
class ShippingTaxViewsTestCase(TestCase):
    def setUp(self):
        self.store = _akhlaghi()
        self.store.admin_subdomain = HOST.split(".")[0]
        self.store.save(update_fields=["admin_subdomain"])
        self.owner = User.objects.create_user(username="09126600001", password="pass12345", is_staff=True)
        StoreMembership.objects.create(
            store=self.store, user=self.owner, role=StoreMembership.Role.OWNER,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )
        self.client = Client(HTTP_HOST=HOST)
        self.client.login(username="09126600001", password="pass12345")

    def _login_as(self, role, suffix):
        user = User.objects.create_user(username=f"09126600{suffix}", password="pass12345", is_staff=True)
        StoreMembership.objects.create(
            store=self.store, user=user, role=role,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )
        self.client.logout()
        self.client.login(username=user.username, password="pass12345")


class ShippingZoneViewTests(ShippingTaxViewsTestCase):
    def test_create_zone(self):
        response = self.client.post(reverse("dashboard:shipping-zone-add"), {
            "name": "تهران", "code": "tehran-view", "provinces": "تهران", "is_active": "on",
        }, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(ShippingZone.objects.filter(store=self.store, code="tehran-view").exists())

    def test_cannot_view_other_store_zone(self):
        other_store = Store.objects.create(name="فروشگاه دیگر", slug="ship-tax-view-other", status=Store.Status.ACTIVE)
        other_zone = ShippingZone.objects.create(store=other_store, name="دیگر", code="other-zone-view")
        response = self.client.get(reverse("dashboard:shipping-zone-edit", args=[other_zone.pk]))
        self.assertEqual(response.status_code, 404)

    def test_analyst_can_view_but_not_manage(self):
        self._login_as(StoreMembership.Role.ANALYST, "101")
        response = self.client.get(reverse("dashboard:shipping-zone-list"))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "منطقه‌ی جدید")

    def test_content_editor_denied(self):
        self._login_as(StoreMembership.Role.CONTENT_EDITOR, "102")
        response = self.client.get(reverse("dashboard:shipping-zone-list"))
        self.assertEqual(response.status_code, 403)

    def test_order_manager_can_manage_shipping(self):
        self._login_as(StoreMembership.Role.ORDER_MANAGER, "103")
        response = self.client.post(reverse("dashboard:shipping-zone-add"), {
            "name": "فارس", "code": "fars-view", "provinces": "فارس", "is_active": "on",
        }, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(ShippingZone.objects.filter(store=self.store, code="fars-view").exists())


class ShippingMethodViewTests(ShippingTaxViewsTestCase):
    def test_create_method(self):
        response = self.client.post(reverse("dashboard:shipping-method-add"), {
            "name": "پیک موتوری", "slug": "moto-view", "cost": "30000", "free_over": "500000",
            "method_type": ShippingMethod.MethodType.FLAT_RATE, "is_active": "on",
        }, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(ShippingMethod.objects.filter(store=self.store, slug="moto-view").exists())

    def test_cannot_edit_other_store_method(self):
        other_store = Store.objects.create(name="فروشگاه دیگر", slug="ship-method-view-other", status=Store.Status.ACTIVE)
        other_method = ShippingMethod.objects.create(store=other_store, name="دیگر", slug="other-method-view")
        response = self.client.get(reverse("dashboard:shipping-method-edit", args=[other_method.pk]))
        self.assertEqual(response.status_code, 404)

    def test_toggle_archive(self):
        method = ShippingMethod.objects.create(store=self.store, name="پست", slug="post-view", cost=Decimal("40000"))
        self.client.post(reverse("dashboard:shipping-method-archive", args=[method.pk]))
        method.refresh_from_db()
        self.assertFalse(method.is_active)


class ShippingRateRuleViewTests(ShippingTaxViewsTestCase):
    def setUp(self):
        super().setUp()
        self.method = ShippingMethod.objects.create(store=self.store, name="پست", slug="post-rate-view", cost=Decimal("40000"))

    def test_create_rate_rule(self):
        response = self.client.post(reverse("dashboard:shipping-rate-rule-add", args=[self.method.pk]), {
            "name": "ویژه", "rate_amount": "15000", "priority": "0", "is_active": "on",
        }, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(ShippingRateRule.objects.filter(method=self.method, name="ویژه").exists())

    def test_cannot_manage_rate_rule_for_other_store_method(self):
        other_store = Store.objects.create(name="فروشگاه دیگر", slug="ship-rate-view-other", status=Store.Status.ACTIVE)
        other_method = ShippingMethod.objects.create(store=other_store, name="دیگر", slug="other-rate-method-view")
        response = self.client.get(reverse("dashboard:shipping-rate-rule-list", args=[other_method.pk]))
        self.assertEqual(response.status_code, 404)


class TaxSettingsViewTests(ShippingTaxViewsTestCase):
    def test_update_tax_settings(self):
        response = self.client.post(reverse("dashboard:tax-settings"), {
            "tax_enabled": "on", "shipping_taxable": "on", "tax_rounding_policy": "per_line",
        }, follow=True)
        self.assertEqual(response.status_code, 200)
        settings_row = ShopSettings.load(store=self.store)
        self.assertTrue(settings_row.shipping_taxable)
        self.assertEqual(settings_row.tax_rounding_policy, "per_line")

    def test_order_manager_can_view_but_not_change_tax_settings(self):
        self._login_as(StoreMembership.Role.ORDER_MANAGER, "104")
        response = self.client.get(reverse("dashboard:tax-settings"))
        self.assertEqual(response.status_code, 200)
        response = self.client.post(reverse("dashboard:tax-settings"), {"tax_enabled": "on"})
        self.assertEqual(response.status_code, 403)


class TaxNoTaxChoiceViewTests(ShippingTaxViewsTestCase):
    """صفحه‌ی مالیات باید یک انتخابِ صریحِ «مالیات ندارم/دارم» بدهد؛ ذخیره‌ی
    هرکدام باید ``tax_setup_confirmed_at`` را ثبت کند."""

    def test_choosing_no_tax_saves_disabled_and_confirms(self):
        response = self.client.post(reverse("dashboard:tax-settings"), {"tax_enabled": "off"}, follow=True)
        self.assertEqual(response.status_code, 200)
        settings_row = ShopSettings.load(store=self.store)
        self.assertFalse(settings_row.tax_enabled)
        self.assertIsNotNone(settings_row.tax_setup_confirmed_at)

    def test_choosing_has_tax_saves_enabled_and_confirms(self):
        response = self.client.post(
            reverse("dashboard:tax-settings"),
            {"tax_enabled": "on", "tax_rounding_policy": "on_total"}, follow=True,
        )
        self.assertEqual(response.status_code, 200)
        settings_row = ShopSettings.load(store=self.store)
        self.assertTrue(settings_row.tax_enabled)
        self.assertIsNotNone(settings_row.tax_setup_confirmed_at)

    def test_page_shows_the_two_choice_labels(self):
        response = self.client.get(reverse("dashboard:tax-settings"))
        self.assertContains(response, "مالیات ندارم")
        self.assertContains(response, "مالیات دارم")

    def test_no_tax_choice_does_not_leak_to_other_store(self):
        other_store = Store.objects.create(name="فروشگاه دیگر", slug="tax-choice-other", status=Store.Status.ACTIVE)
        self.client.post(reverse("dashboard:tax-settings"), {"tax_enabled": "off"})
        with self.assertRaises(ShopSettingsNotProvisionedError):
            ShopSettings.load(store=other_store)


class TaxClassViewTests(ShippingTaxViewsTestCase):
    def test_create_tax_class(self):
        response = self.client.post(reverse("dashboard:tax-class-add"), {
            "name": "عمومی", "code": "general-view", "is_active": "on",
        }, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(TaxClass.objects.filter(store=self.store, code="general-view").exists())

    def test_cannot_view_other_store_tax_class(self):
        other_store = Store.objects.create(name="فروشگاه دیگر", slug="tax-class-view-other", status=Store.Status.ACTIVE)
        other_class = TaxClass.objects.create(store=other_store, name="دیگر", code="other-class-view")
        response = self.client.get(reverse("dashboard:tax-class-edit", args=[other_class.pk]))
        self.assertEqual(response.status_code, 404)

    def test_catalog_manager_cannot_manage_tax_classes(self):
        self._login_as(StoreMembership.Role.CATALOG_MANAGER, "105")
        response = self.client.post(reverse("dashboard:tax-class-add"), {"name": "معاف", "code": "exempt-view"})
        self.assertEqual(response.status_code, 403)


class TaxRateViewTests(ShippingTaxViewsTestCase):
    def setUp(self):
        super().setUp()
        self.tax_class = TaxClass.objects.create(store=self.store, name="عمومی", code="general-rate-view")

    def test_create_tax_rate(self):
        response = self.client.post(reverse("dashboard:tax-rate-add", args=[self.tax_class.pk]), {
            "rate_percent": "9", "priority": "0", "is_active": "on", "applies_to_shipping": "",
        }, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(TaxRate.objects.filter(tax_class=self.tax_class, rate_percent=Decimal("9")).exists())

    def test_cannot_manage_rate_for_other_store_tax_class(self):
        other_store = Store.objects.create(name="فروشگاه دیگر", slug="tax-rate-view-other", status=Store.Status.ACTIVE)
        other_class = TaxClass.objects.create(store=other_store, name="دیگر", code="other-rate-class-view")
        response = self.client.get(reverse("dashboard:tax-rate-list", args=[other_class.pk]))
        self.assertEqual(response.status_code, 404)
