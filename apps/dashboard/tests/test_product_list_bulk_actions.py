"""Tests for Phase 1C product-list additions: pagination, sorting, brand
filter, and bulk actions (status change, delete, category assignment) —
including tenant isolation and permission enforcement for each."""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.catalog.models import Brand, Category, Product, Vendor
from apps.core.models import AuditLogEntry
from apps.orders.models import TaxClass
from apps.stores.models import Store, StoreMembership

User = get_user_model()

HOST = "plb-test.rastisi.ir"


def _akhlaghi():
    return Store.objects.get(slug="akhlaghi")


@override_settings(ALLOWED_HOSTS=[HOST, "testserver"])
class ProductListBulkTestCase(TestCase):
    """Uses an explicit admin-subdomain host throughout (rather than the
    default ``testserver`` + single-Store compatibility fallback), since
    several subclasses create a second Store to test tenant isolation —
    which would otherwise silently break resolution for every other
    request in the same test via the fallback's "exactly one Store" rule."""

    def setUp(self):
        self.client = Client(HTTP_HOST=HOST)
        self.store = _akhlaghi()
        self.store.admin_subdomain = "plb-test"
        self.store.save(update_fields=["admin_subdomain"])
        self.vendor = Vendor.objects.create(store=self.store, name="فروشگاه", slug="shop-plb")
        self.category = Category.objects.create(store=self.store, name="دسته", slug="cat-plb", parent=None)
        self.leaf = Category.objects.create(store=self.store, name="زیردسته", slug="leaf-plb", parent=self.category)
        self.other_leaf = Category.objects.create(store=self.store, name="زیردسته۲", slug="leaf2-plb", parent=self.category)
        self.brand_a = Brand.objects.create(store=self.store, name="برند آ", slug="brand-a-plb")
        self.brand_b = Brand.objects.create(store=self.store, name="برند ب", slug="brand-b-plb")

        self.product_a = Product.objects.create(
            store=self.store, vendor=self.vendor, category=self.leaf, brand=self.brand_a,
            name="کالای آلفا", slug="alpha-plb", sku="SKU-PLB-A", price=Decimal("300000"), stock=5,
        )
        self.product_b = Product.objects.create(
            store=self.store, vendor=self.vendor, category=self.leaf, brand=self.brand_b,
            name="کالای بتا", slug="beta-plb", sku="SKU-PLB-B", price=Decimal("100000"), stock=20,
        )

        self.owner = User.objects.create_user(username="plb-owner", password="pass12345", is_staff=True)
        StoreMembership.objects.create(
            store=self.store, user=self.owner, role=StoreMembership.Role.OWNER,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )
        self.client.login(username="plb-owner", password="pass12345")


