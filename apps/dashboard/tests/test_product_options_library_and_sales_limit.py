from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.catalog.models import Category, Product, Vendor
from apps.catalog.services.attribute_service import create_attribute, create_attribute_value
from apps.catalog.services.variant_engine_service import add_product_option, add_option_value, generate_variants
from apps.stores.models import Store, StoreMembership

User = get_user_model()
HOST = "optlib.rastisi.localhost"


@override_settings(ALLOWED_HOSTS=[HOST, "testserver"])
class ProductOptionsLibraryAndSalesLimitTests(TestCase):
    def setUp(self):
        self.store = Store.objects.create(
            name="فروشگاه تست", slug="optlib", status=Store.Status.ACTIVE,
            admin_subdomain="optlib", platform_code="OPTLIB01",
        )
        self.vendor = Vendor.objects.create(store=self.store, name="فروشنده", slug="optlib-shop")
        self.category_group = Category.objects.create(store=self.store, name="گروه", slug="optlib-group")
        self.category = Category.objects.create(
            store=self.store, name="دسته", slug="optlib-cat", parent=self.category_group,
        )
        self.product = Product.objects.create(
            store=self.store, vendor=self.vendor, category=self.category, name="قیچی",
            slug="optlib-scissors", sku="OPTLIB-SKU1", price=Decimal("100000"),
            product_type=Product.ProductType.VARIABLE,
        )
        self.staff = User.objects.create_user(username="optlibstaff", password="pass12345", is_staff=True)
        StoreMembership.objects.create(
            store=self.store, user=self.staff, role=StoreMembership.Role.OWNER,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )
        self.client = Client(HTTP_HOST=HOST)
        self.client.login(username="optlibstaff", password="pass12345")

    def test_product_options_page_renders(self):
        response = self.client.get(reverse("dashboard:product-options", args=[self.product.pk]))
        self.assertEqual(response.status_code, 200)

    def test_add_attribute_creates_library_entry_and_renders(self):
        from apps.catalog.models import Attribute

        response = self.client.post(
            reverse("dashboard:product-option-add", args=[self.product.pk]),
            {"label": "کشور سازنده", "raw_values": "ایرانی، ایتالیایی"},
        )
        self.assertEqual(response.status_code, 200)
        attribute = Attribute.objects.get(store=self.store, label="کشور سازنده")
        self.assertTrue(attribute.is_variant_axis)
        self.assertEqual(attribute.values.count(), 2)

    def test_library_picker_shows_on_second_product(self):
        attribute = create_attribute(self.store, label="کشور سازنده", is_variant_axis=True)
        create_attribute_value(attribute, label="ایرانی")
        create_attribute_value(attribute, label="ایتالیایی")
        response = self.client.get(reverse("dashboard:product-options", args=[self.product.pk]))
        self.assertContains(response, "کشور سازنده")
        self.assertContains(response, "انتخاب از کتابخانه‌ی ویژگی‌ها")

    def test_sales_limit_modal_save_and_clear(self):
        option = add_product_option(self.product, label="کشور سازنده", values=["ایرانی", "ایتالیایی"])
        generate_variants(self.product)
        variant = self.product.variants.filter(is_obsolete=False).first()
        response = self.client.post(
            reverse("dashboard:product-variant-set-sales-limit", args=[self.product.pk, variant.pk]),
            {"sales_limit_min": "1", "sales_limit_max": "5"},
        )
        self.assertEqual(response.status_code, 200)
        variant.refresh_from_db()
        self.assertEqual(variant.sales_limit_min, 1)
        self.assertEqual(variant.sales_limit, 5)

        response = self.client.post(
            reverse("dashboard:product-variant-set-sales-limit", args=[self.product.pk, variant.pk]),
            {"sales_limit_min": "", "sales_limit_max": ""},
        )
        self.assertEqual(response.status_code, 200)
        variant.refresh_from_db()
        self.assertIsNone(variant.sales_limit_min)
        self.assertIsNone(variant.sales_limit)

    def test_sales_limit_min_gt_max_rejected(self):
        add_product_option(self.product, label="کشور سازنده", values=["ایرانی"])
        generate_variants(self.product)
        variant = self.product.variants.filter(is_obsolete=False).first()
        response = self.client.post(
            reverse("dashboard:product-variant-set-sales-limit", args=[self.product.pk, variant.pk]),
            {"sales_limit_min": "10", "sales_limit_max": "2"},
        )
        self.assertEqual(response.status_code, 200)
        variant.refresh_from_db()
        self.assertIsNone(variant.sales_limit)

    def test_keep_open_creates_draft_and_shows_inline_variant_ui(self):
        """بخشِ ۸ — پیکربندیِ تنوع در حینِ ساختِ کالا باید ممکن باشد (نه اجباری):
        دکمه‌ی «ذخیره و ادامه با تنظیمِ ویژگی‌ها» باید کالا را بسازد و همان‌
        پارشالِ صفحه‌ی «پیکربندیِ تنوع‌ها» را همان‌جا نمایش دهد."""
        response = self.client.post(
            reverse("dashboard:product-add"),
            {
                "name": "کالای جدید", "sku": "OPTLIB-NEW1", "category": self.category.pk,
                "product_type": "variable", "price": "1", "discount_percent": "0",
                "status": "draft", "keep_open": "1",
            },
        )
        self.assertEqual(response.status_code, 200)
        new_product = Product.objects.get(sku="OPTLIB-NEW1")
        self.assertEqual(new_product.product_type, Product.ProductType.VARIABLE)
        self.assertContains(response, "ویژگی‌های تنوع‌ساز")
        self.assertContains(response, 'id="productOptionsBody"')
        self.assertContains(response, reverse("dashboard:product-edit", args=[new_product.pk]))

    def test_keep_open_reopened_form_reflects_saved_values_not_blank_defaults(self):
        """رگرسیون: ``ProductForm`` یک ``forms.Form`` سادّه است، نه
        ``ModelForm`` — دادنِ ``instance=`` بدونِ ``initial=`` مقادیرِ فیلدها
        را پر نمی‌کند. باگِ واقعی‌ای که این تست رویش می‌ایستد: مسیرِ
        keep_open یک بار این ``initial=`` را فراموش کرده بود، پس مودالِ
        بازشده «نوعِ کالا» را دوباره به «کالایِ ساده» ریست می‌کرد — با
        وجودِ اینکه در دیتابیس درست «دارای تنوع» ذخیره شده بود — و همه‌ی
        فیلدهایِ دیگر (نام، برند، توضیحات، سئو، نمایش) هم خالی می‌شدند."""
        response = self.client.post(
            reverse("dashboard:product-add"),
            {
                "name": "کالای تست ریست", "sku": "OPTLIB-NEW2", "category": self.category.pk,
                "product_type": "variable", "price": "543210", "discount_percent": "5",
                "status": "draft", "seo_title": "عنوانِ سئوی تست", "visibility": "link",
                "keep_open": "1",
            },
        )
        self.assertEqual(response.status_code, 200)
        new_product = Product.objects.get(sku="OPTLIB-NEW2")
        self.assertEqual(new_product.product_type, Product.ProductType.VARIABLE)
        self.assertEqual(new_product.visibility, Product.Visibility.LINK_ONLY)

        # مودالِ بازشده باید همین مقادیر را — نه خالی/پیش‌فرض — نشان دهد.
        content = response.content.decode()
        self.assertIn('value="کالای تست ریست"', content)
        self.assertIn('value="عنوانِ سئوی تست"', content)
        self.assertIn("productType: 'variable'", content)
        self.assertRegex(content, r'<option value="link" selected>')

    def test_editing_variable_product_with_variants_keeps_base_price_intact(self):
        """رگرسیونِ تداخلِ نام‌گذاری: وقتی فرمِ کالا (که حالا شاملِ ردیف‌هایِ
        تنوع با ورودی‌هایِ پنهانِ قیمتِ خودشان است) ذخیره می‌شود، قیمتِ پایه‌ی
        محصول نباید با قیمتِ هیچ‌کدام از تنوع‌ها اشتباه گرفته شود."""
        add_product_option(self.product, label="کشور سازنده", values=["ایرانی", "ایتالیایی"])
        generate_variants(self.product)
        variant = self.product.variants.filter(is_obsolete=False).first()
        self.client.post(
            reverse("dashboard:product-variant-set-price", args=[self.product.pk, variant.pk]),
            {"variant_price": "999999", "variant_discount_percent": "0"},
        )
        response = self.client.post(
            reverse("dashboard:product-edit", args=[self.product.pk]),
            {
                "name": self.product.name, "sku": self.product.sku, "category": self.category.pk,
                "product_type": "variable", "price": "250000", "discount_percent": "0",
                "status": "draft",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.product.refresh_from_db()
        self.assertEqual(self.product.price, Decimal("250000"))

    def test_library_attribute_is_store_scoped_never_crosses_stores(self):
        """بخشِ ۲۸ — کتابخانه‌ی ویژگیِ فروشگاه باید کاملاً store-scoped باشد:
        ویژگیِ ساخته‌شده برایِ فروشگاهِ دیگر هرگز نباید در «ویژگی‌های
        استفاده‌شده در فروشگاه» یا نتیجه‌ی get_or_create این فروشگاه ظاهر شود،
        حتی اگر برچسبِ آن (case-insensitive) دقیقاً یکسان باشد."""
        other_store = Store.objects.create(
            name="فروشگاه دیگر", slug="optlib-other", status=Store.Status.ACTIVE,
            admin_subdomain="optlib-other", platform_code="OPTLIBOTH1",
        )
        other_attribute = create_attribute(other_store, label="کشور سازنده", is_variant_axis=True)
        create_attribute_value(other_attribute, label="ایرانی")

        response = self.client.get(reverse("dashboard:product-options", args=[self.product.pk]))
        self.assertNotContains(response, "ویژگی‌های استفاده‌شده در فروشگاه")

        response = self.client.post(
            reverse("dashboard:product-option-add", args=[self.product.pk]),
            {"label": "کشور سازنده", "raw_values": "ایتالیایی"},
        )
        self.assertEqual(response.status_code, 200)
        from apps.catalog.models import Attribute

        own_attribute = Attribute.objects.get(store=self.store, label="کشور سازنده")
        self.assertNotEqual(own_attribute.pk, other_attribute.pk)
        self.assertEqual(own_attribute.values.count(), 1)
        self.assertEqual(other_attribute.values.count(), 1)

    def test_removing_value_from_product_does_not_delete_it_from_library(self):
        """حذفِ یک مقدار از یک کالا نباید آن را از کتابخانه‌ی فروشگاه حذف کند —
        فقط لینکِ ProductOptionValueِ همین کالا حذف می‌شود. ساختِ محور از
        طریقِ ویو انجام می‌شود چون اتصالِ به کتابخانه (بخشِ ۲۸) در همان لایه
        اعمال می‌شود، نه در ``add_product_option`` خودِ سرویس."""
        from apps.catalog.models import Attribute
        from apps.catalog.services.variant_engine_service import remove_option_value

        self.client.post(
            reverse("dashboard:product-option-add", args=[self.product.pk]),
            {"label": "کشور سازنده", "raw_values": "ایرانی، ایتالیایی"},
        )
        library_attribute = Attribute.objects.get(store=self.store, label__iexact="کشور سازنده")
        self.assertEqual(library_attribute.values.count(), 2)

        option = self.product.options.get(label="کشور سازنده")
        value_to_remove = option.values.get(label="ایرانی")
        remove_option_value(value_to_remove)

        library_attribute.refresh_from_db()
        self.assertEqual(library_attribute.values.count(), 2)
        self.assertEqual(option.values.count(), 1)

    def test_deactivating_attribute_on_product_does_not_delete_it_from_library(self):
        """غیرفعال‌کردنِ یک محور روی یک کالا (مکانیزمِ موجود برایِ «حذفِ ویژگی
        از این کالا») نباید ویژگیِ متناظرش را از کتابخانه‌ی فروشگاه حذف کند."""
        from apps.catalog.models import Attribute
        from apps.catalog.services.variant_engine_service import deactivate_product_option

        self.client.post(
            reverse("dashboard:product-option-add", args=[self.product.pk]),
            {"label": "کشور سازنده", "raw_values": "ایرانی"},
        )
        library_attribute = Attribute.objects.get(store=self.store, label__iexact="کشور سازنده")
        option = self.product.options.get(label="کشور سازنده")

        deactivate_product_option(option)

        self.assertTrue(Attribute.objects.filter(pk=library_attribute.pk, is_active=True).exists())
        self.assertEqual(library_attribute.values.count(), 1)


@override_settings(ALLOWED_HOSTS=[HOST, "testserver"])
class VariantDisplayImagePriorityRegressionTests(TestCase):
    """رگرسیون: ``ProductVariant.display_image`` (استفاده‌شده در جدولِ
    «پیکربندیِ تنوع‌ها»یِ پنلِ مدیریت) پیش‌تر فقط اولویتِ ۱ (تصویرِ دقیقِ
    تنوع) و ۳ (کاورِ کالا) را پیاده می‌کرد و اولویتِ ۲ (تصویرِ اختصاص‌یافته
    به مقدارِ ویژگیِ تصویرمحور — مثلاً رنگ) را نادیده می‌گرفت؛ یعنی برایِ
    کالاهایِ چندمحوره (مثلاً رنگ×سایز)، پنلِ مدیریت همیشه تصویرِ کاور را
    نشان می‌داد حتی وقتی تصویرِ رنگ درست map شده بود — با وجودی که همین
    اولویت در فروشگاه (``storefront_variant_service``) درست کار می‌کرد.
    این تست ثابت می‌کند هر دو مسیر اکنون از یک تابعِ مشترک استفاده
    می‌کنند."""

    def setUp(self):
        from apps.catalog.services.attribute_service import create_attribute
        from apps.catalog.services.product_image_service import add_product_image, set_image_option_value
        from apps.catalog.services.variant_engine_service import add_product_option, generate_variants

        self.store = Store.objects.create(
            name="فروشگاه تست", slug="dispimg", status=Store.Status.ACTIVE,
            admin_subdomain="dispimg", platform_code="DISPIMG01",
        )
        self.vendor = Vendor.objects.create(store=self.store, name="فروشنده", slug="dispimg-shop")
        self.category_group = Category.objects.create(store=self.store, name="گروه", slug="dispimg-group")
        self.category = Category.objects.create(
            store=self.store, name="دسته", slug="dispimg-cat", parent=self.category_group,
        )
        self.product = Product.objects.create(
            store=self.store, vendor=self.vendor, category=self.category, name="تی‌شرت",
            slug="dispimg-tshirt", sku="DISPIMG-SKU1", price=Decimal("100000"),
            product_type=Product.ProductType.VARIABLE,
        )
        color_attribute = create_attribute(self.store, label="رنگ", is_variant_axis=True, is_image_driving=True)
        add_product_option(self.product, label="رنگ", attribute=color_attribute, values=["قرمز", "آبی"])
        generate_variants(self.product)

        import io

        from django.core.files.uploadedfile import SimpleUploadedFile
        from PIL import Image

        def _tiny_image(name):
            buf = io.BytesIO()
            Image.new("RGB", (10, 10), (200, 30, 30)).save(buf, format="JPEG")
            return SimpleUploadedFile(name, buf.getvalue(), content_type="image/jpeg")

        red_option_value = self.product.options.get(label="رنگ").values.get(label="قرمز")
        self.cover_image = add_product_image(self.product, _tiny_image("cover.jpg"))
        self.red_image = add_product_image(self.product, _tiny_image("red.jpg"))
        set_image_option_value(self.red_image, red_option_value)

    def test_variant_with_mapped_value_image_shows_mapped_image_not_cover(self):
        red_variant = self.product.variants.filter(is_obsolete=False, value="قرمز").first()
        self.assertEqual(red_variant.display_image.pk, self.red_image.pk)

    def test_variant_without_mapped_value_image_falls_back_to_cover(self):
        blue_variant = self.product.variants.filter(is_obsolete=False, value="آبی").first()
        self.assertEqual(blue_variant.display_image.pk, self.cover_image.pk)
