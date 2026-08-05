"""تست‌های تمیزکاریِ رابطِ کاربریِ صفحه‌ی افزودن/ویرایشِ کالا — نگاه کنید به
گزارشِ تحویلِ همین تسک: حذفِ راهنمایِ بالایِ صفحه، رفعِ تکرارِ لیبلِ برند، فونتِ
یکدست، و سادّه‌سازیِ UXِ افزودنِ ویژگی/مقدار (بدونِ تغییرِ موتورِ واقعیِ تنوع)."""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.catalog.models import Category, Product, ProductOption, ProductOptionValue, Vendor
from apps.catalog.services.attribute_service import create_attribute, create_attribute_value
from apps.catalog.services.variant_engine_service import add_option_value, add_product_option
from apps.stores.models import Store, StoreMembership

User = get_user_model()
HOST = "uicleanup.rastisi.localhost"


@override_settings(ALLOWED_HOSTS=[HOST, "testserver"])
class ProductEntryUiCleanupTestCase(TestCase):
    def setUp(self):
        self.store = Store.objects.create(
            name="فروشگاه تست", slug="uicleanup", status=Store.Status.ACTIVE,
            admin_subdomain="uicleanup", platform_code="UICLEAN1",
        )
        self.vendor = Vendor.objects.create(store=self.store, name="فروشنده", slug="uicleanup-shop")
        self.main = Category.objects.create(store=self.store, name="گروه", slug="uicleanup-group")
        self.sub = Category.objects.create(store=self.store, name="زیرگروه", slug="uicleanup-sub", parent=self.main)
        self.product = Product.objects.create(
            store=self.store, vendor=self.vendor, category=self.sub, name="کالای تست",
            slug="uicleanup-product", sku="UICLEAN-SKU1", price=Decimal("100000"),
            product_type=Product.ProductType.VARIABLE,
        )
        self.staff = User.objects.create_user(username="uicleanup-staff", password="pass12345", is_staff=True)
        StoreMembership.objects.create(
            store=self.store, user=self.staff, role=StoreMembership.Role.OWNER,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )
        self.client = Client(HTTP_HOST=HOST)
        self.client.login(username="uicleanup-staff", password="pass12345")


class TopLegendAndBrandLabelTests(ProductEntryUiCleanupTestCase):
    def test_required_optional_legend_is_absent(self):
        response = self.client.get(reverse("dashboard:product-edit", args=[self.product.pk]))
        self.assertNotContains(response, "فیلدِ ضروری")
        self.assertNotContains(response, "می‌توانید بعداً هم تکمیل کنید")

    def test_brand_label_appears_exactly_once(self):
        response = self.client.get(reverse("dashboard:product-edit", args=[self.product.pk]))
        content = response.content.decode()
        self.assertEqual(content.count(">برند "), 1)

    def test_brand_optional_pill_appears_exactly_once(self):
        response = self.client.get(reverse("dashboard:product-edit", args=[self.product.pk]))
        content = response.content.decode()
        tab_start = content.index('x-ref="tabBasic"')
        tab_end = content.index('x-ref="tabCategory"')
        tab_html = content[tab_start:tab_end]
        self.assertEqual(tab_html.count('برند <span class="opt-pill">اختیاری</span>'), 1)

    def test_brand_field_still_has_select_and_quick_add_button(self):
        response = self.client.get(reverse("dashboard:product-edit", args=[self.product.pk]))
        content = response.content.decode()
        self.assertIn('id="id_brand"', content)
        self.assertIn("+ افزودن برند", content)

    def test_brand_field_is_not_double_wrapped(self):
        """رگرسیون: قبلاً ``product_form.html`` یک ``<div class="field">`` و
        لیبلِ خودش را دورِ ``product_brand_select.html`` (که خودش هم یک
        ``#brandField.field`` کاملِ مستقل با لیبلِ خودش است) می‌گذاشت — یعنی
        دو ``.field`` تودرتو و دو لیبلِ «برند». اکنون include باید مستقیماً
        همان ``#brandField`` را به‌عنوانِ تنها wrapper رندر کند."""
        response = self.client.get(reverse("dashboard:product-edit", args=[self.product.pk]))
        content = response.content.decode()
        brand_field_start = content.index('id="brandField"')
        # جستجوی نزدیک‌ترین ``<div class="field">`` باز پیش از #brandField در
        # همان ناحیه — نباید در فاصله‌ی کوتاهی (همان بستهٔ اطراف) وجود داشته باشد.
        preceding = content[max(0, brand_field_start - 120):brand_field_start]
        self.assertNotIn('<div class="field">\n            <label>برند', preceding)


