"""رگرسیونِ رفعِ باگِ «افزودنِ مقدارِ اولیه» که کلِ فرمِ کالا را ارسال می‌کرد
(به‌جایِ فقط مقدارِ همان ویژگی) — نگاه کنید به کامیتِ رفعِ این رگرسیون.

ریشه‌ی باگ: htmx به‌طور پیش‌فرض همه‌ی ورودی‌هایِ نزدیک‌ترین ``<form>`` را هم
ارسال می‌کند (فارغ از ``hx-include``)، چون این دکمه‌ها هنوز داخلِ
``#productSaveForm`` هستند. تا پیش از این رفع، ورودیِ «افزودنِ مقدارِ اولیه»
در هر کارتِ ویژگی نامِ مشترکِ ``label`` داشت؛ با وجودِ چند کارتِ ویژگی، مقدارِ
آخرینِ کارت (اغلب خالی) به‌جایِ مقدارِ واقعاً واردشده به Django می‌رسید و باعثِ
شکستِ اعتبارسنجی و نمایشِ toast عمومیِ فرم می‌شد."""

from decimal import Decimal

from django.test import override_settings
from django.urls import reverse

from apps.catalog.models import Category, Product, ProductOptionValue, Vendor
from apps.catalog.services.variant_engine_service import add_product_option
from apps.dashboard.tests.test_product_entry_ui_cleanup import HOST, ProductEntryUiCleanupTestCase
from apps.stores.models import Store


