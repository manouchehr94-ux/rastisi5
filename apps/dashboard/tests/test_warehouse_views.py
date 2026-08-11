from decimal import Decimal

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.catalog.models import Category, InventoryReservation, Product, Vendor, Warehouse, WarehouseInventory, WarehouseTransfer
from apps.catalog.services.reservation_service import reserve_inventory
from apps.catalog.services.transfer_service import create_transfer, request_transfer, ship_transfer
from apps.catalog.services.warehouse_service import create_warehouse, provision_default_warehouse
from apps.stores.models import Store, StoreMembership

User = get_user_model()

HOST = f"warehouse-test.{settings.RASTISI_ADMIN_DOMAIN_SUFFIX}"


def _akhlaghi():
    return Store.objects.get(slug="akhlaghi")


@override_settings(ALLOWED_HOSTS=[HOST, "testserver"])
class WarehouseViewsTestCase(TestCase):
    def setUp(self):
        self.store = _akhlaghi()
        self.store.admin_subdomain = HOST.split(".")[0]
        self.store.save(update_fields=["admin_subdomain"])
        self.owner = User.objects.create_user(username="09125500001", password="pass12345", is_staff=True)
        StoreMembership.objects.create(
            store=self.store, user=self.owner, role=StoreMembership.Role.OWNER,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )
        self.client = Client(HTTP_HOST=HOST)
        self.client.login(username="09125500001", password="pass12345")
        self.vendor = Vendor.objects.create(store=self.store, name="فروشگاه", slug="shop-wh-view")
        self.category = Category.objects.create(store=self.store, name="لوازم", slug="gear-wh-view")
        self.product = Product.objects.create(
            store=self.store, vendor=self.vendor, category=self.category, name="کیف پول", slug="wallet-wh-view",
            sku="SKU-WHV1", price=Decimal("200000"), stock=10,
        )

    def _login_as(self, role, suffix):
        user = User.objects.create_user(username=f"09125500{suffix}", password="pass12345", is_staff=True)
        StoreMembership.objects.create(
            store=self.store, user=user, role=role,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )
        self.client.logout()
        self.client.login(username=user.username, password="pass12345")


