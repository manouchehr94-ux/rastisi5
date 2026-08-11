"""Tests for the Checkpoint 4 Export domain: generating CSV exports for all
five export types, permission enforcement, tenant isolation, CSV-injection
protection, and the authenticated Store-scoped download view."""

from decimal import Decimal

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.catalog.models import Brand, Category, Product, Vendor, Warehouse, WarehouseInventory
from apps.core.models import AuditLogEntry, ExportJob
from apps.core.services.export_service import ExportError, run_export
from apps.customers.models import Customer
from apps.orders.models import (
    Order,
    PaymentGateway,
    ShippingMethod,
    ShippingZone,
    TaxClass,
)
from apps.stores.models import Store, StoreMembership

User = get_user_model()

HOST = f"export-test.{settings.RASTISI_ADMIN_DOMAIN_SUFFIX}"


def _akhlaghi():
    return Store.objects.get(slug="akhlaghi")


@override_settings(ALLOWED_HOSTS=[HOST, "testserver"])
class ExportTestCase(TestCase):
    def setUp(self):
        self.client = Client(HTTP_HOST=HOST)
        self.store = _akhlaghi()
        self.store.admin_subdomain = "export-test"
        self.store.save(update_fields=["admin_subdomain"])

        self.vendor = Vendor.objects.create(store=self.store, name="فروشگاه", slug="shop-exp")
        self.category = Category.objects.create(store=self.store, name="دسته", slug="cat-exp", parent=None)
        self.leaf = Category.objects.create(store=self.store, name="زیردسته", slug="leaf-exp", parent=self.category)
        self.brand = Brand.objects.create(store=self.store, name="برند", slug="brand-exp")
        self.tax_class = TaxClass.objects.create(store=self.store, name="عمومی", code="general-exp")

        self.product = Product.objects.create(
            store=self.store, vendor=self.vendor, category=self.leaf, brand=self.brand,
            tax_class=self.tax_class,
            name="=cmd|'/c calc'!A1", slug="formula-product-exp", sku="SKU-EXP-1",
            price=Decimal("150000"), stock=30,
        )
        self.warehouse = Warehouse.objects.filter(store=self.store, is_default=True).first()
        if self.warehouse is None:
            self.warehouse = Warehouse.objects.create(
                store=self.store, name="انبار اصلی", code="main-exp", is_default=True,
            )
        WarehouseInventory.objects.filter(store=self.store, warehouse=self.warehouse, product=self.product).delete()
        WarehouseInventory.objects.create(
            store=self.store, warehouse=self.warehouse, product=self.product, on_hand=30,
        )

        user_model_user = User.objects.create_user(username="09121110001", password="pass12345")
        self.customer = Customer.objects.create(
            user=user_model_user, full_name="مشتری تست", phone="09121110001", email="c@example.com",
        )
        self.zone = ShippingZone.objects.create(store=self.store, name="منطقه", code="zone-exp")
        self.shipping_method = ShippingMethod.objects.create(
            store=self.store, zone=self.zone, name="ارسال عادی", slug="std-exp",
        )
        self.gateway = PaymentGateway.objects.create(store=self.store, name="درگاه", slug="gw-exp")
        self.order = Order.objects.create(
            store=self.store, customer=self.customer, vendor=self.vendor, code="ORD-EXP-1",
            address={}, shipping_method=self.shipping_method, payment_gateway=self.gateway,
            status=Order.Status.DELIVERED, payment_status=Order.PaymentStatus.PAID,
            items_total=Decimal("150000"), grand_total=Decimal("150000"),
        )

        self.owner = User.objects.create_user(username="exp-owner", password="pass12345", is_staff=True)
        StoreMembership.objects.create(
            store=self.store, user=self.owner, role=StoreMembership.Role.OWNER,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )
        self.client.login(username="exp-owner", password="pass12345")

    def _login_as(self, role, suffix):
        user = User.objects.create_user(username=f"exp-role-{suffix}", password="pass12345", is_staff=True)
        StoreMembership.objects.create(
            store=self.store, user=user, role=role,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )
        self.client.logout()
        self.client.login(username=user.username, password="pass12345")


