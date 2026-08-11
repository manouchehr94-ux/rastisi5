import json
from decimal import Decimal

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.catalog.models import Attribute, Category, Product, ProductAttributeValue, Vendor
from apps.catalog.services.attribute_service import create_attribute, create_attribute_value
from apps.catalog.services.category_schema_service import add_category_attribute
from apps.catalog.services.variant_engine_service import add_product_option, generate_variants
from apps.stores.models import Store, StoreMembership

User = get_user_model()

HOST = f"paf-test.{settings.RASTISI_ADMIN_DOMAIN_SUFFIX}"


def _akhlaghi():
    return Store.objects.get(slug="akhlaghi")


@override_settings(ALLOWED_HOSTS=[HOST, "testserver"])
class ProductAttributeFormTestCase(TestCase):
    def setUp(self):
        self.store = _akhlaghi()
        self.store.admin_subdomain = HOST.split(".")[0]
        self.store.save(update_fields=["admin_subdomain"])
        self.vendor = Vendor.objects.create(store=self.store, name="فروشگاه", slug="paf-shop")
        self.main = Category.objects.create(store=self.store, name="دیجیتال", slug="paf-main")
        self.category = Category.objects.create(store=self.store, name="پوشاک", slug="paf-cat", parent=self.main)
        self.other_category = Category.objects.create(
            store=self.store, name="کفش", slug="paf-cat2", parent=self.main,
        )
        self.material = create_attribute(self.store, label="جنس")
        add_category_attribute(self.category, self.material)
        self.staff = User.objects.create_user(username="09121166001", password="pass12345", is_staff=True)
        StoreMembership.objects.create(
            store=self.store, user=self.staff, role=StoreMembership.Role.OWNER,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )
        self.client = Client(HTTP_HOST=HOST)
        self.client.login(username="09121166001", password="pass12345")

    def _payload(self, **overrides):
        payload = {
            "name": "تی‌شرت جدید", "sku": "PAF-SKU1", "category": self.category.id,
            "price": "300000", "discount_percent": "0", "stock": "10",
            "status": "active", "icon": "🎁", "description": "",
        }
        payload.update(overrides)
        return payload


class ProductAttributeFieldsAjaxTests(ProductAttributeFormTestCase):
    def test_loads_fields_for_category(self):
        response = self.client.get(reverse("dashboard:product-attribute-fields"), {"category": self.category.pk})
        self.assertContains(response, "جنس")

    def test_no_category_returns_empty(self):
        response = self.client.get(reverse("dashboard:product-attribute-fields"))
        self.assertContains(response, "هیچ ویژگی توصیفی‌ای تعریف نشده است")

    def test_other_store_category_ignored(self):
        other_store = Store.objects.create(name="فروشگاه دیگر", slug="paf-other", status=Store.Status.ACTIVE)
        other_category = Category.objects.create(store=other_store, name="دسته دیگر", slug="paf-other-cat")
        response = self.client.get(reverse("dashboard:product-attribute-fields"), {"category": other_category.pk})
        self.assertContains(response, "هیچ ویژگی توصیفی‌ای تعریف نشده است")