class WarehouseListViewTests(WarehouseViewsTestCase):
    def test_renders_list(self):
        provision_default_warehouse(self.store)
        response = self.client.get(reverse("dashboard:warehouse-list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "انبار اصلی")

    def test_other_store_warehouse_not_listed(self):
        other_store = Store.objects.create(name="فروشگاه دیگر", slug="wh-view-other", status=Store.Status.ACTIVE)
        create_warehouse(other_store, name="انبارِ دیگر", code="other")
        response = self.client.get(reverse("dashboard:warehouse-list"))
        self.assertNotContains(response, "انبارِ دیگر")

    def test_content_editor_denied(self):
        self._login_as(StoreMembership.Role.CONTENT_EDITOR, "101")
        response = self.client.get(reverse("dashboard:warehouse-list"))
        self.assertEqual(response.status_code, 403)

    def test_analyst_can_view_but_not_manage(self):
        self._login_as(StoreMembership.Role.ANALYST, "102")
        response = self.client.get(reverse("dashboard:warehouse-list"))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "انبارِ جدید")


class WarehouseFormViewTests(WarehouseViewsTestCase):
    def test_owner_can_create_warehouse(self):
        response = self.client.post(reverse("dashboard:warehouse-add"), {
            "name": "انبار شمال", "code": "north-view", "is_active": "on",
        }, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(Warehouse.objects.filter(store=self.store, code="north-view").exists())

    def test_cannot_edit_warehouse_from_other_store(self):
        other_store = Store.objects.create(name="فروشگاه دیگر", slug="wh-view-other2", status=Store.Status.ACTIVE)
        other_warehouse = create_warehouse(other_store, name="انبارِ دیگر", code="other2")
        response = self.client.get(reverse("dashboard:warehouse-edit", args=[other_warehouse.pk]))
        self.assertEqual(response.status_code, 404)

    def test_catalog_manager_can_create_warehouse(self):
        self._login_as(StoreMembership.Role.CATALOG_MANAGER, "103")
        response = self.client.post(reverse("dashboard:warehouse-add"), {
            "name": "انبار جنوب", "code": "south-view", "is_active": "on",
        }, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(Warehouse.objects.filter(store=self.store, code="south-view").exists())

    def test_order_manager_cannot_create_warehouse(self):
        self._login_as(StoreMembership.Role.ORDER_MANAGER, "104")
        response = self.client.post(reverse("dashboard:warehouse-add"), {
            "name": "انبار شرق", "code": "east-view",
        })
        self.assertEqual(response.status_code, 403)
        self.assertFalse(Warehouse.objects.filter(store=self.store, code="east-view").exists())


class WarehouseLifecycleViewTests(WarehouseViewsTestCase):
    def test_cannot_archive_warehouse_from_other_store(self):
        other_store = Store.objects.create(name="فروشگاه دیگر", slug="wh-view-other3", status=Store.Status.ACTIVE)
        other_warehouse = create_warehouse(other_store, name="انبارِ دیگر", code="other3")
        response = self.client.post(reverse("dashboard:warehouse-archive", args=[other_warehouse.pk]))
        self.assertEqual(response.status_code, 404)
        other_warehouse.refresh_from_db()
        self.assertTrue(other_warehouse.is_active)

    def test_set_default(self):
        provision_default_warehouse(self.store)
        secondary = create_warehouse(self.store, name="ثانویه", code="secondary-view")
        self.client.post(reverse("dashboard:warehouse-set-default", args=[secondary.pk]))
        secondary.refresh_from_db()
        self.assertTrue(secondary.is_default)


class WarehouseDetailViewTests(WarehouseViewsTestCase):
    def test_shows_balances_for_this_store_only(self):
        warehouse = provision_default_warehouse(self.store)
        WarehouseInventory.objects.create(store=self.store, warehouse=warehouse, product=self.product, on_hand=5)
        response = self.client.get(reverse("dashboard:warehouse-detail", args=[warehouse.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "کیف پول")

    def test_cannot_view_other_store_warehouse_detail(self):
        other_store = Store.objects.create(name="فروشگاه دیگر", slug="wh-view-other4", status=Store.Status.ACTIVE)
        other_warehouse = create_warehouse(other_store, name="انبارِ دیگر", code="other4")
        response = self.client.get(reverse("dashboard:warehouse-detail", args=[other_warehouse.pk]))
        self.assertEqual(response.status_code, 404)


class ReservationViewsTestCase(WarehouseViewsTestCase):
    def test_reservation_list_shows_only_this_store(self):
        reserve_inventory(store=self.store, product=self.product, quantity=2)
        other_store = Store.objects.create(name="فروشگاه دیگر", slug="wh-view-other5", status=Store.Status.ACTIVE)
        other_vendor = Vendor.objects.create(store=other_store, name="فروشگاه دیگر", slug="other-vendor-view")
        other_category = Category.objects.create(store=other_store, name="دیجیتال", slug="other-cat-view")
        other_product = Product.objects.create(
            store=other_store, vendor=other_vendor, category=other_category, name="کالای دیگر", slug="other-prod-view",
            sku="SKU-OTHV1", price=Decimal("1000"), stock=5,
        )
        reserve_inventory(store=other_store, product=other_product, quantity=1)

        response = self.client.get(reverse("dashboard:reservation-list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "کیف پول")
        self.assertNotContains(response, "کالای دیگر")

    def test_release_reservation(self):
        reservation = reserve_inventory(store=self.store, product=self.product, quantity=2)
        self.client.post(reverse("dashboard:reservation-release", args=[reservation.pk]))
        reservation.refresh_from_db()
        self.assertEqual(reservation.status, InventoryReservation.Status.RELEASED)

    def test_cannot_release_reservation_from_other_store(self):
        other_store = Store.objects.create(name="فروشگاه دیگر", slug="wh-view-other6", status=Store.Status.ACTIVE)
        other_vendor = Vendor.objects.create(store=other_store, name="فروشگاه دیگر", slug="other-vendor-view2")
        other_category = Category.objects.create(store=other_store, name="دیجیتال", slug="other-cat-view2")
        other_product = Product.objects.create(
            store=other_store, vendor=other_vendor, category=other_category, name="کالای دیگر", slug="other-prod-view2",
            sku="SKU-OTHV2", price=Decimal("1000"), stock=5,
        )
        other_reservation = reserve_inventory(store=other_store, product=other_product, quantity=1)
        response = self.client.post(reverse("dashboard:reservation-release", args=[other_reservation.pk]))
        self.assertEqual(response.status_code, 404)
        other_reservation.refresh_from_db()
        self.assertEqual(other_reservation.status, InventoryReservation.Status.ACTIVE)


class TransferViewsTestCase(WarehouseViewsTestCase):
    def setUp(self):
        super().setUp()
        self.source = provision_default_warehouse(self.store)
        self.destination = create_warehouse(self.store, name="مقصد", code="dest-view")
        WarehouseInventory.objects.create(store=self.store, warehouse=self.source, product=self.product, on_hand=10)

    def test_create_transfer_via_view(self):
        response = self.client.post(reverse("dashboard:transfer-add"), {
            "source_warehouse": self.source.pk, "destination_warehouse": self.destination.pk,
            f"quantity_{self.product.pk}": "3",
        }, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(WarehouseTransfer.objects.filter(store=self.store, source_warehouse=self.source).exists())

    def test_cannot_view_transfer_from_other_store(self):
        other_store = Store.objects.create(name="فروشگاه دیگر", slug="wh-view-other7", status=Store.Status.ACTIVE)
        other_source = create_warehouse(other_store, name="مبدأ دیگر", code="other-src")
        other_destination = create_warehouse(other_store, name="مقصد دیگر", code="other-dst")
        other_vendor = Vendor.objects.create(store=other_store, name="فروشگاه دیگر", slug="other-vendor-view3")
        other_category = Category.objects.create(store=other_store, name="دیجیتال", slug="other-cat-view3")
        other_product = Product.objects.create(
            store=other_store, vendor=other_vendor, category=other_category, name="کالای دیگر", slug="other-prod-view3",
            sku="SKU-OTHV3", price=Decimal("1000"), stock=5,
        )
        other_transfer = create_transfer(
            other_store, source_warehouse=other_source, destination_warehouse=other_destination,
            items=[{"product": other_product, "quantity": 1}],
        )
        response = self.client.get(reverse("dashboard:transfer-detail", args=[other_transfer.pk]))
        self.assertEqual(response.status_code, 404)

    def test_ship_and_receive_flow_via_views(self):
        transfer = create_transfer(
            self.store, source_warehouse=self.source, destination_warehouse=self.destination,
            items=[{"product": self.product, "quantity": 3}],
        )
        self.client.post(reverse("dashboard:transfer-request", args=[transfer.pk]))
        self.client.post(reverse("dashboard:transfer-ship", args=[transfer.pk]))
        transfer.refresh_from_db()
        self.assertEqual(transfer.status, WarehouseTransfer.Status.IN_TRANSIT)
        self.client.post(reverse("dashboard:transfer-receive", args=[transfer.pk]))
        transfer.refresh_from_db()
        self.assertEqual(transfer.status, WarehouseTransfer.Status.RECEIVED)

    def test_order_manager_can_view_but_not_manage_transfer(self):
        self._login_as(StoreMembership.Role.ORDER_MANAGER, "105")
        transfer = create_transfer(
            self.store, source_warehouse=self.source, destination_warehouse=self.destination,
            items=[{"product": self.product, "quantity": 1}],
        )
        response = self.client.get(reverse("dashboard:transfer-detail", args=[transfer.pk]))
        self.assertEqual(response.status_code, 200)
        response = self.client.post(reverse("dashboard:transfer-request", args=[transfer.pk]))
        self.assertEqual(response.status_code, 403)
