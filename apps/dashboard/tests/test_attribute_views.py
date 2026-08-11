import json
from decimal import Decimal

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.catalog.models import Attribute, AttributeValue, Category, Product, ProductAttributeValue, Vendor
from apps.catalog.services.attribute_service import create_attribute, create_attribute_value, set_product_attribute_value
from apps.stores.models import Store, StoreMembership

User = get_user_model()

HOST = f"attr-test.{settings.RASTISI_ADMIN_DOMAIN_SUFFIX}"


def _akhlaghi():
    return Store.objects.get(slug="akhlaghi")


@override_settings(ALLOWED_HOSTS=[HOST, "testserver"])
class AttributeViewsTestCase(TestCase):
    def setUp(self):
        self.store = _akhlaghi()
        self.store.admin_subdomain = HOST.split(".")[0]
        self.store.save(update_fields=["admin_subdomain"])
        self.category = Category.objects.create(store=self.store, name="دسته", slug="attr-cat")
        self.staff = User.objects.create_user(username="09121144001", password="pass12345", is_staff=True)
        StoreMembership.objects.create(
            store=self.store, user=self.staff, role=StoreMembership.Role.OWNER,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )
        self.client = Client(HTTP_HOST=HOST)
        self.client.login(username="09121144001", password="pass12345")