class RunExportServiceTests(ExportTestCase):
    def test_products_export_generates_completed_job_with_row(self):
        job = run_export(self.store, ExportJob.ExportType.PRODUCTS, requested_by=self.owner)
        self.assertEqual(job.status, ExportJob.Status.COMPLETED)
        self.assertEqual(job.row_count, 1)
        self.assertTrue(job.file.name)

    def test_csv_injection_formula_prefix_neutralized(self):
        job = run_export(self.store, ExportJob.ExportType.PRODUCTS, requested_by=self.owner)
        content = job.file.read().decode("utf-8")
        self.assertNotIn("\n=cmd", content)
        self.assertIn("'=cmd", content)

    def test_variants_export_runs(self):
        job = run_export(self.store, ExportJob.ExportType.VARIANTS, requested_by=self.owner)
        self.assertEqual(job.status, ExportJob.Status.COMPLETED)

    def test_inventory_export_reports_on_hand_and_available(self):
        job = run_export(self.store, ExportJob.ExportType.INVENTORY, requested_by=self.owner)
        self.assertEqual(job.status, ExportJob.Status.COMPLETED)
        content = job.file.read().decode("utf-8")
        self.assertIn("30", content)

    def test_customers_export_scopes_totals_to_store(self):
        job = run_export(self.store, ExportJob.ExportType.CUSTOMERS, requested_by=self.owner)
        self.assertEqual(job.status, ExportJob.Status.COMPLETED)
        self.assertEqual(job.row_count, 1)

    def test_orders_export_runs(self):
        job = run_export(self.store, ExportJob.ExportType.ORDERS, requested_by=self.owner)
        self.assertEqual(job.status, ExportJob.Status.COMPLETED)
        content = job.file.read().decode("utf-8")
        self.assertIn("ORD-EXP-1", content)

    def test_invalid_export_type_rejected(self):
        with self.assertRaises(ExportError):
            run_export(self.store, "not-a-real-type", requested_by=self.owner)

    def test_completion_is_audit_logged(self):
        run_export(self.store, ExportJob.ExportType.PRODUCTS, requested_by=self.owner)
        self.assertTrue(
            AuditLogEntry.objects.filter(store=self.store, action_code="export.completed").exists()
        )


class ExportViewsTests(ExportTestCase):
    def test_owner_can_create_and_list(self):
        response = self.client.post(
            reverse("dashboard:export-create"), {"export_type": ExportJob.ExportType.PRODUCTS},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(ExportJob.objects.filter(store=self.store).count(), 1)
        response = self.client.get(reverse("dashboard:export-list"))
        self.assertEqual(response.status_code, 200)

    def test_content_editor_cannot_create_export(self):
        self._login_as(StoreMembership.Role.CONTENT_EDITOR, "1")
        response = self.client.post(
            reverse("dashboard:export-create"), {"export_type": ExportJob.ExportType.PRODUCTS},
        )
        self.assertEqual(response.status_code, 403)

    def test_catalog_manager_cannot_export_customers(self):
        self._login_as(StoreMembership.Role.CATALOG_MANAGER, "2")
        response = self.client.post(
            reverse("dashboard:export-create"), {"export_type": ExportJob.ExportType.CUSTOMERS},
        )
        self.assertEqual(response.status_code, 403)

    def test_order_manager_can_export_customers(self):
        self._login_as(StoreMembership.Role.ORDER_MANAGER, "3")
        response = self.client.post(
            reverse("dashboard:export-create"), {"export_type": ExportJob.ExportType.CUSTOMERS},
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(ExportJob.objects.filter(store=self.store, export_type="customers").exists())

    def test_analyst_cannot_export_customers(self):
        self._login_as(StoreMembership.Role.ANALYST, "4")
        response = self.client.post(
            reverse("dashboard:export-create"), {"export_type": ExportJob.ExportType.CUSTOMERS},
        )
        self.assertEqual(response.status_code, 403)

    def test_download_completed_job(self):
        job = run_export(self.store, ExportJob.ExportType.PRODUCTS, requested_by=self.owner)
        response = self.client.get(reverse("dashboard:export-download", args=[job.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/csv")

    def test_download_pending_job_404(self):
        job = ExportJob.objects.create(store=self.store, export_type=ExportJob.ExportType.PRODUCTS)
        response = self.client.get(reverse("dashboard:export-download", args=[job.pk]))
        self.assertEqual(response.status_code, 404)

    def test_anonymous_denied(self):
        self.client.logout()
        response = self.client.get(reverse("dashboard:export-list"))
        self.assertEqual(response.status_code, 302)


class ExportTenantIsolationTests(ExportTestCase):
    def setUp(self):
        super().setUp()
        self.other_store = Store.objects.create(name="فروشگاه دیگر", slug="export-other-store")

    def test_cannot_download_other_stores_export(self):
        other_job = run_export(self.other_store, ExportJob.ExportType.PRODUCTS, requested_by=None)
        response = self.client.get(reverse("dashboard:export-download", args=[other_job.pk]))
        self.assertEqual(response.status_code, 404)

    def test_export_list_only_shows_own_store(self):
        run_export(self.other_store, ExportJob.ExportType.PRODUCTS, requested_by=None)
        run_export(self.store, ExportJob.ExportType.PRODUCTS, requested_by=self.owner)
        response = self.client.get(reverse("dashboard:export-list"))
        jobs = list(response.context["jobs"])
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0].store_id, self.store.pk)

    def test_products_export_never_includes_other_stores_products(self):
        other_vendor = Vendor.objects.create(store=self.other_store, name="ف", slug="v-other-exp")
        other_category = Category.objects.create(store=self.other_store, name="د", slug="c-other-exp")
        Product.objects.create(
            store=self.other_store, vendor=other_vendor, category=other_category,
            name="کالای فروشگاه دیگر", slug="other-store-product-exp", sku="SKU-OTHER-EXP",
            price=Decimal("1"), stock=1,
        )
        job = run_export(self.store, ExportJob.ExportType.PRODUCTS, requested_by=self.owner)
        content = job.file.read().decode("utf-8")
        self.assertNotIn("کالای فروشگاه دیگر", content)