class ProductCreateWithAttributesTests(ProductAttributeFormTestCase):
    def test_text_attribute_saved_on_create(self):
        response = self.client.post(reverse("dashboard:product-add"), self._payload(**{
            f"attr_{self.material.pk}": "نخی",
        }))
        self.assertEqual(response.status_code, 200)
        product = Product.objects.get(sku="PAF-SKU1")
        assignment = ProductAttributeValue.objects.get(product=product, attribute=self.material)
        self.assertEqual(assignment.text_value, "نخی")

    def test_number_attribute_saved(self):
        weight = create_attribute(self.store, label="وزن", data_type=Attribute.DataType.NUMBER)
        add_category_attribute(self.category, weight)
        response = self.client.post(reverse("dashboard:product-add"), self._payload(**{
            f"attr_{weight.pk}": "۲۵۰",
        }))
        self.assertEqual(response.status_code, 200)
        product = Product.objects.get(sku="PAF-SKU1")
        assignment = ProductAttributeValue.objects.get(product=product, attribute=weight)
        self.assertEqual(assignment.number_value, Decimal("250"))

    def test_boolean_attribute_saved(self):
        waterproof = create_attribute(self.store, label="ضدآب", data_type=Attribute.DataType.BOOLEAN)
        add_category_attribute(self.category, waterproof)
        self.client.post(reverse("dashboard:product-add"), self._payload(**{
            f"attr_{waterproof.pk}": "true",
        }))
        product = Product.objects.get(sku="PAF-SKU1")
        assignment = ProductAttributeValue.objects.get(product=product, attribute=waterproof)
        self.assertTrue(assignment.boolean_value)

    def test_select_attribute_saved(self):
        color = create_attribute(self.store, label="رنگ", data_type=Attribute.DataType.SELECT)
        green = create_attribute_value(color, label="سبز")
        add_category_attribute(self.category, color)
        self.client.post(reverse("dashboard:product-add"), self._payload(**{
            f"attr_{color.pk}": str(green.pk),
        }))
        product = Product.objects.get(sku="PAF-SKU1")
        assignment = ProductAttributeValue.objects.get(product=product, attribute=color)
        self.assertEqual(assignment.value_id, green.pk)

    def test_multiselect_attribute_saved(self):
        features = create_attribute(self.store, label="ویژگی‌ها", data_type=Attribute.DataType.MULTISELECT)
        waterproof = create_attribute_value(features, label="ضدآب")
        breathable = create_attribute_value(features, label="تنفس‌پذیر")
        add_category_attribute(self.category, features)
        payload = self._payload()
        payload[f"attr_{features.pk}"] = [str(waterproof.pk), str(breathable.pk)]
        response = self.client.post(reverse("dashboard:product-add"), payload)
        self.assertEqual(response.status_code, 200)
        product = Product.objects.get(sku="PAF-SKU1")
        assignments = ProductAttributeValue.objects.filter(product=product, attribute=features)
        self.assertEqual(assignments.count(), 2)

    def test_optional_attribute_may_be_left_blank(self):
        response = self.client.post(reverse("dashboard:product-add"), self._payload())
        self.assertEqual(response.status_code, 200)
        product = Product.objects.get(sku="PAF-SKU1")
        self.assertFalse(ProductAttributeValue.objects.filter(product=product).exists())

    def test_cross_attribute_value_id_ignored_for_select_field(self):
        color = create_attribute(self.store, label="رنگ", data_type=Attribute.DataType.SELECT)
        add_category_attribute(self.category, color)
        # a value belonging to a *different* Attribute (still same Store) must never be
        # accepted for "رنگ" — set_product_attribute_value's own value/attribute check applies.
        foreign_value = create_attribute_value(self.material, label="نخی")
        response = self.client.post(reverse("dashboard:product-add"), self._payload(**{
            f"attr_{color.pk}": str(foreign_value.pk),
        }))
        self.assertEqual(response.status_code, 200)
        product = Product.objects.get(sku="PAF-SKU1")
        self.assertFalse(ProductAttributeValue.objects.filter(product=product, attribute=color).exists())


