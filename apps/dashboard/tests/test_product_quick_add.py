"""تست‌های اکشن‌های سریعِ داخلِ فرمِ کالا — برند/دسته‌بندی/ویژگی، بدون ترکِ فرم."""
from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.catalog.models import Attribute, Brand, Category, CategoryAttributeSchema, Product, Vendor
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
    def test_creates_subcategory_under_existing_group_and_category(self):
        response = self.client.post(reverse("dashboard:product-quick-add-category"), {
            "group": self.main.pk, "new_group_name": "",
            "category": self.sub.pk, "new_category_name": "",
            "sub_name": "لپ‌تاپ",
        })
        self.assertEqual(response.status_code, 200)
        leaf = Category.objects.get(store=self.store, name="لپ‌تاپ")
        self.assertEqual(leaf.parent_id, self.sub.pk)
        self.assertContains(response, str(leaf.pk))

    def test_creates_group_category_and_subcategory_together_when_all_new(self):
        response = self.client.post(reverse("dashboard:product-quick-add-category"), {
            "group": "", "new_group_name": "پوشاک",
            "category": "", "new_category_name": "تیشرت",
            "sub_name": "تیشرت مردانه",
        })
        self.assertEqual(response.status_code, 200)
        group = Category.objects.get(store=self.store, name="پوشاک", parent__isnull=True)
        category = Category.objects.get(store=self.store, name="تیشرت")
        leaf = Category.objects.get(store=self.store, name="تیشرت مردانه")
        self.assertEqual(category.parent_id, group.pk)
        self.assertEqual(leaf.parent_id, category.pk)

    def test_creates_new_category_under_existing_group(self):
        response = self.client.post(reverse("dashboard:product-quick-add-category"), {
            "group": self.main.pk, "new_group_name": "",
            "category": "", "new_category_name": "پوشیدنی‌ها",
            "sub_name": "ساعت هوشمند",
        })
        self.assertEqual(response.status_code, 200)
        category = Category.objects.get(store=self.store, name="پوشیدنی‌ها")
        leaf = Category.objects.get(store=self.store, name="ساعت هوشمند")
        self.assertEqual(category.parent_id, self.main.pk)
        self.assertEqual(leaf.parent_id, category.pk)

    def test_neither_group_nor_new_name_rejected(self):
        response = self.client.post(reverse("dashboard:product-quick-add-category"), {
            "group": "", "new_group_name": "",
            "category": "", "new_category_name": "دسته",
            "sub_name": "تیشرت",
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Category.objects.filter(store=self.store, name="تیشرت").exists())

    def test_neither_category_nor_new_category_name_rejected(self):
        response = self.client.post(reverse("dashboard:product-quick-add-category"), {
            "group": self.main.pk, "new_group_name": "",
            "category": "", "new_category_name": "",
            "sub_name": "تیشرت",
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Category.objects.filter(store=self.store, name="تیشرت").exists())

    def test_refreshes_attribute_fields_out_of_band(self):
        response = self.client.post(reverse("dashboard:product-quick-add-category"), {
            "group": self.main.pk, "new_group_name": "",
            "category": self.sub.pk, "new_category_name": "",
            "sub_name": "کنسول بازی",
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


class QuickAddCategoryButtonPlacementTests(ProductQuickAddTestCase):
    """«+ افزودن گروه اصلی» و «+ افزودن زیرگروه» هر دو همان مودالِ سه‌مرحله‌ای
    را دوباره‌استفاده می‌کنند (نه یک فرم/اندپوینت جداگانه) — فقط نقطه‌ی
    ورودشان به مودال فرق دارد."""

    def test_both_buttons_render_and_reuse_the_existing_modal(self):
        response = self.client.get(reverse("dashboard:product-add"))
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertIn("+ افزودن گروه اصلی", html)
        self.assertIn("+ افزودن زیرگروه", html)
        self.assertIn("openQuickAddForSubcategory", html)
        # هیچ فرم/اندپوینتِ دومی برای دسته‌بندی معرفی نشده — همان مودالِ
        # سه‌مرحله‌ایِ موجود (qStep) توسطِ هر دو دکمه استفاده می‌شود.
        self.assertEqual(html.count('id="categoryField"'), 1)

    def test_add_main_group_button_starts_at_step_one(self):
        response = self.client.get(reverse("dashboard:product-add"))
        html = response.content.decode()
        pos = html.find("+ افزودن گروه اصلی")
        button_html = html[max(0, pos - 200):pos]
        self.assertIn('@click="openQuickAdd()"', button_html)

    def test_add_subcategory_button_falls_back_to_step_one_when_no_group_known(self):
        """وقتی هنوز هیچ دسته‌بندی‌ای برایِ کالا انتخاب نشده (کالایِ تازه)، گروهی
        برای پیش‌پرکردن شناخته‌شده نیست — ``openQuickAddForSubcategory`` باید
        صادقانه به مرحله‌ی ۱ برگردد، نه اینکه وانمود کند گروهی انتخاب شده.
        دیگر یک ثابتِ جاوااسکریپتیِ جداگانه (``prefillGroupId``) وجود ندارد —
        این منطق مستقیماً از رویِ ``selectedGroupId`` (مقدارِ اولیه‌ی خودِ
        سلکتِ «گروهِ اصلی») در همان متدِ ``openQuickAddForSubcategory``
        تصمیم می‌گیرد."""
        response = self.client.get(reverse("dashboard:product-add"))
        html = response.content.decode()
        self.assertIn("selectedGroupId: '',", html)
        self.assertIn("this.qStep = 1;", html)

    def test_add_subcategory_button_prefills_parent_group_for_existing_product(self):
        """وقتی کالا از قبل به یک زیرگروهِ نهایی وصل است، ``selectedGroupId``یِ
        اولیه باید گروهِ اصلیِ همان مسیر را (نه فقط دسته‌ی میانی) بشناسد —
        همان مقداری که ``openQuickAddForSubcategory`` برای پیش‌پرکردنِ
        مرحله‌ی ۲ استفاده می‌کند."""
        vendor = Vendor.objects.create(store=self.store, name="فروشنده", slug="pqa-vendor")
        product = Product.objects.create(
            store=self.store, vendor=vendor, category=self.sub, name="کالای تست",
            slug="pqa-product", sku="PQA-SKU1", price=100000,
        )
        response = self.client.get(reverse("dashboard:product-edit", args=[product.pk]))
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertIn(f"selectedGroupId: '{self.main.pk}',", html)


class ProductQuickAddPermissionTests(ProductQuickAddTestCase):
    def test_anonymous_denied(self):
        self.client.logout()
        response = self.client.post(reverse("dashboard:product-quick-add-brand"), {"quick_brand_name": "برند"})
        self.assertEqual(response.status_code, 302)

    def test_get_not_allowed(self):
        response = self.client.get(reverse("dashboard:product-quick-add-brand"))
        self.assertEqual(response.status_code, 405)
