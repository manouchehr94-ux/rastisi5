from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.catalog.models import Category, Product, StockMovement, Vendor
from apps.catalog.services.inventory_service import decrement_stock_for_order_item
from apps.stores.models import Store, StoreMembership

User = get_user_model()

HOST = "inv-test.rastisi.ir"


def _akhlaghi():
    return Store.objects.get(slug="akhlaghi")


@override_settings(ALLOWED_HOSTS=[HOST, "testserver"])
class InventoryViewsTestCase(TestCase):
    def setUp(self):
        self.store = _akhlaghi()
        self.store.admin_subdomain = HOST.split(".")[0]
        self.store.save(update_fields=["admin_subdomain"])
        self.vendor = Vendor.objects.create(store=self.store, name="فروشگاه", slug="shop-invv")
        self.category = Category.objects.create(store=self.store, name="لوازم", slug="gear-invv")
        self.product = Product.objects.create(
            store=self.store, vendor=self.vendor, category=self.category, name="کوله پشتی", slug="backpack-invv",
            sku="SKU-INVV1", price=Decimal("400000"), stock=10,
        )
        self.staff = User.objects.create_user(username="09123388001", password="pass12345", is_staff=True)
        StoreMembership.objects.create(
            store=self.store, user=self.staff, role=StoreMembership.Role.OWNER,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )
        self.client = Client(HTTP_HOST=HOST)
        self.client.login(username="09123388001", password="pass12345")
        decrement_stock_for_order_item(store=self.store, product=self.product, variant=None, quantity=2, order=None)


class InventoryListViewTests(InventoryViewsTestCase):
    def test_renders_movements(self):
        response = self.client.get(reverse("dashboard:inventory-list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "کوله پشتی")
        self.assertContains(response, "SKU-INVV1")

    def test_anonymous_denied(self):
        self.client.logout()
        response = self.client.get(reverse("dashboard:inventory-list"))
        self.assertEqual(response.status_code, 302)

    def test_analyst_cannot_view_inventory_ledger(self):
        user = User.objects.create_user(username="09123388010", password="pass12345", is_staff=True)
        StoreMembership.objects.create(
            store=self.store, user=user, role=StoreMembership.Role.ANALYST,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )
        self.client.logout()
        self.client.login(username=user.username, password="pass12345")
        response = self.client.get(reverse("dashboard:inventory-list"))
        self.assertEqual(response.status_code, 403)

    def test_catalog_manager_can_view_inventory_ledger(self):
        user = User.objects.create_user(username="09123388011", password="pass12345", is_staff=True)
        StoreMembership.objects.create(
            store=self.store, user=user, role=StoreMembership.Role.CATALOG_MANAGER,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )
        self.client.logout()
        self.client.login(username=user.username, password="pass12345")
        response = self.client.get(reverse("dashboard:inventory-list"))
        self.assertEqual(response.status_code, 200)

    def test_other_store_movements_not_visible(self):
        other_store = Store.objects.create(name="فروشگاه دیگر", slug="inv-other-view", status=Store.Status.ACTIVE)
        other_vendor = Vendor.objects.create(store=other_store, name="فروشگاه دیگر", slug="shop-invv-other")
        other_category = Category.objects.create(store=other_store, name="لوازم", slug="gear-invv-other")
        other_product = Product.objects.create(
            store=other_store, vendor=other_vendor, category=other_category, name="چمدان", slug="suitcase-invv",
            sku="SKU-INVV2", price=Decimal("900000"), stock=5,
        )
        decrement_stock_for_order_item(store=other_store, product=other_product, variant=None, quantity=1, order=None)
        response = self.client.get(reverse("dashboard:inventory-list"))
        self.assertNotContains(response, "چمدان")


class InventoryTableViewTests(InventoryViewsTestCase):
    def test_search_filters_by_product_name(self):
        response = self.client.get(reverse("dashboard:inventory-table"), {"q": "کوله"})
        self.assertContains(response, "کوله پشتی")

    def test_search_excludes_non_matching(self):
        response = self.client.get(reverse("dashboard:inventory-table"), {"q": "چیز-نامرتبط"})
        self.assertNotContains(response, "کوله پشتی")

    def test_reason_filter(self):
        response = self.client.get(reverse("dashboard:inventory-table"), {"reason": StockMovement.Reason.ORDER_PLACED})
        self.assertContains(response, "کوله پشتی")
        response = self.client.get(reverse("dashboard:inventory-table"), {"reason": StockMovement.Reason.MANUAL_ADJUSTMENT})
        self.assertNotContains(response, "کوله پشتی")