class ProductPublishValidationTests(ProductAttributeFormTestCase):
    def setUp(self):
        super().setUp()
        entry = self.category.attribute_schema_entries.get(attribute=self.material)
        entry.is_required = True
        entry.save(update_fields=["is_required"])

    def test_publish_with_missing_required_attribute_rejected(self):
        response = self.client.post(reverse("dashboard:product-add"), self._payload(status="active"))
        self.assertContains(response, "جنس")
        self.assertFalse(Product.objects.filter(sku="PAF-SKU1").exists())

    def test_draft_with_missing_required_attribute_allowed(self):
        response = self.client.post(reverse("dashboard:product-add"), self._payload(status="draft"))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(Product.objects.filter(sku="PAF-SKU1").exists())

    def test_publish_with_required_attribute_filled_succeeds(self):
        response = self.client.post(reverse("dashboard:product-add"), self._payload(status="active", **{
            f"attr_{self.material.pk}": "نخی",
        }))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(Product.objects.filter(sku="PAF-SKU1").exists())

    def test_publish_variable_product_without_variant_allowed(self):
        # Deliberate: preserves the existing, tested simple->variable transition
        # workflow — see product_publish_service's own comment for the reasoning.
        response = self.client.post(reverse("dashboard:product-add"), self._payload(
            status="active", product_type="variable", **{f"attr_{self.material.pk}": "نخی"},
        ))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(Product.objects.filter(sku="PAF-SKU1").exists())


class CategoryChangeOrphanTests(ProductAttributeFormTestCase):
    def test_changing_category_does_not_delete_value(self):
        product = Product.objects.create(
            store=self.store, vendor=self.vendor, category=self.category, name="کالا",
            slug="paf-existing", sku="PAF-EXIST1", price=Decimal("100000"),
        )
        ProductAttributeValue.objects.create(product=product, attribute=self.material, text_value="نخی")

        payload = self._payload(sku="PAF-EXIST1", category=self.other_category.id)
        response = self.client.post(reverse("dashboard:product-edit", args=[product.pk]), payload)

        self.assertEqual(response.status_code, 200)
        product.refresh_from_db()
        self.assertEqual(product.category_id, self.other_category.pk)
        # value still exists — never silently deleted
        self.assertTrue(ProductAttributeValue.objects.filter(product=product, attribute=self.material).exists())
        # پیامِ موفقیت دیگر HX-Trigger نیست — از طریقِ django.contrib.messages
        # در همان رندرِ درجاجایِ صفحه‌ی تمام‌صفحه نمایش داده می‌شود.
        self.assertContains(response, "مطابقت ندارد")

    def test_cleanup_endpoint_deletes_orphans_explicitly(self):
        product = Product.objects.create(
            store=self.store, vendor=self.vendor, category=self.other_category, name="کالا",
            slug="paf-existing2", sku="PAF-EXIST2", price=Decimal("100000"),
        )
        ProductAttributeValue.objects.create(product=product, attribute=self.material, text_value="نخی")

        response = self.client.post(reverse("dashboard:product-attribute-cleanup", args=[product.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertFalse(ProductAttributeValue.objects.filter(product=product, attribute=self.material).exists())

    def test_edit_form_shows_existing_values(self):
        product = Product.objects.create(
            store=self.store, vendor=self.vendor, category=self.category, name="کالا",
            slug="paf-existing3", sku="PAF-EXIST3", price=Decimal("100000"),
        )
        ProductAttributeValue.objects.create(product=product, attribute=self.material, text_value="پلی‌استر")
        response = self.client.get(reverse("dashboard:product-edit", args=[product.pk]))
        self.assertContains(response, "پلی‌استر")


class ProductAttributeFormPermissionTests(ProductAttributeFormTestCase):
    def test_anonymous_cannot_load_attribute_fields(self):
        self.client.logout()
        response = self.client.get(reverse("dashboard:product-attribute-fields"), {"category": self.category.pk})
        self.assertEqual(response.status_code, 302)

    def test_non_member_cannot_save_attributes(self):
        other = User.objects.create_user(username="09121166099", password="pass12345", is_staff=False)
        self.client.logout()
        self.client.login(username=other.username, password="pass12345")
        response = self.client.post(reverse("dashboard:product-add"), self._payload())
        self.assertRedirects(response, reverse("catalog:home"), fetch_redirect_response=False)
        self.assertFalse(Product.objects.filter(sku="PAF-SKU1").exists())
