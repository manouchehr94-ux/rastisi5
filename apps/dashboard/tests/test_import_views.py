"""View-level tests for the Merchant Admin Import UI (checkpoint 4B §19-21):
upload → preview → execute → results flow, error-report and source
downloads, permissions, tenant isolation, invalid-file handling, and the
CSV template downloads."""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.catalog.models import Brand, Category, Product, Vendor
from apps.core.models import ImportJob
from apps.dashboard.services import import_service
from apps.orders.models import TaxClass
from apps.stores.models import Store, StoreMembership

User = get_user_model()

HOST = "import-view-test.rastisi.ir"

PRODUCT_HEADER = (
    "product_id,sku,name,slug,barcode,status,brand_code,category_code,"
    "price,stock,weight_grams,requires_shipping,tax_class_code,seo_title,seo_description\n"
)


def _akhlaghi():
    return Store.objects.get(slug="akhlaghi")


def _csv(text, name="products.csv"):
    return SimpleUploadedFile(name, text.encode("utf-8"), content_type="text/csv")


@override_settings(ALLOWED_HOSTS=[HOST, "testserver"])
class ImportViewTestCase(TestCase):
    def setUp(self):
        self.client = Client(HTTP_HOST=HOST)
        self.store = _akhlaghi()
        self.store.admin_subdomain = "import-view-test"
        self.store.save(update_fields=["admin_subdomain"])
        self.vendor = Vendor.objects.create(store=self.store, name="فروشگاه", slug="shop-ivw")
        self.category = Category.objects.create(store=self.store, name="دسته", slug="cat-ivw", parent=None)
        self.leaf = Category.objects.create(store=self.store, name="زیردسته", slug="leaf-ivw", parent=self.category)
        self.brand = Brand.objects.create(store=self.store, name="برند", slug="brand-ivw")

        self.owner = User.objects.create_user(username="ivw-owner", password="pass12345", is_staff=True)
        StoreMembership.objects.create(
            store=self.store, user=self.owner, role=StoreMembership.Role.OWNER,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )
        self.client.login(username="ivw-owner", password="pass12345")

    def _login_as(self, role, suffix):
        user = User.objects.create_user(username=f"ivw-{suffix}", password="pass12345", is_staff=True)
        StoreMembership.objects.create(
            store=self.store, user=user, role=role,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )
        self.client.logout()
        self.client.login(username=user.username, password="pass12345")

    def _valid_product_csv(self):
        return PRODUCT_HEADER + ",SKU-IVW-1,کالای وارداتی,,,active,brand-ivw,leaf-ivw,150000,8,,,,,\n"


