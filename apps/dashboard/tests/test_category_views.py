import json
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.catalog.models import Category, Product, Vendor

User = get_user_model()


class CategoryViewsTestCase(TestCase):
    def setUp(self):
        self.main = Category.objects.create(name="گروه اصلی", slug="main-cv", icon="📦")
        self.sub = Category.objects.create(name="زیرگروه", slug="sub-cv", parent=self.main, icon="📱")
        self.staff = User.objects.create_user(username="09121123001", password="pass12345", is_staff=True)
        self.client.login(username="09121123001", password="pass12345")


class CategoryListViewTests(CategoryViewsTestCase):
    def test_renders_tree(self):
        response = self.client.get(reverse("dashboard:category-list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "گروه اصلی")
        self.assertContains(response, "زیرگروه")

    def test_anonymous_denied(self):
        self.client.logout()
        response = self.client.get(reverse("dashboard:category-list"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin-panel/login/", response.url)


class CategoryAddMainTests(CategoryViewsTestCase):
    def test_valid_add_creates_category(self):
        response = self.client.post(reverse("dashboard:category-add-main"), {"name": "گروه تازه", "icon": "🆕"})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(Category.objects.filter(name="گروه تازه", parent__isnull=True).exists())
        trigger = json.loads(response.headers["HX-Trigger"])
        self.assertIn("اضافه شد", trigger["toast"]["message"])

    def test_blank_icon_defaults_to_folder(self):
        self.client.post(reverse("dashboard:category-add-main"), {"name": "گروه بی‌آیکون", "icon": ""})
        category = Category.objects.get(name="گروه بی‌آیکون")
        self.assertEqual(category.icon, "📁")

    def test_blank_name_rejected(self):
        response = self.client.post(reverse("dashboard:category-add-main"), {"name": "", "icon": ""})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Category.objects.filter(icon="").exists())


class CategoryAddSubTests(CategoryViewsTestCase):
    def test_valid_add_creates_subcategory(self):
        response = self.client.post(reverse("dashboard:category-add-sub"), {
            "parent": self.main.id, "name": "زیرگروه تازه", "icon": "",
        })
        self.assertEqual(response.status_code, 200)
        created = Category.objects.get(name="زیرگروه تازه")
        self.assertEqual(created.parent, self.main)

    def test_missing_parent_rejected(self):
        response = self.client.post(reverse("dashboard:category-add-sub"), {"parent": "", "name": "بی‌والد"})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Category.objects.filter(name="بی‌والد").exists())


class CategoryEditViewTests(CategoryViewsTestCase):
    def test_get_prefills_form(self):
        response = self.client.get(reverse("dashboard:category-edit", args=[self.sub.pk]))
        self.assertContains(response, "زیرگروه")

    def test_valid_edit_updates_category(self):
        response = self.client.post(reverse("dashboard:category-edit", args=[self.sub.pk]), {
            "name": "زیرگروه ویرایش‌شده", "icon": "🆕",
        })
        self.assertEqual(response.status_code, 200)
        self.sub.refresh_from_db()
        self.assertEqual(self.sub.name, "زیرگروه ویرایش‌شده")
        self.assertEqual(self.sub.icon, "🆕")
        trigger = json.loads(response.headers["HX-Trigger"])
        self.assertIn("modal-close", trigger)

    def test_blank_name_rejected(self):
        response = self.client.post(reverse("dashboard:category-edit", args=[self.sub.pk]), {"name": ""})
        self.sub.refresh_from_db()
        self.assertEqual(self.sub.name, "زیرگروه")


class CategoryDeleteViewTests(CategoryViewsTestCase):
    def test_deletes_empty_leaf_category(self):
        response = self.client.post(reverse("dashboard:category-delete", args=[self.sub.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Category.objects.filter(pk=self.sub.pk).exists())
        trigger = json.loads(response.headers["HX-Trigger"])
        self.assertIn("حذف شد", trigger["toast"]["message"])

    def test_cannot_delete_category_with_children(self):
        response = self.client.post(reverse("dashboard:category-delete", args=[self.main.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(Category.objects.filter(pk=self.main.pk).exists())
        self.assertTrue(Category.objects.filter(pk=self.sub.pk).exists())
        trigger = json.loads(response.headers["HX-Trigger"])
        self.assertIn("زیرگروه", trigger["toast"]["message"])

    def test_cannot_delete_category_with_products(self):
        vendor = Vendor.objects.create(name="فروشگاه", slug="shop-cd")
        Product.objects.create(
            vendor=vendor, category=self.sub, name="محصول", slug="prod-cd",
            sku="SKU-CDV1", price=Decimal("1000"),
        )
        response = self.client.post(reverse("dashboard:category-delete", args=[self.sub.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(Category.objects.filter(pk=self.sub.pk).exists())
        trigger = json.loads(response.headers["HX-Trigger"])
        self.assertIn("کالا", trigger["toast"]["message"])

    def test_non_staff_cannot_delete(self):
        self.client.logout()
        other = User.objects.create_user(username="09121123099", password="pass12345", is_staff=False)
        self.client.login(username="09121123099", password="pass12345")
        response = self.client.post(reverse("dashboard:category-delete", args=[self.sub.pk]))
        self.assertRedirects(response, reverse("catalog:home"))
        self.assertTrue(Category.objects.filter(pk=self.sub.pk).exists())
