from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.catalog.models import Category, CategoryAttributeSchema
from apps.catalog.services.attribute_service import create_attribute
from apps.catalog.services.category_schema_service import add_category_attribute
from apps.stores.models import Store, StoreMembership

User = get_user_model()

HOST = "csv-test.rastisi.ir"


def _akhlaghi():
    return Store.objects.get(slug="akhlaghi")


@override_settings(ALLOWED_HOSTS=[HOST, "testserver"])
class CategorySchemaViewsTestCase(TestCase):
    def setUp(self):
        self.store = _akhlaghi()
        self.store.admin_subdomain = HOST.split(".")[0]
        self.store.save(update_fields=["admin_subdomain"])
        self.category = Category.objects.create(store=self.store, name="پوشاک", slug="csv-cat")
        self.material = create_attribute(self.store, label="جنس")
        self.staff = User.objects.create_user(username="09121177001", password="pass12345", is_staff=True)
        StoreMembership.objects.create(
            store=self.store, user=self.staff, role=StoreMembership.Role.OWNER,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )
        self.client = Client(HTTP_HOST=HOST)
        self.client.login(username="09121177001", password="pass12345")


class CategorySchemaPageTests(CategorySchemaViewsTestCase):
    def test_renders_modal(self):
        response = self.client.get(reverse("dashboard:category-schema", args=[self.category.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "طرح ویژگی")

    def test_other_store_category_404s(self):
        other_store = Store.objects.create(name="فروشگاه دیگر", slug="csv-other", status=Store.Status.ACTIVE)
        other_category = Category.objects.create(store=other_store, name="دسته دیگر", slug="csv-other-cat")
        response = self.client.get(reverse("dashboard:category-schema", args=[other_category.pk]))
        self.assertEqual(response.status_code, 404)


class CategorySchemaAddViewTests(CategorySchemaViewsTestCase):
    def test_adds_attribute(self):
        response = self.client.post(reverse("dashboard:category-schema-add", args=[self.category.pk]), {
            "attribute": self.material.pk, "group": "عمومی", "is_required": "on",
        })
        self.assertEqual(response.status_code, 200)
        entry = CategoryAttributeSchema.objects.get(category=self.category, attribute=self.material)
        self.assertTrue(entry.is_required)

    def test_duplicate_rejected(self):
        add_category_attribute(self.category, self.material)
        response = self.client.post(reverse("dashboard:category-schema-add", args=[self.category.pk]), {
            "attribute": self.material.pk,
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(CategoryAttributeSchema.objects.filter(category=self.category).count(), 1)

    def test_cross_store_attribute_id_rejected(self):
        other_store = Store.objects.create(name="فروشگاه دیگر", slug="csv-other2", status=Store.Status.ACTIVE)
        other_attr = create_attribute(other_store, label="ویژگی دیگر")
        response = self.client.post(reverse("dashboard:category-schema-add", args=[self.category.pk]), {
            "attribute": other_attr.pk,
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(CategoryAttributeSchema.objects.filter(category=self.category).exists())


class CategorySchemaToggleRemoveMoveTests(CategorySchemaViewsTestCase):
    def test_toggle_required(self):
        entry = add_category_attribute(self.category, self.material)
        self.client.post(reverse("dashboard:category-schema-toggle-required", args=[self.category.pk, entry.pk]))
        entry.refresh_from_db()
        self.assertTrue(entry.is_required)

    def test_remove(self):
        entry = add_category_attribute(self.category, self.material)
        self.client.post(reverse("dashboard:category-schema-remove", args=[self.category.pk, entry.pk]))
        self.assertFalse(CategoryAttributeSchema.objects.filter(pk=entry.pk).exists())

    def test_move_up(self):
        season = create_attribute(self.store, label="فصل")
        e1 = add_category_attribute(self.category, self.material)
        e2 = add_category_attribute(self.category, season)
        self.client.post(
            reverse("dashboard:category-schema-move", args=[self.category.pk, e2.pk]), {"direction": "up"},
        )
        e1.refresh_from_db()
        e2.refresh_from_db()
        self.assertEqual(e2.display_order, 0)
        self.assertEqual(e1.display_order, 1)

    def test_entry_from_other_category_404s(self):
        other_category = Category.objects.create(store=self.store, name="کفش", slug="csv-shoes")
        entry = add_category_attribute(other_category, self.material)
        response = self.client.post(
            reverse("dashboard:category-schema-remove", args=[self.category.pk, entry.pk])
        )
        self.assertEqual(response.status_code, 404)
        self.assertTrue(CategoryAttributeSchema.objects.filter(pk=entry.pk).exists())


class CategorySchemaPermissionTests(CategorySchemaViewsTestCase):
    def _login_as(self, role, suffix):
        user = User.objects.create_user(username=f"09121177{suffix}", password="pass12345", is_staff=True)
        StoreMembership.objects.create(
            store=self.store, user=user, role=role,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )
        self.client.logout()
        self.client.login(username=user.username, password="pass12345")

    def test_catalog_manager_can_manage_schema(self):
        self._login_as(StoreMembership.Role.CATALOG_MANAGER, "301")
        response = self.client.post(reverse("dashboard:category-schema-add", args=[self.category.pk]), {
            "attribute": self.material.pk,
        })
        self.assertEqual(response.status_code, 200)
        self.assertTrue(CategoryAttributeSchema.objects.filter(category=self.category).exists())

    def test_analyst_cannot_manage_schema(self):
        self._login_as(StoreMembership.Role.ANALYST, "302")
        response = self.client.post(reverse("dashboard:category-schema-add", args=[self.category.pk]), {
            "attribute": self.material.pk,
        })
        self.assertEqual(response.status_code, 403)

    def test_order_manager_cannot_view_schema(self):
        self._login_as(StoreMembership.Role.ORDER_MANAGER, "303")
        response = self.client.get(reverse("dashboard:category-schema", args=[self.category.pk]))
        self.assertEqual(response.status_code, 403)


class CategorySchemaOverrideTests(CategorySchemaViewsTestCase):
    """نگاه کنید به بخش ۳۱ پرامپت فاز ۱F — کنترل‌های بازنویسیِ فیلتر/مقایسه/جست‌وجو/نمایش."""

    def setUp(self):
        super().setUp()
        self.entry = add_category_attribute(self.category, self.material)

    def test_filterable_override_cycles_inherit_true_false_inherit(self):
        self.assertIsNone(self.entry.is_filterable_override)

        self.client.post(
            reverse("dashboard:category-schema-toggle-override", args=[self.category.pk, self.entry.pk]),
            {"field": "filterable"},
        )
        self.entry.refresh_from_db()
        self.assertTrue(self.entry.is_filterable_override)

        self.client.post(
            reverse("dashboard:category-schema-toggle-override", args=[self.category.pk, self.entry.pk]),
            {"field": "filterable"},
        )
        self.entry.refresh_from_db()
        self.assertFalse(self.entry.is_filterable_override)

        self.client.post(
            reverse("dashboard:category-schema-toggle-override", args=[self.category.pk, self.entry.pk]),
            {"field": "filterable"},
        )
        self.entry.refresh_from_db()
        self.assertIsNone(self.entry.is_filterable_override)

    def test_comparable_override_toggle_independent_of_filterable(self):
        self.client.post(
            reverse("dashboard:category-schema-toggle-override", args=[self.category.pk, self.entry.pk]),
            {"field": "comparable"},
        )
        self.entry.refresh_from_db()
        self.assertTrue(self.entry.is_comparable_override)
        self.assertIsNone(self.entry.is_filterable_override)
        self.assertIsNone(self.entry.is_searchable_override)

    def test_searchable_override_toggle(self):
        self.client.post(
            reverse("dashboard:category-schema-toggle-override", args=[self.category.pk, self.entry.pk]),
            {"field": "searchable"},
        )
        self.entry.refresh_from_db()
        self.assertTrue(self.entry.is_searchable_override)

    def test_invalid_field_rejected(self):
        response = self.client.post(
            reverse("dashboard:category-schema-toggle-override", args=[self.category.pk, self.entry.pk]),
            {"field": "not-a-real-field"},
        )
        self.assertEqual(response.status_code, 200)
        self.entry.refresh_from_db()
        self.assertIsNone(self.entry.is_filterable_override)
        self.assertIsNone(self.entry.is_comparable_override)
        self.assertIsNone(self.entry.is_searchable_override)

    def test_visibility_toggle(self):
        self.assertTrue(self.entry.is_visible_on_storefront)
        self.client.post(
            reverse("dashboard:category-schema-toggle-visibility", args=[self.category.pk, self.entry.pk]),
        )
        self.entry.refresh_from_db()
        self.assertFalse(self.entry.is_visible_on_storefront)

    def test_override_entry_from_other_category_404s(self):
        other_category = Category.objects.create(store=self.store, name="کفش", slug="csv-override-other")
        entry = add_category_attribute(other_category, self.material)
        response = self.client.post(
            reverse("dashboard:category-schema-toggle-override", args=[self.category.pk, entry.pk]),
            {"field": "filterable"},
        )
        self.assertEqual(response.status_code, 404)
        entry.refresh_from_db()
        self.assertIsNone(entry.is_filterable_override)

    def test_analyst_cannot_toggle_override(self):
        user = User.objects.create_user(username="09121177304", password="pass12345", is_staff=True)
        StoreMembership.objects.create(
            store=self.store, user=user, role=StoreMembership.Role.ANALYST,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )
        self.client.logout()
        self.client.login(username=user.username, password="pass12345")
        response = self.client.post(
            reverse("dashboard:category-schema-toggle-override", args=[self.category.pk, self.entry.pk]),
            {"field": "filterable"},
        )
        self.assertEqual(response.status_code, 403)