class ProductListSortAndFilterTests(ProductListBulkTestCase):
    def test_sort_by_price_ascending(self):
        response = self.client.get(reverse("dashboard:product-list"), {"sort": "price"})
        self.assertEqual(response.status_code, 200)
        products = list(response.context["products"])
        self.assertEqual([p.pk for p in products], [self.product_b.pk, self.product_a.pk])

    def test_sort_by_price_descending(self):
        response = self.client.get(reverse("dashboard:product-list"), {"sort": "-price"})
        products = list(response.context["products"])
        self.assertEqual([p.pk for p in products], [self.product_a.pk, self.product_b.pk])

    def test_invalid_sort_falls_back_to_default(self):
        response = self.client.get(reverse("dashboard:product-list"), {"sort": "'; DROP TABLE"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["selected_sort"], "-created_at")

    def test_brand_filter(self):
        response = self.client.get(reverse("dashboard:product-list"), {"brand": self.brand_a.pk})
        products = list(response.context["products"])
        self.assertEqual([p.pk for p in products], [self.product_a.pk])

    def test_brand_options_scoped_to_store(self):
        other_store = Store.objects.create(name="Other", slug="plb-other-store")
        Brand.objects.create(store=other_store, name="برند دیگر", slug="brand-other-plb")
        response = self.client.get(reverse("dashboard:product-list"))
        brand_names = [b.name for b in response.context["brand_options"]]
        self.assertIn("برند آ", brand_names)
        self.assertNotIn("برند دیگر", brand_names)


class ProductListPaginationTests(ProductListBulkTestCase):
    def setUp(self):
        super().setUp()
        for i in range(25):
            Product.objects.create(
                store=self.store, vendor=self.vendor, category=self.leaf,
                name=f"کالای صفحه‌بندی {i}", slug=f"page-plb-{i}", sku=f"SKU-PAGE-{i}",
                price=Decimal("50000"), stock=1,
            )

    def test_first_page_has_twenty_items(self):
        response = self.client.get(reverse("dashboard:product-list"))
        self.assertEqual(len(response.context["products"]), 20)
        self.assertTrue(response.context["page_obj"].has_next())

    def test_second_page_has_remaining_items(self):
        response = self.client.get(reverse("dashboard:product-list"), {"page": 2})
        # 27 total products (2 from setUp + 25 here) -> page 2 has 7
        self.assertEqual(len(response.context["products"]), 7)
        self.assertFalse(response.context["page_obj"].has_next())

    def test_out_of_range_page_returns_last_page_not_error(self):
        response = self.client.get(reverse("dashboard:product-list"), {"page": 999})
        self.assertEqual(response.status_code, 200)


class ProductBulkStatusActionTests(ProductListBulkTestCase):
    def test_bulk_deactivate(self):
        response = self.client.post(reverse("dashboard:product-bulk-action"), {
            "bulk_action": "deactivate",
            "product_ids": [self.product_a.pk, self.product_b.pk],
        })
        self.assertEqual(response.status_code, 200)
        self.product_a.refresh_from_db()
        self.product_b.refresh_from_db()
        self.assertEqual(self.product_a.status, Product.Status.INACTIVE)
        self.assertEqual(self.product_b.status, Product.Status.INACTIVE)

    def test_bulk_activate(self):
        Product.objects.filter(pk__in=[self.product_a.pk, self.product_b.pk]).update(status=Product.Status.INACTIVE)
        self.client.post(reverse("dashboard:product-bulk-action"), {
            "bulk_action": "activate", "product_ids": [self.product_a.pk],
        })
        self.product_a.refresh_from_db()
        self.product_b.refresh_from_db()
        self.assertEqual(self.product_a.status, Product.Status.ACTIVE)
        self.assertEqual(self.product_b.status, Product.Status.INACTIVE)  # untouched

    def test_bulk_draft(self):
        self.client.post(reverse("dashboard:product-bulk-action"), {
            "bulk_action": "draft", "product_ids": [self.product_a.pk],
        })
        self.product_a.refresh_from_db()
        self.assertEqual(self.product_a.status, Product.Status.DRAFT)

    def test_bulk_delete(self):
        self.client.post(reverse("dashboard:product-bulk-action"), {
            "bulk_action": "delete", "product_ids": [self.product_a.pk],
        })
        self.assertFalse(Product.objects.filter(pk=self.product_a.pk).exists())
        self.assertTrue(Product.objects.filter(pk=self.product_b.pk).exists())

    def test_bulk_assign_category(self):
        self.client.post(reverse("dashboard:product-bulk-action"), {
            "bulk_action": "assign-category", "bulk_category": self.other_leaf.pk,
            "product_ids": [self.product_a.pk, self.product_b.pk],
        })
        self.product_a.refresh_from_db()
        self.product_b.refresh_from_db()
        self.assertEqual(self.product_a.category_id, self.other_leaf.pk)
        self.assertEqual(self.product_b.category_id, self.other_leaf.pk)

    def test_bulk_assign_tax_class(self):
        tax_class = TaxClass.objects.create(store=self.store, name="عمومی", code="general-bulk-plb")
        self.client.post(reverse("dashboard:product-bulk-action"), {
            "bulk_action": "assign-tax-class", "bulk_tax_class": tax_class.pk,
            "product_ids": [self.product_a.pk, self.product_b.pk],
        })
        self.product_a.refresh_from_db()
        self.product_b.refresh_from_db()
        self.assertEqual(self.product_a.tax_class_id, tax_class.pk)
        self.assertEqual(self.product_b.tax_class_id, tax_class.pk)
        self.assertTrue(AuditLogEntry.objects.filter(action_code="product.bulk_tax_class_assigned").exists())

    def test_bulk_clear_tax_class(self):
        tax_class = TaxClass.objects.create(store=self.store, name="عمومی", code="general-clear-plb")
        Product.objects.filter(pk=self.product_a.pk).update(tax_class=tax_class)
        self.client.post(reverse("dashboard:product-bulk-action"), {
            "bulk_action": "clear-tax-class", "product_ids": [self.product_a.pk],
        })
        self.product_a.refresh_from_db()
        self.assertIsNone(self.product_a.tax_class_id)
        self.assertTrue(AuditLogEntry.objects.filter(action_code="product.bulk_tax_class_cleared").exists())

    def test_invalid_tax_class_id_rejected(self):
        response = self.client.post(reverse("dashboard:product-bulk-action"), {
            "bulk_action": "assign-tax-class", "bulk_tax_class": "999999",
            "product_ids": [self.product_a.pk],
        })
        self.assertEqual(response.status_code, 200)
        self.product_a.refresh_from_db()
        self.assertIsNone(self.product_a.tax_class_id)

    def test_no_ids_selected_is_a_no_op(self):
        response = self.client.post(reverse("dashboard:product-bulk-action"), {"bulk_action": "delete"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Product.objects.filter(store=self.store).count(), 2)

    def test_invalid_action_is_rejected(self):
        self.client.post(reverse("dashboard:product-bulk-action"), {
            "bulk_action": "not-a-real-action", "product_ids": [self.product_a.pk],
        })
        self.product_a.refresh_from_db()
        self.assertEqual(self.product_a.status, Product.Status.ACTIVE)


class ProductBulkActionTenantIsolationTests(ProductListBulkTestCase):
    """A crafted bulk-action POST must never mutate another Store's products."""

    def setUp(self):
        super().setUp()
        self.other_store = Store.objects.create(name="Other Store", slug="plb-tenant-other")
        self.other_vendor = Vendor.objects.create(store=self.other_store, name="Vendor", slug="vendor-plb-other")
        self.other_category = Category.objects.create(store=self.other_store, name="Cat", slug="cat-plb-other")
        self.other_product = Product.objects.create(
            store=self.other_store, vendor=self.other_vendor, category=self.other_category,
            name="Other Store Product", slug="other-product-plb", sku="SKU-PLB-OTHER", price=Decimal("500000"),
        )

    def test_cannot_bulk_deactivate_other_stores_product(self):
        self.client.post(reverse("dashboard:product-bulk-action"), {
            "bulk_action": "deactivate", "product_ids": [self.other_product.pk],
        })
        self.other_product.refresh_from_db()
        self.assertEqual(self.other_product.status, Product.Status.ACTIVE)

    def test_cannot_bulk_delete_other_stores_product(self):
        self.client.post(reverse("dashboard:product-bulk-action"), {
            "bulk_action": "delete", "product_ids": [self.other_product.pk],
        })
        self.assertTrue(Product.objects.filter(pk=self.other_product.pk).exists())

    def test_mixed_own_and_other_store_ids_only_affects_own_store(self):
        self.client.post(reverse("dashboard:product-bulk-action"), {
            "bulk_action": "deactivate", "product_ids": [self.product_a.pk, self.other_product.pk],
        })
        self.product_a.refresh_from_db()
        self.other_product.refresh_from_db()
        self.assertEqual(self.product_a.status, Product.Status.INACTIVE)
        self.assertEqual(self.other_product.status, Product.Status.ACTIVE)

    def test_cannot_assign_to_other_stores_category(self):
        self.client.post(reverse("dashboard:product-bulk-action"), {
            "bulk_action": "assign-category", "bulk_category": self.other_category.pk,
            "product_ids": [self.product_a.pk],
        })
        self.product_a.refresh_from_db()
        self.assertEqual(self.product_a.category_id, self.leaf.pk)  # unchanged

    def test_cannot_assign_other_stores_tax_class(self):
        other_tax_class = TaxClass.objects.create(store=self.other_store, name="دیگر", code="other-tax-plb")
        self.client.post(reverse("dashboard:product-bulk-action"), {
            "bulk_action": "assign-tax-class", "bulk_tax_class": other_tax_class.pk,
            "product_ids": [self.product_a.pk],
        })
        self.product_a.refresh_from_db()
        self.assertIsNone(self.product_a.tax_class_id)

    def test_cannot_bulk_assign_tax_class_to_other_stores_product(self):
        tax_class = TaxClass.objects.create(store=self.store, name="عمومی", code="general-tenant-plb")
        self.client.post(reverse("dashboard:product-bulk-action"), {
            "bulk_action": "assign-tax-class", "bulk_tax_class": tax_class.pk,
            "product_ids": [self.other_product.pk],
        })
        self.other_product.refresh_from_db()
        self.assertIsNone(self.other_product.tax_class_id)


class ProductBulkActionPermissionTests(ProductListBulkTestCase):
    def _login_as(self, username, role):
        user = User.objects.create_user(username=username, password="pass12345", is_staff=True)
        StoreMembership.objects.create(
            store=self.store, user=user, role=role,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )
        self.client.logout()
        self.client.force_login(user)
        return user

    def test_analyst_cannot_bulk_deactivate(self):
        self._login_as("plb-analyst", StoreMembership.Role.ANALYST)
        response = self.client.post(reverse("dashboard:product-bulk-action"), {
            "bulk_action": "deactivate", "product_ids": [self.product_a.pk],
        })
        self.assertEqual(response.status_code, 403)
        self.product_a.refresh_from_db()
        self.assertEqual(self.product_a.status, Product.Status.ACTIVE)

    def test_catalog_manager_can_bulk_deactivate_and_delete(self):
        """CATALOG_MANAGER (Product Manager) holds the full catalog
        read/write permission set, including PRODUCT_DELETE — see the
        role-permission matrix in apps.stores.authorization."""
        self._login_as("plb-catalogmgr", StoreMembership.Role.CATALOG_MANAGER)
        response = self.client.post(reverse("dashboard:product-bulk-action"), {
            "bulk_action": "deactivate", "product_ids": [self.product_a.pk],
        })
        self.assertNotEqual(response.status_code, 403)
        self.product_a.refresh_from_db()
        self.assertEqual(self.product_a.status, Product.Status.INACTIVE)

        response = self.client.post(reverse("dashboard:product-bulk-action"), {
            "bulk_action": "delete", "product_ids": [self.product_b.pk],
        })
        self.assertNotEqual(response.status_code, 403)
        self.assertFalse(Product.objects.filter(pk=self.product_b.pk).exists())

    def test_order_manager_cannot_access_bulk_action_at_all(self):
        self._login_as("plb-ordermgr", StoreMembership.Role.ORDER_MANAGER)
        response = self.client.post(reverse("dashboard:product-bulk-action"), {
            "bulk_action": "deactivate", "product_ids": [self.product_a.pk],
        })
        self.assertEqual(response.status_code, 403)