class UploadPreviewFlowTests(ImportViewTestCase):
    def test_upload_creates_job_and_preview(self):
        response = self.client.post(reverse("dashboard:import-upload"), {
            "import_type": ImportJob.ImportType.PRODUCTS, "mode": ImportJob.Mode.CREATE_ONLY,
            "file": _csv(self._valid_product_csv()),
        })
        self.assertEqual(response.status_code, 302)
        job = ImportJob.objects.get(store=self.store)
        self.assertEqual(job.status, ImportJob.Status.PREVIEW_READY)
        self.assertEqual(job.valid_rows, 1)
        # Preview did not create the product.
        self.assertFalse(Product.objects.filter(store=self.store, sku="SKU-IVW-1").exists())
        self.assertIn(reverse("dashboard:import-detail", args=[job.pk]), response.url)

    def test_upload_without_file_errors(self):
        response = self.client.post(reverse("dashboard:import-upload"), {
            "import_type": ImportJob.ImportType.PRODUCTS, "mode": ImportJob.Mode.UPSERT,
        })
        self.assertEqual(response.status_code, 302)
        self.assertFalse(ImportJob.objects.exists())

    def test_upload_non_csv_rejected(self):
        response = self.client.post(reverse("dashboard:import-upload"), {
            "import_type": ImportJob.ImportType.PRODUCTS, "mode": ImportJob.Mode.UPSERT,
            "file": SimpleUploadedFile("data.xlsx", b"binary", content_type="application/octet-stream"),
        })
        self.assertEqual(response.status_code, 302)
        self.assertFalse(ImportJob.objects.exists())

    def test_execute_runs_and_creates_product(self):
        self.client.post(reverse("dashboard:import-upload"), {
            "import_type": ImportJob.ImportType.PRODUCTS, "mode": ImportJob.Mode.CREATE_ONLY,
            "file": _csv(self._valid_product_csv()),
        })
        job = ImportJob.objects.get(store=self.store)
        response = self.client.post(reverse("dashboard:import-execute", args=[job.pk]))
        self.assertEqual(response.status_code, 302)
        job.refresh_from_db()
        self.assertEqual(job.status, ImportJob.Status.COMPLETED)
        self.assertTrue(Product.objects.filter(store=self.store, sku="SKU-IVW-1").exists())

    def test_detail_page_renders(self):
        self.client.post(reverse("dashboard:import-upload"), {
            "import_type": ImportJob.ImportType.PRODUCTS, "mode": ImportJob.Mode.CREATE_ONLY,
            "file": _csv(self._valid_product_csv()),
        })
        job = ImportJob.objects.get(store=self.store)
        response = self.client.get(reverse("dashboard:import-detail", args=[job.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "نتیجه‌ی ردیف‌ها")


class ErrorReportTests(ImportViewTestCase):
    def test_error_report_generated_and_downloadable(self):
        bad_csv = PRODUCT_HEADER + ",,,,,,,,,,,,,,\n"  # invalid: no name/category/price
        self.client.post(reverse("dashboard:import-upload"), {
            "import_type": ImportJob.ImportType.PRODUCTS, "mode": ImportJob.Mode.CREATE_ONLY,
            "file": _csv(bad_csv),
        })
        job = ImportJob.objects.get(store=self.store)
        self.client.post(reverse("dashboard:import-execute", args=[job.pk]))
        job.refresh_from_db()
        self.assertTrue(job.error_report_file)
        response = self.client.get(reverse("dashboard:import-download-errors", args=[job.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/csv")

    def test_source_downloadable(self):
        self.client.post(reverse("dashboard:import-upload"), {
            "import_type": ImportJob.ImportType.PRODUCTS, "mode": ImportJob.Mode.CREATE_ONLY,
            "file": _csv(self._valid_product_csv()),
        })
        job = ImportJob.objects.get(store=self.store)
        response = self.client.get(reverse("dashboard:import-download-source", args=[job.pk]))
        self.assertEqual(response.status_code, 200)


class TemplateDownloadTests(ImportViewTestCase):
    def test_product_template(self):
        response = self.client.get(reverse("dashboard:import-template", args=["products"]))
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"category_code", response.content)

    def test_variant_template(self):
        response = self.client.get(reverse("dashboard:import-template", args=["variants"]))
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"option_1_code", response.content)

    def test_inventory_template(self):
        response = self.client.get(reverse("dashboard:import-template", args=["inventory"]))
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"warehouse_code", response.content)

    def test_invalid_template_type_404(self):
        response = self.client.get(reverse("dashboard:import-template", args=["not-a-type"]))
        self.assertEqual(response.status_code, 404)


class PermissionTests(ImportViewTestCase):
    def test_analyst_can_view_but_not_upload(self):
        self._login_as(StoreMembership.Role.ANALYST, "analyst")
        self.assertEqual(self.client.get(reverse("dashboard:import-list")).status_code, 200)
        response = self.client.post(reverse("dashboard:import-upload"), {
            "import_type": ImportJob.ImportType.PRODUCTS, "mode": ImportJob.Mode.CREATE_ONLY,
            "file": _csv(self._valid_product_csv()),
        })
        self.assertEqual(response.status_code, 403)

    def test_catalog_manager_can_upload(self):
        self._login_as(StoreMembership.Role.CATALOG_MANAGER, "catmgr")
        response = self.client.post(reverse("dashboard:import-upload"), {
            "import_type": ImportJob.ImportType.PRODUCTS, "mode": ImportJob.Mode.CREATE_ONLY,
            "file": _csv(self._valid_product_csv()),
        })
        self.assertEqual(response.status_code, 302)
        self.assertTrue(ImportJob.objects.filter(store=self.store).exists())

    def test_content_editor_cannot_view(self):
        self._login_as(StoreMembership.Role.CONTENT_EDITOR, "content")
        self.assertEqual(self.client.get(reverse("dashboard:import-list")).status_code, 403)

    def test_anonymous_denied(self):
        self.client.logout()
        response = self.client.get(reverse("dashboard:import-list"))
        self.assertEqual(response.status_code, 302)

    def test_csrf_enforced_on_upload(self):
        csrf_client = Client(HTTP_HOST=HOST, enforce_csrf_checks=True)
        csrf_client.login(username="ivw-owner", password="pass12345")
        response = csrf_client.post(reverse("dashboard:import-upload"), {
            "import_type": ImportJob.ImportType.PRODUCTS, "mode": ImportJob.Mode.CREATE_ONLY,
            "file": _csv(self._valid_product_csv()),
        })
        self.assertEqual(response.status_code, 403)


class TenantIsolationTests(ImportViewTestCase):
    def setUp(self):
        super().setUp()
        self.other_store = Store.objects.create(name="فروشگاه دیگر", slug="ivw-other-store")
        self.other_job = ImportJob.objects.create(
            store=self.other_store, import_type=ImportJob.ImportType.PRODUCTS,
            status=ImportJob.Status.PREVIEW_READY,
        )

    def test_cannot_view_other_stores_job(self):
        response = self.client.get(reverse("dashboard:import-detail", args=[self.other_job.pk]))
        self.assertEqual(response.status_code, 404)

    def test_cannot_execute_other_stores_job(self):
        response = self.client.post(reverse("dashboard:import-execute", args=[self.other_job.pk]))
        self.assertEqual(response.status_code, 404)

    def test_cannot_download_other_stores_source(self):
        response = self.client.get(reverse("dashboard:import-download-source", args=[self.other_job.pk]))
        self.assertEqual(response.status_code, 404)

    def test_cannot_download_other_stores_errors(self):
        response = self.client.get(reverse("dashboard:import-download-errors", args=[self.other_job.pk]))
        self.assertEqual(response.status_code, 404)

    def test_import_list_only_shows_own_store(self):
        response = self.client.get(reverse("dashboard:import-list"))
        jobs = list(response.context["jobs"])
        self.assertTrue(all(j.store_id == self.store.pk for j in jobs))