class AttributeListViewTests(AttributeViewsTestCase):
    def test_renders_list(self):
        create_attribute(self.store, label="جنس")
        response = self.client.get(reverse("dashboard:attribute-list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "جنس")

    def test_anonymous_denied(self):
        self.client.logout()
        response = self.client.get(reverse("dashboard:attribute-list"))
        self.assertEqual(response.status_code, 302)
        self.assertNotIn("/admin-portal/login/", response.url)
        self.assertIn("admin_return=", response.url)
    def test_search_filters(self):
        create_attribute(self.store, label="جنس")
        create_attribute(self.store, label="رنگ")
        response = self.client.get(reverse("dashboard:attribute-table"), {"q": "رنگ"})
        self.assertContains(response, "رنگ")
        self.assertNotContains(response, "جنس")

    def test_status_filter(self):
        active = create_attribute(self.store, label="جنس")
        archived = create_attribute(self.store, label="گارانتی")
        archived.is_active = False
        archived.save(update_fields=["is_active"])
        response = self.client.get(reverse("dashboard:attribute-table"), {"status": "archived"})
        self.assertContains(response, "گارانتی")
        self.assertNotContains(response, "جنس")


class AttributeAddViewTests(AttributeViewsTestCase):
    def test_get_returns_form(self):
        response = self.client.get(reverse("dashboard:attribute-add"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "افزودن ویژگی جدید")

    def test_post_creates_attribute(self):
        response = self.client.post(reverse("dashboard:attribute-add"), {
            "label": "رنگ", "data_type": Attribute.DataType.SELECT, "display_type": "swatch",
            "is_variant_axis": "on",
        })
        self.assertEqual(response.status_code, 200)
        attribute = Attribute.objects.get(store=self.store, label="رنگ")
        self.assertTrue(attribute.is_variant_axis)
        trigger = json.loads(response.headers["HX-Trigger"])
        self.assertIn("modal-close", trigger)

    def test_is_image_driving_defaults_to_false(self):
        self.client.post(reverse("dashboard:attribute-add"), {
            "label": "جنس", "data_type": Attribute.DataType.TEXT, "is_variant_axis": "on",
        })
        attribute = Attribute.objects.get(store=self.store, label="جنس")
        self.assertFalse(attribute.is_image_driving)

    def test_post_creates_image_driving_attribute(self):
        self.client.post(reverse("dashboard:attribute-add"), {
            "label": "رنگ", "data_type": Attribute.DataType.SELECT, "display_type": "swatch",
            "is_variant_axis": "on", "is_image_driving": "on",
        })
        attribute = Attribute.objects.get(store=self.store, label="رنگ")
        self.assertTrue(attribute.is_image_driving)

    def test_blank_label_rejected(self):
        response = self.client.post(reverse("dashboard:attribute-add"), {
            "label": "", "data_type": Attribute.DataType.TEXT,
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Attribute.objects.filter(store=self.store).exists())

    def test_category_from_other_store_rejected(self):
        other_store = Store.objects.create(name="فروشگاه دیگر", slug="attr-other", status=Store.Status.ACTIVE)
        other_category = Category.objects.create(store=other_store, name="دسته دیگر", slug="attr-other-cat")
        response = self.client.post(reverse("dashboard:attribute-add"), {
            "label": "جنس", "data_type": Attribute.DataType.TEXT, "category": other_category.pk,
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Attribute.objects.filter(store=self.store, label="جنس").exists())


class AttributeEditViewTests(AttributeViewsTestCase):
    def test_edit_updates_label(self):
        attribute = create_attribute(self.store, label="جنس")
        response = self.client.post(reverse("dashboard:attribute-edit", args=[attribute.pk]), {
            "label": "جنس محصول", "data_type": Attribute.DataType.TEXT,
        })
        self.assertEqual(response.status_code, 200)
        attribute.refresh_from_db()
        self.assertEqual(attribute.label, "جنس محصول")

    def test_other_store_attribute_404s(self):
        other_store = Store.objects.create(name="فروشگاه دیگر", slug="attr-other2", status=Store.Status.ACTIVE)
        other_attribute = create_attribute(other_store, label="جنس دیگر")
        response = self.client.get(reverse("dashboard:attribute-edit", args=[other_attribute.pk]))
        self.assertEqual(response.status_code, 404)

    def test_edit_toggles_is_image_driving(self):
        attribute = create_attribute(self.store, label="رنگ", is_variant_axis=True)
        self.assertFalse(attribute.is_image_driving)
        self.client.post(reverse("dashboard:attribute-edit", args=[attribute.pk]), {
            "label": "رنگ", "data_type": Attribute.DataType.SELECT,
            "is_variant_axis": "on", "is_image_driving": "on",
        })
        attribute.refresh_from_db()
        self.assertTrue(attribute.is_image_driving)

    def test_get_prefills_is_image_driving(self):
        attribute = create_attribute(self.store, label="رنگ", is_variant_axis=True, is_image_driving=True)
        response = self.client.get(reverse("dashboard:attribute-edit", args=[attribute.pk]))
        self.assertContains(response, 'name="is_image_driving" checked')


class AttributeArchiveActivateDeleteTests(AttributeViewsTestCase):
    def test_archive_and_activate(self):
        attribute = create_attribute(self.store, label="جنس")
        self.client.post(reverse("dashboard:attribute-archive", args=[attribute.pk]))
        attribute.refresh_from_db()
        self.assertFalse(attribute.is_active)
        self.client.post(reverse("dashboard:attribute-activate", args=[attribute.pk]))
        attribute.refresh_from_db()
        self.assertTrue(attribute.is_active)

    def test_delete_unused_attribute(self):
        attribute = create_attribute(self.store, label="جنس")
        self.client.post(reverse("dashboard:attribute-delete", args=[attribute.pk]))
        self.assertFalse(Attribute.objects.filter(pk=attribute.pk).exists())

    def test_delete_used_attribute_kept(self):
        vendor = Vendor.objects.create(store=self.store, name="فروشنده", slug="attr-vendor")
        product = Product.objects.create(
            store=self.store, vendor=vendor, category=self.category, name="کالا", slug="attr-product",
            sku="ATTR-SKU1", price=Decimal("100000"),
        )
        attribute = create_attribute(self.store, label="گارانتی")
        set_product_attribute_value(product, attribute, text_value="۱۲ ماه")
        response = self.client.post(reverse("dashboard:attribute-delete", args=[attribute.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(Attribute.objects.filter(pk=attribute.pk).exists())


class AttributeValueViewTests(AttributeViewsTestCase):
    def test_add_value(self):
        attribute = create_attribute(self.store, label="رنگ", data_type=Attribute.DataType.SELECT)
        response = self.client.post(
            reverse("dashboard:attribute-value-add", args=[attribute.pk]), {"label": "سبز"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(AttributeValue.objects.filter(attribute=attribute, label="سبز").exists())

    def test_archive_value(self):
        attribute = create_attribute(self.store, label="رنگ", data_type=Attribute.DataType.SELECT)
        value = create_attribute_value(attribute, label="سبز")
        self.client.post(reverse("dashboard:attribute-value-archive", args=[attribute.pk, value.pk]))
        value.refresh_from_db()
        self.assertFalse(value.is_active)

    def test_delete_unused_value(self):
        attribute = create_attribute(self.store, label="رنگ", data_type=Attribute.DataType.SELECT)
        value = create_attribute_value(attribute, label="سبز")
        self.client.post(reverse("dashboard:attribute-value-delete", args=[attribute.pk, value.pk]))
        self.assertFalse(AttributeValue.objects.filter(pk=value.pk).exists())

    def test_value_from_other_store_attribute_404s(self):
        other_store = Store.objects.create(name="فروشگاه دیگر", slug="attr-other3", status=Store.Status.ACTIVE)
        other_attribute = create_attribute(other_store, label="رنگ دیگر", data_type=Attribute.DataType.SELECT)
        other_value = create_attribute_value(other_attribute, label="سبز")
        response = self.client.post(
            reverse("dashboard:attribute-value-archive", args=[other_attribute.pk, other_value.pk])
        )
        self.assertEqual(response.status_code, 404)

    def test_add_color_value_with_hex(self):
        attribute = create_attribute(self.store, label="رنگ", data_type=Attribute.DataType.COLOR)
        response = self.client.post(
            reverse("dashboard:attribute-value-add", args=[attribute.pk]),
            {"label": "قرمز", "color_hex": "#ff0000"},
        )
        self.assertEqual(response.status_code, 200)
        value = AttributeValue.objects.get(attribute=attribute, label="قرمز")
        self.assertEqual(value.color_hex, "#ff0000")

    def test_add_value_with_swatch_image(self):
        import io

        from django.core.files.uploadedfile import SimpleUploadedFile
        from PIL import Image

        attribute = create_attribute(self.store, label="جنس", data_type=Attribute.DataType.SELECT)
        buf = io.BytesIO()
        Image.new("RGB", (10, 10), color="brown").save(buf, format="PNG")
        image = SimpleUploadedFile("swatch.png", buf.getvalue(), content_type="image/png")
        response = self.client.post(
            reverse("dashboard:attribute-value-add", args=[attribute.pk]),
            {"label": "چرم", "swatch_image": image},
        )
        self.assertEqual(response.status_code, 200)
        value = AttributeValue.objects.get(attribute=attribute, label="چرم")
        self.assertTrue(value.swatch_image)


class AttributeValueReorderTests(AttributeViewsTestCase):
    def test_reorders_values_by_posted_sequence(self):
        attribute = create_attribute(self.store, label="سایز", data_type=Attribute.DataType.SELECT)
        small = create_attribute_value(attribute, label="کوچک")
        medium = create_attribute_value(attribute, label="متوسط")
        large = create_attribute_value(attribute, label="بزرگ")

        response = self.client.post(reverse("dashboard:attribute-value-reorder", args=[attribute.pk]), {
            "value_ids": [large.pk, small.pk, medium.pk],
        })
        self.assertEqual(response.status_code, 200)
        large.refresh_from_db()
        small.refresh_from_db()
        medium.refresh_from_db()
        self.assertEqual(large.display_order, 0)
        self.assertEqual(small.display_order, 1)
        self.assertEqual(medium.display_order, 2)

    def test_get_not_allowed(self):
        attribute = create_attribute(self.store, label="سایز")
        response = self.client.get(reverse("dashboard:attribute-value-reorder", args=[attribute.pk]))
        self.assertEqual(response.status_code, 405)


class AttributeSortTests(AttributeViewsTestCase):
    def test_sort_by_label_ascending(self):
        create_attribute(self.store, label="ویژگیِ ب")
        create_attribute(self.store, label="ویژگیِ آ")
        response = self.client.get(reverse("dashboard:attribute-table"), {"sort": "label"})
        content = response.content.decode()
        self.assertLess(content.index("ویژگیِ آ"), content.index("ویژگیِ ب"))


class AttributePermissionTests(AttributeViewsTestCase):
    def _login_as(self, role):
        user = User.objects.create_user(username=f"09121144{role.value[:3]}", password="pass12345", is_staff=True)
        StoreMembership.objects.create(
            store=self.store, user=user, role=role,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )
        self.client.logout()
        self.client.login(username=user.username, password="pass12345")
        return user

    def test_catalog_manager_can_manage_attributes(self):
        self._login_as(StoreMembership.Role.CATALOG_MANAGER)
        response = self.client.post(reverse("dashboard:attribute-add"), {
            "label": "رنگ", "data_type": Attribute.DataType.TEXT,
        })
        self.assertEqual(response.status_code, 200)
        self.assertTrue(Attribute.objects.filter(store=self.store, label="رنگ").exists())

    def test_analyst_cannot_manage_attributes(self):
        self._login_as(StoreMembership.Role.ANALYST)
        response = self.client.post(reverse("dashboard:attribute-add"), {
            "label": "رنگ", "data_type": Attribute.DataType.TEXT,
        })
        self.assertEqual(response.status_code, 403)
        self.assertFalse(Attribute.objects.filter(store=self.store, label="رنگ").exists())

    def test_order_manager_cannot_view_attributes(self):
        self._login_as(StoreMembership.Role.ORDER_MANAGER)
        response = self.client.get(reverse("dashboard:attribute-list"))
        self.assertEqual(response.status_code, 403)

    def test_content_editor_cannot_manage_attributes(self):
        self._login_as(StoreMembership.Role.CONTENT_EDITOR)
        response = self.client.get(reverse("dashboard:attribute-list"))
        self.assertEqual(response.status_code, 403)

    def test_inactive_membership_denied(self):
        user = User.objects.create_user(username="09121144777", password="pass12345", is_staff=True)
        StoreMembership.objects.create(
            store=self.store, user=user, role=StoreMembership.Role.OWNER,
            status=StoreMembership.MembershipStatus.REVOKED, revoked_at=timezone.now(),
        )
        self.client.logout()
        self.client.login(username="09121144777", password="pass12345")
        response = self.client.get(reverse("dashboard:attribute-list"))
        self.assertRedirects(response, reverse("catalog:home"), fetch_redirect_response=False)

    def test_staff_without_membership_denied(self):
        user = User.objects.create_user(username="09121144666", password="pass12345", is_staff=True)
        self.client.logout()
        self.client.login(username="09121144666", password="pass12345")
        response = self.client.get(reverse("dashboard:attribute-list"))
        self.assertRedirects(response, reverse("catalog:home"), fetch_redirect_response=False)

    def test_user_from_other_store_denied(self):
        other_store = Store.objects.create(name="فروشگاه دیگر", slug="attr-other4", status=Store.Status.ACTIVE)
        user = User.objects.create_user(username="09121144888", password="pass12345", is_staff=True)
        StoreMembership.objects.create(
            store=other_store, user=user, role=StoreMembership.Role.OWNER,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )
        self.client.logout()
        self.client.login(username="09121144888", password="pass12345")
        response = self.client.get(reverse("dashboard:attribute-list"))
        self.assertRedirects(response, reverse("catalog:home"), fetch_redirect_response=False)
