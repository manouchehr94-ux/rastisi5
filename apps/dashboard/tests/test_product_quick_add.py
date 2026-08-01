"""تست‌های اکشن‌های سریعِ داخلِ فرمِ کالا — برند/دسته‌بندی/ویژگی، بدون ترکِ فرم."""
from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.catalog.models import Attribute, Brand, Category, CategoryAttributeSchema
from apps.stores.models import Store, StoreMembership

User = get_user_model()

HOST = "pqa-test.rastisi.ir"


def _akhlaghi():
    return Store.objects.get(slug="akhlaghi")


@override_settings(ALLOWED_HOSTS=[HOST, "testserver"])
class ProductQuickAddTestCase(TestCase):
    def setUp(self):
        self.store = _akhlaghi()
        self.store.admin_subdomain = HOST.split(".")[0]
        self.store.save(update_fields=["admin_subdomain"])
        self.main = Category.objects.create(store=self.store, name="دیجیتال", slug="pqa-main")
        self.sub = Category.objects.create(store=self.store, name="موبایل", slug="pqa-sub", parent=self.main)
        self.staff = User.objects.create_user(username="09121177001", password="pass12345", is_staff=True)
        StoreMembership.objects.create(
            store=self.store, user=self.staff, role=StoreMembership.Role.OWNER,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )
        self.client = Client(HTTP_HOST=HOST)
        self.client.login(username="09121177001", password="pass12345")


class QuickAddBrandTests(ProductQuickAddTestCase):
    def test_creates_and_selects_new_brand(self):
        response = self.client.post(reverse("dashboard:product-quick-add-brand"), {
            "quick_brand_name": "دیجی‌لوول",
        })
        self.assertEqual(response.status_code, 200)
        brand = Brand.objects.get(store=self.store, name="دیجی‌لوول")
        self.assertContains(response, f'value="{brand.pk}" selected')

    def test_blank_name_shows_error_without_creating(self):
        response = self.client.post(reverse("dashboard:product-quick-add-brand"), {"quick_brand_name": ""})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Brand.objects.filter(store=self.store).exists())
        self.assertIn("quickOpen: true", response.content.decode())

    def test_does_not_collide_with_product_name_field(self):
        """The panel's own input is ``quick_brand_name``, not ``name`` — must
        never be confused with the outer product form's own name field."""
        response = self.client.post(reverse("dashboard:product-quick-add-brand"), {
            "quick_brand_name": "برند تست", "name": "کالای دیگر",
        })
        self.assertEqual(response.status_code, 200)
        self.assertTrue(Brand.objects.filter(store=self.store, name="برند تست").exists())
        self.assertFalse(Brand.objects.filter(store=self.store, name="کالای دیگر").exists())


class QuickAddCategoryTests(ProductQuickAddTestCase):
    def test_creates_subcategory_under_existing_group(self):
        response = self.client.post(reverse("dashboard:product-quick-add-category"), {
            "group": self.main.pk, "new_group_name": "", "sub_name": "لپ‌تاپ",
        })
        self.assertEqual(response.status_code, 200)
        sub = Category.objects.get(store=self.store, name="لپ‌تاپ")
        self.assertEqual(sub.parent_id, self.main.pk)
        self.assertContains(response, f'value="{sub.pk}" selected')

    def test_creates_group_and_subcategory_together_when_none_selected(self):
        response = self.client.post(reverse("dashboard:product-quick-add-category"), {
            "group": "", "new_group_name": "پوشاک", "sub_name": "تیشرت",
        })
        self.assertEqual(response.status_code, 200)
        group = Category.objects.get(store=self.store, name="پوشاک", parent__isnull=True)
        sub = Category.objects.get(store=self.store, name="تیشرت")
        self.assertEqual(sub.parent_id, group.pk)

    def test_neither_group_nor_new_name_rejected(self):
        response = self.client.post(reverse("dashboard:product-quick-add-category"), {
            "group": "", "new_group_name": "", "sub_name": "تیشرت",
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Category.objects.filter(store=self.store, name="تیشرت").exists())

    def test_refreshes_attribute_fields_out_of_band(self):
        response = self.client.post(reverse("dashboard:product-quick-add-category"), {
            "group": self.main.pk, "new_group_name": "", "sub_name": "کنسول بازی",
        })
        self.assertContains(response, 'id="productAttributeFields"')
        self.assertContains(response, 'hx-swap-oob="true"')


class QuickAddAttributeTests(ProductQuickAddTestCase):
    def test_creates_attribute_and_attaches_to_category_schema(self):
        response = self.client.post(reverse("dashboard:product-quick-add-attribute"), {
            "label": "جنس", "category": self.sub.pk,
        })
        self.assertEqual(response.status_code, 200)
        attribute = Attribute.objects.get(store=self.store, label="جنس")
        self.assertTrue(CategoryAttributeSchema.objects.filter(category=self.sub, attribute=attribute).exists())
        self.assertContains(response, "جنس")

    def test_requires_a_category_first(self):
        response = self.client.post(reverse("dashboard:product-quick-add-attribute"), {
            "label": "جنس", "category": "",
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Attribute.objects.filter(store=self.store, label="جنس").exists())
        self.assertContains(response, "اول یک دسته‌بندی")

    def test_duplicate_attribute_in_schema_reports_error(self):
        first = self.client.post(reverse("dashboard:product-quick-add-attribute"), {
            "label": "رنگ", "category": self.sub.pk,
        })
        self.assertEqual(first.status_code, 200)
        attribute = Attribute.objects.get(store=self.store, label="رنگ")
        second = self.client.post(reverse("dashboard:product-quick-add-attribute"), {
            "label": "رنگ", "category": self.sub.pk,
        })
        self.assertEqual(second.status_code, 200)
        # دومین ویژگیِ هم‌نام یک رکوردِ Attribute جداگانه می‌سازد (کدِ داخلی
        # متفاوت)، اما نباید بتواند دوباره به همان دسته‌بندی وصل شود.
        self.assertEqual(
            CategoryAttributeSchema.objects.filter(category=self.sub, attribute__label="رنگ").count(), 1,
        )


class ProductQuickAddPermissionTests(ProductQuickAddTestCase):
    def test_anonymous_denied(self):
        self.client.logout()
        response = self.client.post(reverse("dashboard:product-quick-add-brand"), {"quick_brand_name": "برند"})
        self.assertEqual(response.status_code, 302)

    def test_get_not_allowed(self):
        response = self.client.get(reverse("dashboard:product-quick-add-brand"))
        self.assertEqual(response.status_code, 405)