@override_settings(ALLOWED_HOSTS=[HOST, "testserver"])
class AttributeValueAddScopeTests(ProductEntryUiCleanupTestCase):
    def setUp(self):
        super().setUp()
        self.axis_length = add_product_option(self.product, label="طول")
        self.axis_height = add_product_option(self.product, label="ارتفاع")

    def _add_value_url(self, axis):
        return reverse("dashboard:product-option-value-add", args=[self.product.pk, axis.pk])

    def test_button_markup_is_type_button_and_scoped(self):
        response = self.client.get(reverse("dashboard:product-edit", args=[self.product.pk]))
        content = response.content.decode()
        self.assertIn(f'name="v_{self.axis_length.pk}"', content)
        self.assertIn(f'hx-params="v_{self.axis_length.pk}"', content)
        self.assertNotIn('name="label" placeholder="افزودن مقدار اولیه', content)

    def test_valid_value_created_and_chip_rendered(self):
        response = self.client.post(
            self._add_value_url(self.axis_length),
            {f"v_{self.axis_length.pk}": "160 سانتی‌متر"},
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            ProductOptionValue.objects.filter(option=self.axis_length, label="160 سانتی‌متر").exists()
        )
        self.assertContains(response, "160 سانتی‌متر")

    def test_does_not_leak_or_corrupt_other_axis_when_whole_product_form_is_posted(self):
        """شبیه‌سازیِ دقیقِ درخواستی که مرورگر واقعاً می‌فرستاد: htmx تمامِ
        ورودی‌هایِ فرمِ اصلیِ کالا + ورودیِ خالیِ کارتِ ویژگیِ دوم را هم اضافه
        می‌کرد. حتی اگر این فیلدها در بدنه حاضر باشند، مقدارِ محورِ اول باید
        درست ثبت شود و محصول دست‌نخورده بماند."""
        payload = {
            f"v_{self.axis_length.pk}": "160 سانتی‌متر",
            f"v_{self.axis_height.pk}": "",  # ورودیِ خالیِ کارتِ دیگر، دقیقاً مثلِ باگِ واقعی
            "name": "این نباید ذخیره شود",
            "sku": "SHOULD-NOT-SAVE",
            "price": "999999",
            "stock": "5",
            "current_tab": "",
        }
        response = self.client.post(self._add_value_url(self.axis_length), payload, HTTP_HX_REQUEST="true")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            ProductOptionValue.objects.filter(option=self.axis_length, label="160 سانتی‌متر").exists()
        )
        self.product.refresh_from_db()
        self.assertEqual(self.product.name, "کالای تست")
        self.assertEqual(self.product.sku, "UICLEAN-SKU1")
        self.assertNotEqual(self.product.stock, 5)

    def test_blank_value_rejected_inline_not_generic_toast(self):
        response = self.client.post(
            self._add_value_url(self.axis_length), {f"v_{self.axis_length.pk}": ""}, HTTP_HX_REQUEST="true",
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("HX-Trigger", response)
        self.assertContains(response, '<div class="pe-field-error">')
        self.assertNotContains(response, "لطفاً خطاهای فرم را برطرف کنید")
        self.assertFalse(ProductOptionValue.objects.filter(option=self.axis_length).exists())

    def test_duplicate_value_rejected_inline_with_clear_persian_message(self):
        self.client.post(
            self._add_value_url(self.axis_length), {f"v_{self.axis_length.pk}": "120 cm"}, HTTP_HX_REQUEST="true",
        )
        response = self.client.post(
            self._add_value_url(self.axis_length), {f"v_{self.axis_length.pk}": "120 cm"}, HTTP_HX_REQUEST="true",
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("HX-Trigger", response)
        self.assertContains(response, "این مقدار قبلاً برای این ویژگی ثبت شده است")
        self.assertNotContains(response, "لطفاً خطاهای فرم را برطرف کنید")
        self.assertEqual(
            ProductOptionValue.objects.filter(option=self.axis_length, label="120 cm").count(), 1,
        )

    def test_current_tab_and_other_axis_untouched_after_add(self):
        response = self.client.post(
            self._add_value_url(self.axis_length), {f"v_{self.axis_length.pk}": "160 سانتی‌متر"}, HTTP_HX_REQUEST="true",
        )
        content = response.content.decode()
        self.assertIn("نامِ ویژگی: طول", content)
        self.assertIn("نامِ ویژگی: ارتفاع", content)
        self.assertEqual(self.axis_height.values.count(), 0)

    def test_cross_store_option_id_is_rejected(self):
        other_store = Store.objects.create(
            name="فروشگاهِ دیگر", slug="othershop", status=Store.Status.ACTIVE,
            admin_subdomain="othershop", platform_code="OTHERSHOP1",
        )
        other_vendor = Vendor.objects.create(store=other_store, name="فروشنده۲", slug="othershop-vendor")
        other_main = Category.objects.create(store=other_store, name="گروه۲", slug="othershop-group")
        other_sub = Category.objects.create(store=other_store, name="زیرگروه۲", slug="othershop-sub", parent=other_main)
        other_product = Product.objects.create(
            store=other_store, vendor=other_vendor, category=other_sub, name="کالایِ فروشگاهِ دیگر",
            slug="othershop-product", sku="OTHER-SKU1", price=Decimal("50000"),
            product_type=Product.ProductType.VARIABLE,
        )
        other_axis = add_product_option(other_product, label="رنگ")

        response = self.client.post(
            reverse("dashboard:product-option-value-add", args=[self.product.pk, other_axis.pk]),
            {f"v_{other_axis.pk}": "قرمز"}, HTTP_HX_REQUEST="true",
        )
        self.assertEqual(response.status_code, 404)
        self.assertFalse(ProductOptionValue.objects.filter(option=other_axis, label="قرمز").exists())

    def test_deactivated_attribute_rejects_value_add_cleanly(self):
        from apps.catalog.services.variant_engine_service import deactivate_product_option

        deactivate_product_option(self.axis_length)
        response = self.client.post(
            self._add_value_url(self.axis_length), {f"v_{self.axis_length.pk}": "160 سانتی‌متر"}, HTTP_HX_REQUEST="true",
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            ProductOptionValue.objects.filter(option=self.axis_length, label="160 سانتی‌متر").exists()
        )


@override_settings(ALLOWED_HOSTS=[HOST, "testserver"])
class OtherActionButtonsAreNotFormSubmittersTests(ProductEntryUiCleanupTestCase):
    """اطمینان از اینکه دکمه‌هایِ دیگرِ بخشِ تنوع هم دکمه‌هایِ ارسالِ ناخواسته‌ی
    فرمِ اصلی نیستند و کدشان کلِ فرم را در درخواست‌شان نمی‌گنجانند."""

    def setUp(self):
        super().setUp()
        self.axis = add_product_option(self.product, label="طول")

    def test_all_variant_section_buttons_are_type_button(self):
        # پاسخِ خودِ ویجت (نه کلِ صفحه) را می‌گیریم تا قطعاً فقط دکمه‌های همین
        # بخش شمرده شوند، نه دکمه‌ی ارسالِ نهاییِ فرمِ کالا یا بخش‌های دیگر.
        response = self.client.post(
            reverse("dashboard:product-option-activate", args=[self.product.pk, self.axis.pk]),
            {}, HTTP_HX_REQUEST="true",
        )
        content = response.content.decode()
        button_count = content.count("<button")
        typed_button_count = content.count('<button type="button"')
        self.assertGreater(button_count, 5)
        self.assertEqual(button_count, typed_button_count, "همه‌ی دکمه‌های این بخش باید type=\"button\" صریح داشته باشند")

    def test_generate_combinations_button_has_no_form_leak_guard(self):
        response = self.client.get(reverse("dashboard:product-edit", args=[self.product.pk]))
        content = response.content.decode()
        self.assertIn('hx-params="none"', content)

    def test_deactivate_and_remove_do_not_touch_product_fields(self):
        from apps.catalog.services.variant_engine_service import add_option_value

        value = add_option_value(self.axis, "۱۶۰ سانتی‌متر")
        response = self.client.post(
            reverse("dashboard:product-option-value-remove", args=[self.product.pk, value.pk]),
            {"name": "دستکاری‌شده", "price": "1"}, HTTP_HX_REQUEST="true",
        )
        self.assertEqual(response.status_code, 200)
        self.product.refresh_from_db()
        self.assertEqual(self.product.name, "کالای تست")
