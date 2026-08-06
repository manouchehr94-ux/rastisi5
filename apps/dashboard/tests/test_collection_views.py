from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.catalog.models import Category, MerchantCollection, MerchantCollectionItem, Product, Vendor
from apps.catalog.services import collection_service as svc
from apps.stores.authorization import ROLE_PERMISSIONS, COLLECTION_MANAGE
from apps.stores.models import Store, StoreMembership

User = get_user_model()

HOST = "coll-test.rastisi.localhost"


def _akhlaghi():
    return Store.objects.get(slug="akhlaghi")


def _product(store, slug):
    vendor = Vendor.objects.create(store=store, name=f"فروشنده {slug}", slug=f"v-{slug}")
    category = Category.objects.create(store=store, name=f"دسته {slug}", slug=f"c-{slug}")
    return Product.objects.create(
        store=store, vendor=vendor, category=category, name=f"کالای {slug}", slug=slug,
        sku=f"SKU-{slug}", price=Decimal("10000"),
    )


class CollectionViewsTestCase(TestCase):
    ROLE = StoreMembership.Role.OWNER

    def setUp(self):
        cache.clear()
        self.store = _akhlaghi()
        self.store.admin_subdomain = HOST.split(".")[0]
        self.store.save(update_fields=["admin_subdomain"])
        self.staff = User.objects.create_user(username="coll_owner", password="pass12345", is_staff=True)
        StoreMembership.objects.create(
            store=self.store, user=self.staff, role=self.ROLE,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )
        self.client = Client(HTTP_HOST=HOST)
        self.client.login(username="coll_owner", password="pass12345")


