import json
from decimal import Decimal

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.catalog.models import Brand, Category, Product, Vendor
from apps.catalog.services.brand_service import create_brand
from apps.stores.models import Store, StoreMembership

User = get_user_model()

HOST = f"brand-test.{settings.RASTISI_ADMIN_DOMAIN_SUFFIX}"


def _akhlaghi():
    return Store.objects.get(slug="akhlaghi")


@override_settings(ALLOWED_HOSTS=[HOST, "testserver"])
class BrandViewsTestCase(TestCase):
    def setUp(self):
        self.store = _akhlaghi()
        self.store.admin_subdomain = HOST.split(".")[0]
        self.store.save(update_fields=["admin_subdomain"])
        self.category = Category.objects.create(store=self.store, name="دسته", slug="brand-cat")
        self.staff = User.objects.create_user(username="09121155001", password="pass12345", is_staff=True)
        StoreMembership.objects.create(
            store=self.store, user=self.staff, role=StoreMembership.Role.OWNER,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )
        self.client = Client(HTTP_HOST=HOST)
        self.client.login(username="09121155001", password="pass12345")


class BrandListViewTests(BrandViewsTestCase):
    def test_renders_list(self):
        create_brand(self.store, name="دیجی‌لوول")
        response = self.client.get(reverse("dashboard:brand-list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "دیجی‌لوول")

    def test_anonymous_denied(self):
        self.client.logout()
        response = self.client.get(reverse("dashboard:brand-list"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("admin_return=", response.url)

    def test_search_filters(self):
        create_brand(self.store, name="دیجی‌لوول")
        create_brand(self.store, name="سام")
        response = self.client.get(reverse("dashboard:brand-table"), {"q": "سام"})
        self.assertContains(response, "سام")
        self.assertNotContains(response, "دیجی‌لوول")


class BrandAddViewTests(BrandViewsTestCase):
    def test_get_returns_form(self):
        response = self.client.get(reverse("dashboard:brand-add"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "افزودن برند جدید")

    def test_post_creates_brand(self):
        response = self.client.post(reverse("dashboard:brand-add"), {
            "name": "دیجی‌لوول", "name_en": "DigiLool", "description": "برند نمونه",
        })
        self.assertEqual(response.status_code, 200)
        brand = Brand.objects.get(store=self.store, name="دیجی‌لوول")
        self.assertEqual(brand.name_en, "DigiLool")
        self.assertTrue(brand.is_active)
        self.assertTrue(brand.slug)
        trigger = json.loads(response.headers["HX-Trigger"])
        self.assertIn("modal-close", trigger)

    def test_blank_name_rejected(self):
        response = self.client.post(reverse("dashboard:brand-add"), {"name": ""})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Brand.objects.filter(store=self.store).exists())

    def test_website_and_country_saved(self):
        response = self.client.post(reverse("dashboard:brand-add"), {
            "name": "برند خارجی", "website": "https://example.com", "country": "آلمان",
        })
        self.assertEqual(response.status_code, 200)
        brand = Brand.objects.get(store=self.store, name="برند خارجی")
        self.assertEqual(brand.website, "https://example.com")
        self.assertEqual(brand.country, "آلمان")

    def test_invalid_website_rejected(self):
        response = self.client.post(reverse("dashboard:brand-add"), {
            "name": "برند نامعتبر", "website": "not-a-url",
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Brand.objects.filter(store=self.store, name="برند نامعتبر").exists())

    def test_new_brand_gets_next_sort_order(self):
        from apps.catalog.services.brand_service import create_brand
        create_brand(self.store, name="اول")
        self.client.post(reverse("dashboard:brand-add"), {"name": "دوم"})
        second = Brand.objects.get(store=self.store, name="دوم")
        self.assertEqual(second.sort_order, 1)

    def test_brand_is_optional_on_product(self):
        """Sanity guard for the UX requirement: a Product must never require a Brand."""
        vendor = Vendor.objects.create(store=self.store, name="فروشنده", slug="brand-vendor")
        product = Product.objects.create(
            store=self.store, vendor=vendor, category=self.category, name="کالا بی‌برند", slug="brand-product",
            sku="BRAND-SKU1", price=Decimal("100000"),
        )
        self.assertIsNone(product.brand)


class BrandEditViewTests(BrandViewsTestCase):
    def test_edit_updates_name(self):
        brand = create_brand(self.store, name="دیجی‌لوول")
        response = self.client.post(reverse("dashboard:brand-edit", args=[brand.pk]), {
            "name": "دیجی‌لوول پرو", "name_en": "", "description": "",
        })
        self.assertEqual(response.status_code, 200)
        brand.refresh_from_db()
        self.assertEqual(brand.name, "دیجی‌لوول پرو")

    def test_edit_without_new_logo_keeps_existing(self):
        brand = create_brand(self.store, name="دیجی‌لوول")
        self.client.post(reverse("dashboard:brand-edit", args=[brand.pk]), {
            "name": "دیجی‌لوول", "name_en": "", "description": "توضیح تازه",
        })
        brand.refresh_from_db()
        self.assertEqual(brand.description, "توضیح تازه")
        self.assertFalse(brand.logo)

    def test_other_store_brand_404s(self):
        other_store = Store.objects.create(name="فروشگاه دیگر", slug="brand-other", status=Store.Status.ACTIVE)
        other_brand = create_brand(other_store, name="برند دیگر")
        response = self.client.get(reverse("dashboard:brand-edit", args=[other_brand.pk]))
        self.assertEqual(response.status_code, 404)


class BrandArchiveActivateDeleteTests(BrandViewsTestCase):
    def test_archive_and_activate(self):
        brand = create_brand(self.store, name="دیجی‌لوول")
        self.client.post(reverse("dashboard:brand-archive", args=[brand.pk]))
        brand.refresh_from_db()
        self.assertFalse(brand.is_active)
        self.client.post(reverse("dashboard:brand-activate", args=[brand.pk]))
        brand.refresh_from_db()
        self.assertTrue(brand.is_active)

    def test_delete_unused_brand(self):
        brand = create_brand(self.store, name="دیجی‌لوول")
        self.client.post(reverse("dashboard:brand-delete", args=[brand.pk]))
        self.assertFalse(Brand.objects.filter(pk=brand.pk).exists())

    def test_delete_used_brand_kept(self):
        vendor = Vendor.objects.create(store=self.store, name="فروشنده", slug="brand-vendor2")
        brand = create_brand(self.store, name="دیجی‌لوول")
        Product.objects.create(
            store=self.store, vendor=vendor, category=self.category, brand=brand, name="کالا", slug="brand-product2",
            sku="BRAND-SKU2", price=Decimal("100000"),
        )
        response = self.client.post(reverse("dashboard:brand-delete", args=[brand.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(Brand.objects.filter(pk=brand.pk).exists())


class BrandPermissionTests(BrandViewsTestCase):
    def _login_as(self, role):
        user = User.objects.create_user(username=f"09121155{role.value[:3]}", password="pass12345", is_staff=True)
        StoreMembership.objects.create(
            store=self.store, user=user, role=role,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )
        self.client.logout()
        self.client.login(username=user.username, password="pass12345")
        return user

    def test_analyst_cannot_add_brand(self):
        self._login_as(StoreMembership.Role.ANALYST)
        response = self.client.post(reverse("dashboard:brand-add"), {"name": "برند تحلیلگر"})
        self.assertEqual(response.status_code, 403)
        self.assertFalse(Brand.objects.filter(store=self.store, name="برند تحلیلگر").exists())

    def test_catalog_manager_can_add_brand(self):
        self._login_as(StoreMembership.Role.CATALOG_MANAGER)
        response = self.client.post(reverse("dashboard:brand-add"), {"name": "برند کاتالوگ"})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(Brand.objects.filter(store=self.store, name="برند کاتالوگ").exists())


class BrandReorderTests(BrandViewsTestCase):
    def test_reorders_by_posted_id_sequence(self):
        from apps.catalog.services.brand_service import create_brand
        first = create_brand(self.store, name="اول")
        second = create_brand(self.store, name="دوم")
        third = create_brand(self.store, name="سوم")

        response = self.client.post(reverse("dashboard:brand-reorder"), {
            "brand_ids": [third.pk, first.pk, second.pk],
        })
        self.assertEqual(response.status_code, 200)
        third.refresh_from_db()
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertEqual(third.sort_order, 0)
        self.assertEqual(first.sort_order, 1)
        self.assertEqual(second.sort_order, 2)

    def test_ignores_ids_from_another_store(self):
        from apps.catalog.services.brand_service import create_brand
        other_store = Store.objects.create(name="فروشگاه دیگر", slug="brand-reorder-other", status=Store.Status.ACTIVE)
        other_brand = create_brand(other_store, name="برند دیگر")
        mine = create_brand(self.store, name="برند من")

        self.client.post(reverse("dashboard:brand-reorder"), {"brand_ids": [other_brand.pk, mine.pk]})
        other_brand.refresh_from_db()
        self.assertEqual(other_brand.sort_order, 0)  # unchanged, never touched

    def test_get_not_allowed(self):
        response = self.client.get(reverse("dashboard:brand-reorder"))
        self.assertEqual(response.status_code, 405)


class BrandBulkActionTests(BrandViewsTestCase):
    def test_bulk_activate(self):
        a = create_brand(self.store, name="اول")
        b = create_brand(self.store, name="دوم")
        from apps.catalog.services.brand_service import archive_brand
        archive_brand(a)
        archive_brand(b)
        response = self.client.post(reverse("dashboard:brand-bulk-action"), {
            "brand_ids": [a.pk, b.pk], "action": "activate",
        })
        self.assertEqual(response.status_code, 200)
        a.refresh_from_db(); b.refresh_from_db()
        self.assertTrue(a.is_active)
        self.assertTrue(b.is_active)

    def test_bulk_deactivate(self):
        a = create_brand(self.store, name="اول")
        b = create_brand(self.store, name="دوم")
        self.client.post(reverse("dashboard:brand-bulk-action"), {
            "brand_ids": [a.pk, b.pk], "action": "deactivate",
        })
        a.refresh_from_db(); b.refresh_from_db()
        self.assertFalse(a.is_active)
        self.assertFalse(b.is_active)

    def test_bulk_delete_skips_brand_in_use(self):
        vendor = Vendor.objects.create(store=self.store, name="فروشنده", slug="brand-bulk-vendor")
        unused = create_brand(self.store, name="بدون کالا")
        used = create_brand(self.store, name="دارایِ کالا")
        Product.objects.create(
            store=self.store, vendor=vendor, category=self.category, brand=used, name="کالا", slug="brand-bulk-product",
            sku="BRAND-BULK-SKU1", price=Decimal("100000"),
        )
        response = self.client.post(reverse("dashboard:brand-bulk-action"), {
            "brand_ids": [unused.pk, used.pk], "action": "delete",
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Brand.objects.filter(pk=unused.pk).exists())
        self.assertTrue(Brand.objects.filter(pk=used.pk).exists())

    def test_ignores_ids_from_another_store(self):
        other_store = Store.objects.create(name="فروشگاه دیگر", slug="brand-bulk-other", status=Store.Status.ACTIVE)
        other_brand = create_brand(other_store, name="برند دیگر")
        response = self.client.post(reverse("dashboard:brand-bulk-action"), {
            "brand_ids": [other_brand.pk], "action": "delete",
        })
        self.assertEqual(response.status_code, 200)
        self.assertTrue(Brand.objects.filter(pk=other_brand.pk).exists())

    def test_no_selection_shows_error_toast(self):
        response = self.client.post(reverse("dashboard:brand-bulk-action"), {"action": "activate"})
        trigger = json.loads(response.headers["HX-Trigger"])
        self.assertEqual(trigger["toast"]["type"], "err")

    def test_get_not_allowed(self):
        response = self.client.get(reverse("dashboard:brand-bulk-action"))
        self.assertEqual(response.status_code, 405)


class BrandProductCountLinkTests(BrandViewsTestCase):
    def test_product_count_links_to_filtered_product_list(self):
        vendor = Vendor.objects.create(store=self.store, name="فروشنده", slug="brand-count-vendor")
        brand = create_brand(self.store, name="برند")
        Product.objects.create(
            store=self.store, vendor=vendor, category=self.category, brand=brand, name="کالا", slug="brand-count-product",
            sku="BRAND-COUNT-SKU1", price=Decimal("100000"),
        )
        response = self.client.get(reverse("dashboard:brand-list"))
        expected_url = reverse("dashboard:product-list") + f"?brand={brand.pk}"
        self.assertContains(response, expected_url)

    def test_zero_count_is_not_a_link(self):
        create_brand(self.store, name="برندِ بدونِ کالا")
        response = self.client.get(reverse("dashboard:brand-list"))
        self.assertNotContains(response, "?brand=")