class ConsistentFontTests(ProductEntryUiCleanupTestCase):
    def test_product_entry_stylesheet_uses_vazirmatn_not_tahoma(self):
        with open("apps/dashboard/static/css/product_entry_prototype.css", encoding="utf-8") as fh:
            css = fh.read()
        self.assertIn("font-family:'Vazirmatn'", css)
        self.assertNotIn("font-family:Tahoma,Arial,sans-serif", css)

    def test_admin_dashboard_font_face_is_locally_served(self):
        with open("apps/dashboard/static/css/admin.css", encoding="utf-8") as fh:
            css = fh.read()
        self.assertIn("@font-face", css)
        self.assertIn("Vazirmatn-Variable.woff2", css)
        self.assertNotIn("fonts.googleapis.com", css)
        self.assertNotIn("fonts.gstatic.com", css)

    def test_font_file_exists_locally_in_repo(self):
        import os

        self.assertTrue(os.path.exists("apps/core/static/fonts/Vazirmatn-Variable.woff2"))


class AttributeEntryUxTests(ProductEntryUiCleanupTestCase):
    def test_no_add_color_value_feature_anywhere_in_product_entry(self):
        response = self.client.get(reverse("dashboard:product-edit", args=[self.product.pk]))
        self.assertNotContains(response, "افزودن مقدار رنگ")
        self.assertNotContains(response, "افزودنِ مقدارِ رنگ")

    def test_no_color_picker_input_in_add_attribute_form(self):
        response = self.client.get(reverse("dashboard:product-edit", args=[self.product.pk]))
        content = response.content.decode()
        modal_start = content.index("افزودن ویژگی جدید")
        modal_end = content.index("</template>", modal_start)
        modal_html = content[modal_start:modal_end]
        self.assertNotIn('type="color"', modal_html)
        self.assertNotIn("colorValues", modal_html)
        self.assertNotIn("raw_values", modal_html)
        self.assertNotIn("<textarea", modal_html)

    def test_add_attribute_modal_contains_only_name_field_and_actions(self):
        response = self.client.get(reverse("dashboard:product-edit", args=[self.product.pk]))
        content = response.content.decode()
        modal_start = content.index("افزودن ویژگی جدید")
        modal_end = content.index("</template>", modal_start)
        modal_html = content[modal_start:modal_end]
        self.assertIn('name="label"', modal_html)
        self.assertIn("انصراف", modal_html)
        self.assertIn("افزودن ویژگی", modal_html)
        self.assertEqual(modal_html.count("<input"), 1)

    def test_no_add_value_color_input_per_attribute_card(self):
        create_attribute(self.store, label="طول", is_variant_axis=True)
        self.client.post(reverse("dashboard:product-option-add", args=[self.product.pk]), {"label": "طول"})
        response = self.client.get(reverse("dashboard:product-edit", args=[self.product.pk]))
        content = response.content.decode()
        attrs_start = content.index('id="attrs"')
        attrs_end = content.index("attribute-footer")
        attrs_html = content[attrs_start:attrs_end]
        self.assertNotIn('type="color"', attrs_html)

    def test_attribute_creation_via_new_simplified_endpoint_call(self):
        response = self.client.post(
            reverse("dashboard:product-option-add", args=[self.product.pk]), {"label": "طول"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(ProductOption.objects.filter(product=self.product, label="طول").exists())

    def test_new_attribute_appears_immediately_as_a_card(self):
        response = self.client.post(
            reverse("dashboard:product-option-add", args=[self.product.pk]), {"label": "ارتفاع"},
        )
        self.assertContains(response, "نامِ ویژگی: ارتفاع")

    def test_add_value_works(self):
        option = add_product_option(self.product, label="طول")
        response = self.client.post(
            reverse("dashboard:product-option-value-add", args=[self.product.pk, option.pk]),
            {"label": "100 cm"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(ProductOptionValue.objects.filter(option=option, label="100 cm").exists())
        self.assertContains(response, "100 cm")

    def test_duplicate_value_is_rejected(self):
        option = add_product_option(self.product, label="طول")
        add_option_value(option, "100 cm")
        self.client.post(
            reverse("dashboard:product-option-value-add", args=[self.product.pk, option.pk]),
            {"label": "100 cm"},
        )
        self.assertEqual(ProductOptionValue.objects.filter(option=option, label="100 cm").count(), 1)

    def test_blank_value_is_rejected(self):
        option = add_product_option(self.product, label="طول")
        self.client.post(
            reverse("dashboard:product-option-value-add", args=[self.product.pk, option.pk]),
            {"label": "   "},
        )
        self.assertEqual(ProductOptionValue.objects.filter(option=option).count(), 0)

    def test_value_chip_shows_remove_action(self):
        option = add_product_option(self.product, label="طول")
        value = add_option_value(option, "100 cm")
        response = self.client.get(reverse("dashboard:product-edit", args=[self.product.pk]))
        self.assertContains(
            response,
            reverse("dashboard:product-option-value-remove", args=[self.product.pk, value.pk]),
        )

    def test_remove_value_works(self):
        """مقداری که هنوز در هیچ تنوعی استفاده نشده، با حذف واقعاً از بین
        می‌رود (نه فقط غیرفعال) — طبق ADR-21 در ``remove_option_value``."""
        option = add_product_option(self.product, label="طول")
        value = add_option_value(option, "100 cm")
        response = self.client.post(
            reverse("dashboard:product-option-value-remove", args=[self.product.pk, value.pk]),
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(ProductOptionValue.objects.filter(pk=value.pk).exists())

    def test_values_persist_after_refresh(self):
        option = add_product_option(self.product, label="طول")
        add_option_value(option, "100 cm")
        response = self.client.get(reverse("dashboard:product-edit", args=[self.product.pk]))
        self.assertContains(response, "100 cm")


class AttributeLibraryStillWorksTests(ProductEntryUiCleanupTestCase):
    def test_library_attribute_renders_as_the_same_standard_card(self):
        attribute = create_attribute(self.store, label="جنس", is_variant_axis=True)
        create_attribute_value(attribute, label="استیل")
        create_attribute_value(attribute, label="آلومینیوم")
        response = self.client.post(
            reverse("dashboard:product-option-add-from-library", args=[self.product.pk, attribute.pk]),
        )
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn("نامِ ویژگی: جنس", content)
        self.assertIn("استیل", content)
        self.assertIn("آلومینیوم", content)

    def test_library_picker_is_present_but_secondary(self):
        create_attribute(self.store, label="جنس", is_variant_axis=True)
        response = self.client.get(reverse("dashboard:product-edit", args=[self.product.pk]))
        self.assertContains(response, "انتخاب از کتابخانه‌ی ویژگی‌ها")

    def test_selected_library_attribute_values_are_store_scoped(self):
        other_store = Store.objects.create(name="فروشگاه دیگر", slug="uicleanup-other", admin_subdomain="uicleanup-other")
        other_attribute = create_attribute(other_store, label="جنس دیگر", is_variant_axis=True)
        response = self.client.post(
            reverse("dashboard:product-option-add-from-library", args=[self.product.pk, other_attribute.pk]),
        )
        self.assertEqual(response.status_code, 404)


class MobileNoOverflowStyleTests(ProductEntryUiCleanupTestCase):
    """بررسیِ سطحِ CSS برایِ عدمِ اسکرولِ افقی در ۳۹۰px — تأییدِ Playwright واقعی
    در بخشِ جداگانه‌ی بررسیِ مرورگر انجام می‌شود."""

    def test_add_value_row_stacks_on_mobile(self):
        with open("apps/dashboard/static/css/product_entry_prototype.css", encoding="utf-8") as fh:
            css = fh.read()
        self.assertIn(".pe-prototype .add-value{grid-template-columns:1fr}", css)