class CollectionCrudViewTests(CollectionViewsTestCase):
    def test_list_view_renders(self):
        resp = self.client.get(reverse("dashboard:collection-list"))
        self.assertEqual(resp.status_code, 200)

    def test_list_view_shows_empty_state(self):
        resp = self.client.get(reverse("dashboard:collection-list"))
        self.assertContains(resp, "هنوز هیچ کالکشنی")

    def test_create_collection(self):
        resp = self.client.post(reverse("dashboard:collection-add"), {"name": "وایر شمع"})
        self.assertEqual(resp.status_code, 302)
        collection = MerchantCollection.objects.get(store=self.store, name="وایر شمع")
        self.assertTrue(collection.slug)
        self.assertRedirects(resp, reverse("dashboard:collection-products", args=[collection.pk]))

    def test_create_rejects_blank_name(self):
        resp = self.client.post(reverse("dashboard:collection-add"), {"name": ""})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(MerchantCollection.objects.filter(store=self.store).count(), 0)

    def test_edit_collection(self):
        collection = svc.create_collection(self.store, name="نام اول")
        resp = self.client.post(reverse("dashboard:collection-edit", args=[collection.pk]), {
            "name": "نام دوم", "description": "توضیح تازه", "seo_title": "", "seo_description": "",
        })
        self.assertEqual(resp.status_code, 302)
        collection.refresh_from_db()
        self.assertEqual(collection.name, "نام دوم")
        self.assertEqual(collection.description, "توضیح تازه")

    def test_toggle_collection(self):
        collection = svc.create_collection(self.store, name="فعال‌سازی")
        self.client.post(reverse("dashboard:collection-toggle", args=[collection.pk]))
        collection.refresh_from_db()
        self.assertFalse(collection.is_active)
        self.client.post(reverse("dashboard:collection-toggle", args=[collection.pk]))
        collection.refresh_from_db()
        self.assertTrue(collection.is_active)

    def test_delete_collection(self):
        collection = svc.create_collection(self.store, name="حذف‌شونده")
        resp = self.client.post(reverse("dashboard:collection-delete", args=[collection.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(MerchantCollection.objects.filter(pk=collection.pk).exists())

    def test_cannot_edit_another_stores_collection(self):
        other_store = Store.objects.create(name="فروشگاه دیگر", slug="coll-cross", admin_subdomain="coll-cross")
        other_collection = svc.create_collection(other_store, name="فروشگاه دیگر")
        resp = self.client.get(reverse("dashboard:collection-edit", args=[other_collection.pk]))
        self.assertEqual(resp.status_code, 404)

    def test_cannot_delete_another_stores_collection(self):
        other_store = Store.objects.create(name="فروشگاه دیگر ۲", slug="coll-cross2", admin_subdomain="coll-cross2")
        other_collection = svc.create_collection(other_store, name="فروشگاه دیگر ۲")
        resp = self.client.post(reverse("dashboard:collection-delete", args=[other_collection.pk]))
        self.assertEqual(resp.status_code, 404)
        self.assertTrue(MerchantCollection.objects.filter(pk=other_collection.pk).exists())

    def test_search_filters_list(self):
        svc.create_collection(self.store, name="وایر شمع")
        svc.create_collection(self.store, name="روغن موتور")
        resp = self.client.get(reverse("dashboard:collection-table"), {"q": "شمع"})
        self.assertContains(resp, "وایر شمع")
        self.assertNotContains(resp, "روغن موتور")


class CollectionProductManagementViewTests(CollectionViewsTestCase):
    def setUp(self):
        super().setUp()
        self.collection = svc.create_collection(self.store, name="مدیریت کالا")

    def test_products_page_renders(self):
        resp = self.client.get(reverse("dashboard:collection-products", args=[self.collection.pk]))
        self.assertEqual(resp.status_code, 200)

    def test_search_products(self):
        product = _product(self.store, "search-target")
        resp = self.client.get(reverse("dashboard:collection-products-search", args=[self.collection.pk]), {"q": "search-target"})
        self.assertContains(resp, product.name)

    def test_search_excludes_other_store_products(self):
        other_store = Store.objects.create(name="فروشگاه جست‌وجو", slug="coll-search-cross", admin_subdomain="coll-search-cross")
        foreign = _product(other_store, "foreign-search")
        resp = self.client.get(reverse("dashboard:collection-products-search", args=[self.collection.pk]), {"q": "foreign-search"})
        self.assertNotContains(resp, foreign.name)

    def test_add_products(self):
        p1 = _product(self.store, "add-view-1")
        p2 = _product(self.store, "add-view-2")
        resp = self.client.post(reverse("dashboard:collection-products-add", args=[self.collection.pk]), {
            "product_ids": [p1.pk, p2.pk],
        })
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(self.collection.items.count(), 2)

    def test_cannot_add_duplicate_via_bulk_endpoint(self):
        product = _product(self.store, "add-view-dup")
        self.client.post(reverse("dashboard:collection-products-add", args=[self.collection.pk]), {"product_ids": [product.pk]})
        self.client.post(reverse("dashboard:collection-products-add", args=[self.collection.pk]), {"product_ids": [product.pk]})
        self.assertEqual(self.collection.items.filter(product=product).count(), 1)

    def test_cannot_add_cross_store_product(self):
        other_store = Store.objects.create(name="فروشگاه افزودن", slug="coll-add-cross", admin_subdomain="coll-add-cross")
        foreign = _product(other_store, "add-cross-target")
        resp = self.client.post(reverse("dashboard:collection-products-add", args=[self.collection.pk]), {
            "product_ids": [foreign.pk],
        })
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(self.collection.items.count(), 0)

    def test_remove_product(self):
        product = _product(self.store, "remove-view-1")
        item = svc.add_product(self.collection, product)
        resp = self.client.post(reverse("dashboard:collection-product-remove", args=[self.collection.pk, item.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(MerchantCollectionItem.objects.filter(pk=item.pk).exists())

    def test_reorder_persists(self):
        i1 = svc.add_product(self.collection, _product(self.store, "reorder-view-1"))
        i2 = svc.add_product(self.collection, _product(self.store, "reorder-view-2"))
        resp = self.client.post(reverse("dashboard:collection-products-reorder", args=[self.collection.pk]), {
            "item_ids": [i2.pk, i1.pk],
        })
        self.assertEqual(resp.status_code, 200)
        i1.refresh_from_db()
        i2.refresh_from_db()
        self.assertEqual(i2.order, 0)
        self.assertEqual(i1.order, 1)

    def test_move_up_down_fallback(self):
        i1 = svc.add_product(self.collection, _product(self.store, "move-view-1"))
        i2 = svc.add_product(self.collection, _product(self.store, "move-view-2"))
        self.client.post(reverse("dashboard:collection-product-move", args=[self.collection.pk, i2.pk]), {"direction": "up"})
        i1.refresh_from_db()
        i2.refresh_from_db()
        self.assertEqual(i2.order, 0)
        self.assertEqual(i1.order, 1)

    def test_products_page_cross_store_404(self):
        other_store = Store.objects.create(name="فروشگاه محصولات", slug="coll-products-cross", admin_subdomain="coll-products-cross")
        other_collection = svc.create_collection(other_store, name="فروشگاه دیگر")
        resp = self.client.get(reverse("dashboard:collection-products", args=[other_collection.pk]))
        self.assertEqual(resp.status_code, 404)


class CollectionPermissionTests(TestCase):
    def setUp(self):
        cache.clear()
        self.store = _akhlaghi()
        self.store.admin_subdomain = HOST.split(".")[0]
        self.store.save(update_fields=["admin_subdomain"])

    def _client_for_role(self, role, username):
        user = User.objects.create_user(username=username, password="pass12345", is_staff=True)
        StoreMembership.objects.create(
            store=self.store, user=user, role=role,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )
        client = Client(HTTP_HOST=HOST)
        client.login(username=username, password="pass12345")
        return client

    def test_owner_allowed(self):
        client = self._client_for_role(StoreMembership.Role.OWNER, "coll_perm_owner")
        resp = client.get(reverse("dashboard:collection-list"))
        self.assertEqual(resp.status_code, 200)

    def test_administrator_allowed(self):
        client = self._client_for_role(StoreMembership.Role.ADMINISTRATOR, "coll_perm_admin")
        resp = client.get(reverse("dashboard:collection-list"))
        self.assertEqual(resp.status_code, 200)

    def test_content_editor_allowed(self):
        client = self._client_for_role(StoreMembership.Role.CONTENT_EDITOR, "coll_perm_content")
        resp = client.get(reverse("dashboard:collection-list"))
        self.assertEqual(resp.status_code, 200)

    def test_catalog_manager_denied(self):
        self.assertNotIn(COLLECTION_MANAGE, ROLE_PERMISSIONS[StoreMembership.Role.CATALOG_MANAGER])
        client = self._client_for_role(StoreMembership.Role.CATALOG_MANAGER, "coll_perm_catalog")
        resp = client.get(reverse("dashboard:collection-list"))
        self.assertEqual(resp.status_code, 403)

    def test_analyst_denied(self):
        client = self._client_for_role(StoreMembership.Role.ANALYST, "coll_perm_analyst")
        resp = client.get(reverse("dashboard:collection-list"))
        self.assertEqual(resp.status_code, 403)

    def test_order_manager_denied(self):
        client = self._client_for_role(StoreMembership.Role.ORDER_MANAGER, "coll_perm_order")
        resp = client.get(reverse("dashboard:collection-list"))
        self.assertEqual(resp.status_code, 403)

    def test_anonymous_denied(self):
        client = Client(HTTP_HOST=HOST)
        resp = client.get(reverse("dashboard:collection-list"))
        self.assertEqual(resp.status_code, 302)
        self.assertIn("admin_return=", resp.url)

    def test_missing_membership_denied(self):
        user = User.objects.create_user(username="coll_no_membership", password="pass12345", is_staff=True)
        client = Client(HTTP_HOST=HOST)
        client.login(username="coll_no_membership", password="pass12345")
        resp = client.get(reverse("dashboard:collection-list"))
        self.assertEqual(resp.status_code, 302)

    def test_cross_store_membership_denied(self):
        other_store = Store.objects.create(name="فروشگاه بی‌ربط", slug="coll-perm-cross", admin_subdomain="coll-perm-cross-admin")
        user = User.objects.create_user(username="coll_cross_member", password="pass12345", is_staff=True)
        StoreMembership.objects.create(
            store=other_store, user=user, role=StoreMembership.Role.OWNER,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )
        client = Client(HTTP_HOST=HOST)
        client.login(username="coll_cross_member", password="pass12345")
        resp = client.get(reverse("dashboard:collection-list"))
        self.assertEqual(resp.status_code, 302)
