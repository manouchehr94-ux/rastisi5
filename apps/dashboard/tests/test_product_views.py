import json
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.catalog.models import Category, Product, Vendor
from apps.stores.models import Store

User = get_user_model()


def _akhlaghi():
    return Store.objects.get(slug="akhlaghi")


class ProductViewsTestCase(TestCase):
    def setUp(self):
        self.store = _akhlaghi()
        self.vendor = Vendor.objects.create(store=self.store, name="فروشگاه", slug="shop-pv")
        self.main = Category.objects.create(store=self.store, name="دیجیتال", slug="main-pv")
        self.sub = Category.objects.create(store=self.store, name="موبایل", slug="sub-pv", parent=self.main)
        self.product = Product.objects.create(
            store=self.store, vendor=self.vendor, category=self.sub, name="گوشی هوشمند", slug="phone-pv",
            sku="SKU-PV1", price=Decimal("1000000"), stock=5,
        )
        self.staff = User.objects.create_user(username="09121122001", password="pass12345", is_staff=True)
        self.client.login(username="09121122001", password="pass12345")


class ProductListViewTests(ProductViewsTestCase):
    def test_renders_product_table(self):
        response = self.client.get(reverse("dashboard:product-list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "گوشی هوشمند")
        self.assertContains(response, "SKU-PV1")

    def test_anonymous_denied(self):
        self.client.logout()
        response = self.client.get(reverse("dashboard:product-list"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin-panel/login/", response.url)

    def test_search_filters_table(self):
        response = self.client.get(reverse("dashboard:product-table"), {"q": "گوشی"})
        self.assertContains(response, "گوشی هوشمند")

    def test_search_excludes_non_matching(self):
        response = self.client.get(reverse("dashboard:product-table"), {"q": "چیز-نامرتبط"})
        self.assertNotContains(response, "گوشی هوشمند")
        self.assertContains(response, "کالایی یافت نشد")

    def test_out_of_stock_filter(self):
        Product.objects.create(
            store=self.store, vendor=self.vendor, category=self.sub, name="کالای ناموجود", slug="oos-pv",
            sku="SKU-PV2", price=Decimal("1000"), stock=0,
        )
        response = self.client.get(reverse("dashboard:product-table"), {"status": "out"})
        self.assertContains(response, "کالای ناموجود")
        self.assertNotContains(response, "گوشی هوشمند")


class ProductAddViewTests(ProductViewsTestCase):
    def _payload(self, **overrides):
        payload = {
            "name": "کالای جدید", "sku": "SKU-NEW1", "category": self.sub.id,
            "price": "500000", "discount_percent": "0", "stock": "10",
            "status": "active", "icon": "🎁", "description": "",
        }
        payload.update(overrides)
        return payload

    def test_get_returns_empty_form(self):
        response = self.client.get(reverse("dashboard:product-add"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "افزودن کالای جدید")

    def test_valid_post_creates_product(self):
        response = self.client.post(reverse("dashboard:product-add"), self._payload())
        self.assertEqual(response.status_code, 200)
        product = Product.objects.get(sku="SKU-NEW1")
        self.assertEqual(product.name, "کالای جدید")
        self.assertEqual(product.vendor, self.vendor)
        self.assertTrue(product.slug)
        trigger = json.loads(response.headers["HX-Trigger"])
        self.assertIn("modal-close", trigger)

    def test_persian_digits_are_normalized(self):
        response = self.client.post(reverse("dashboard:product-add"), self._payload(
            price="۵۰۰۰۰۰", discount_percent="۱۰", stock="۷",
        ))
        self.assertEqual(response.status_code, 200)
        product = Product.objects.get(sku="SKU-NEW1")
        self.assertEqual(product.price, Decimal("500000"))
        self.assertEqual(product.discount_percent, 10)
        self.assertEqual(product.stock, 7)

    def test_duplicate_sku_rejected(self):
        response = self.client.post(reverse("dashboard:product-add"), self._payload(sku="SKU-PV1"))
        self.assertContains(response, "قبلاً استفاده شده است")
        self.assertEqual(Product.objects.filter(sku="SKU-PV1").count(), 1)

    def test_missing_required_fields_rejected(self):
        response = self.client.post(reverse("dashboard:product-add"), self._payload(name="", category=""))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Product.objects.filter(sku="SKU-NEW1").exists())

    def test_top_level_category_not_offered(self):
        response = self.client.get(reverse("dashboard:product-add"))
        self.assertNotContains(response, f'value="{self.main.id}"')

    def test_blank_icon_defaults(self):
        self.client.post(reverse("dashboard:product-add"), self._payload(icon=""))
        product = Product.objects.get(sku="SKU-NEW1")
        self.assertEqual(product.icon, "🛍️")


class ProductEditViewTests(ProductViewsTestCase):
    def test_get_prefills_form(self):
        response = self.client.get(reverse("dashboard:product-edit", args=[self.product.pk]))
        self.assertContains(response, "ویرایش کالا")
        self.assertContains(response, "گوشی هوشمند")

    def test_valid_edit_updates_product(self):
        payload = {
            "name": "گوشی هوشمند - ویرایش‌شده", "sku": "SKU-PV1", "category": self.sub.id,
            "price": "1200000", "discount_percent": "5", "stock": "3",
            "status": "active", "icon": "📱", "description": "",
        }
        response = self.client.post(reverse("dashboard:product-edit", args=[self.product.pk]), payload)
        self.assertEqual(response.status_code, 200)
        self.product.refresh_from_db()
        self.assertEqual(self.product.name, "گوشی هوشمند - ویرایش‌شده")
        self.assertEqual(self.product.stock, 3)

    def test_editing_does_not_change_slug(self):
        original_slug = self.product.slug
        payload = {
            "name": "نام کاملاً متفاوت", "sku": "SKU-PV1", "category": self.sub.id,
            "price": "1200000", "discount_percent": "0", "stock": "3",
            "status": "active", "icon": "", "description": "",
        }
        self.client.post(reverse("dashboard:product-edit", args=[self.product.pk]), payload)
        self.product.refresh_from_db()
        self.assertEqual(self.product.slug, original_slug)

    def test_sku_uniqueness_excludes_self(self):
        payload = {
            "name": "گوشی هوشمند", "sku": "SKU-PV1", "category": self.sub.id,
            "price": "1000000", "discount_percent": "0", "stock": "5",
            "status": "active", "icon": "", "description": "",
        }
        response = self.client.post(reverse("dashboard:product-edit", args=[self.product.pk]), payload)
        self.assertNotContains(response, "قبلاً استفاده شده است")


class ProductDeleteViewTests(ProductViewsTestCase):
    def test_deletes_product(self):
        response = self.client.post(reverse("dashboard:product-delete", args=[self.product.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Product.objects.filter(pk=self.product.pk).exists())
        trigger = json.loads(response.headers["HX-Trigger"])
        self.assertIn("حذف شد", trigger["toast"]["message"])

    def test_get_not_allowed(self):
        response = self.client.get(reverse("dashboard:product-delete", args=[self.product.pk]))
        self.assertEqual(response.status_code, 405)

    def test_non_staff_cannot_delete(self):
        self.client.logout()
        other = User.objects.create_user(username="09121122099", password="pass12345", is_staff=False)
        self.client.login(username="09121122099", password="pass12345")
        response = self.client.post(reverse("dashboard:product-delete", args=[self.product.pk]))
        self.assertRedirects(response, reverse("catalog:home"))
        self.assertTrue(Product.objects.filter(pk=self.product.pk).exists())
