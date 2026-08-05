import json
import shutil
import tempfile
from decimal import Decimal
from io import BytesIO

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from PIL import Image

from apps.catalog.models import Brand, Category, Product, ProductImage, ProductVideo, Vendor
from apps.stores.models import Store, StoreMembership


def _make_image_file(name="staged.jpg", color="#3355ff"):
    buffer = BytesIO()
    Image.new("RGB", (300, 300), color).save(buffer, format="JPEG")
    return SimpleUploadedFile(name, buffer.getvalue(), content_type="image/jpeg")

User = get_user_model()

HOST = "pv-test.rastisi.ir"


def _akhlaghi():
    return Store.objects.get(slug="akhlaghi")


@override_settings(ALLOWED_HOSTS=[HOST, "testserver"])
class ProductViewsTestCase(TestCase):
    def setUp(self):
        self.store = _akhlaghi()
        self.store.admin_subdomain = HOST.split(".")[0]
        self.store.save(update_fields=["admin_subdomain"])
        self.vendor = Vendor.objects.create(store=self.store, name="فروشگاه", slug="shop-pv")
        self.main = Category.objects.create(store=self.store, name="دیجیتال", slug="main-pv")
        self.sub = Category.objects.create(store=self.store, name="موبایل", slug="sub-pv", parent=self.main)
        self.product = Product.objects.create(
            store=self.store, vendor=self.vendor, category=self.sub, name="گوشی هوشمند", slug="phone-pv",
            sku="SKU-PV1", price=Decimal("1000000"), stock=5,
        )
        self.staff = User.objects.create_user(username="09121122001", password="pass12345", is_staff=True)
        StoreMembership.objects.create(
            store=self.store, user=self.staff, role=StoreMembership.Role.OWNER,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )
        self.client = Client(HTTP_HOST=HOST)
        self.client.login(username="09121122001", password="pass12345")


class ProductListViewTests(ProductViewsTestCase):
    def test_renders_product_table(self):
        response = self.client.get(reverse("dashboard:product-list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "گوشی هوشمند")
        self.assertContains(response, "SKU-PV1")

    def test_anonymous_denied(self):
        self.client.logout()
        response = self.client.get(reverse("dashboard:product-list"))
        self.assertEqual(response.status_code, 302)
        self.assertNotIn("/admin-portal/login/", response.url)
        self.assertIn("admin_return=", response.url)
    def test_search_filters_table(self):
        response = self.client.get(reverse("dashboard:product-table"), {"q": "گوشی"})
        self.assertContains(response, "گوشی هوشمند")

    def test_search_excludes_non_matching(self):
        response = self.client.get(reverse("dashboard:product-table"), {"q": "چیز-نامرتبط"})
        self.assertNotContains(response, "گوشی هوشمند")
        self.assertContains(response, "کالایی با این فیلترها یافت نشد")
        self.assertContains(response, "حذفِ فیلترها")

    def test_empty_store_shows_add_first_product_cta(self):
        self.product.delete()
        response = self.client.get(reverse("dashboard:product-list"))
        self.assertContains(response, "هنوز کالایی ثبت نشده است")
        self.assertContains(response, reverse("dashboard:product-add"))
        self.assertNotContains(response, "حذفِ فیلترها")

    def test_out_of_stock_filter(self):
        Product.objects.create(
            store=self.store, vendor=self.vendor, category=self.sub, name="کالای ناموجود", slug="oos-pv",
            sku="SKU-PV2", price=Decimal("1000"), stock=0,
        )
        response = self.client.get(reverse("dashboard:product-table"), {"status": "out"})
        self.assertContains(response, "کالای ناموجود")
        self.assertNotContains(response, "گوشی هوشمند")

    def test_health_no_seo_filter_from_dashboard_link(self):
        """self.product has no SEO title/description by default — matches
        the health=no_seo filter used by the dashboard's «بدونِ سئو» card."""
        Product.objects.create(
            store=self.store, vendor=self.vendor, category=self.sub, name="کالای دارایِ سئو", slug="seo-pv",
            sku="SKU-PV3", price=Decimal("1000"), seo_title="عنوان", seo_description="توضیح",
        )
        response = self.client.get(reverse("dashboard:product-list"), {"health": "no_seo"})
        self.assertContains(response, "گوشی هوشمند")
        self.assertNotContains(response, "کالای دارایِ سئو")

    def test_health_filter_banner_shown_with_clear_link(self):
        response = self.client.get(reverse("dashboard:product-list"), {"health": "no_images"})
        self.assertContains(response, "هنوز تصویری ندارند")
        self.assertContains(response, reverse("dashboard:product-list"))

    def test_no_health_filter_no_banner(self):
        response = self.client.get(reverse("dashboard:product-list"))
        self.assertNotContains(response, "حذفِ فیلتر")

    def test_unknown_health_value_falls_back_to_unfiltered(self):
        response = self.client.get(reverse("dashboard:product-list"), {"health": "bogus"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "گوشی هوشمند")

    def test_variable_product_shows_configure_variants_button(self):
        self.product.product_type = Product.ProductType.VARIABLE
        self.product.save(update_fields=["product_type"])
        response = self.client.get(reverse("dashboard:product-list"))
        self.assertContains(response, "پیکربندیِ تنوع‌ها")
        self.assertContains(response, reverse("dashboard:product-options", args=[self.product.pk]))

    def test_simple_product_has_no_configure_variants_button(self):
        response = self.client.get(reverse("dashboard:product-list"))
        self.assertNotContains(response, "پیکربندیِ تنوع‌ها")


class ProductAddViewTests(ProductViewsTestCase):
    def _payload(self, **overrides):
        payload = {
            "name": "کالای جدید", "sku": "SKU-NEW1", "category": self.sub.id,
            "price": "500000", "discount_percent": "0", "stock": "10",
            "status": "active", "icon": "🎁", "description": "",
        }
        payload.update(overrides)
        return payload

    def test_get_returns_empty_form(self):
        response = self.client.get(reverse("dashboard:product-add"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "افزودن کالای جدید")

    def test_valid_post_creates_product(self):
        response = self.client.post(reverse("dashboard:product-add"), self._payload())
        self.assertEqual(response.status_code, 200)
        product = Product.objects.get(sku="SKU-NEW1")
        self.assertEqual(product.name, "کالای جدید")
        self.assertEqual(product.vendor, self.vendor)
        self.assertTrue(product.slug)
        trigger = json.loads(response.headers["HX-Trigger"])
        self.assertIn("modal-close", trigger)

    def test_persian_digits_are_normalized(self):
        response = self.client.post(reverse("dashboard:product-add"), self._payload(
            price="۵۰۰۰۰۰", discount_percent="۱۰", stock="۷",
        ))
        self.assertEqual(response.status_code, 200)
        product = Product.objects.get(sku="SKU-NEW1")
        self.assertEqual(product.price, Decimal("500000"))
        self.assertEqual(product.discount_percent, 10)
        self.assertEqual(product.stock, 7)

    def test_duplicate_sku_rejected(self):
        response = self.client.post(reverse("dashboard:product-add"), self._payload(sku="SKU-PV1"))
        self.assertContains(response, "قبلاً استفاده شده است")
        self.assertEqual(Product.objects.filter(sku="SKU-PV1").count(), 1)

    def test_tags_survive_a_validation_error_round_trip(self):
        """رگرسیون: قبل از این وصله، وقتی فرم با خطا (مثلاً SKU تکراری)
        دوباره رندر می‌شد، برچسب‌هایِ تازه‌واردشده‌ی کاربر بی‌سروصدا از دست
        می‌رفتند چون کانتکست همیشه از رویِ product.tags (خالی، چون کالا هنوز
        ساخته نشده) پر می‌شد، نه از رویِ داده‌ی واقعاً ارسال‌شده."""
        response = self.client.post(
            reverse("dashboard:product-add"), self._payload(sku="SKU-PV1", tags="نخی,تابستانی"),
        )
        self.assertContains(response, "قبلاً استفاده شده است")
        content = response.content.decode()
        self.assertIn('id="existing-tags-data"', content)
        import json as _json

        tags_json_start = content.index('id="existing-tags-data"')
        script_start = content.index(">", tags_json_start) + 1
        script_end = content.index("</script>", script_start)
        self.assertEqual(_json.loads(content[script_start:script_end]), ["نخی", "تابستانی"])

    def test_tags_are_created_and_assigned_on_success(self):
        response = self.client.post(reverse("dashboard:product-add"), self._payload(tags="نخی, تابستانی"))
        self.assertEqual(response.status_code, 200)
        product = Product.objects.get(sku="SKU-NEW1")
        self.assertEqual(set(product.tags.values_list("name", flat=True)), {"نخی", "تابستانی"})

    def test_missing_required_fields_rejected(self):
        response = self.client.post(reverse("dashboard:product-add"), self._payload(name="", category=""))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Product.objects.filter(sku="SKU-NEW1").exists())

    def test_top_level_category_not_offered(self):
        """زیرگروهِ #id_category دیگر مستقیماً در HTMLِ سمتِ سرور رندر نمی‌شود —
        طبقِ پروتوتایپِ نهایی، فقط یک placeholderِ خالی سرور رندر می‌کند و
        Alpine گزینه‌ها را از رویِ group_leaf_options_json (بر اساسِ گروهِ
        اصلیِ انتخاب‌شده) با x-for می‌سازد؛ نگاه کنید به
        ``product_category_select.html``. این تست همان قاعده‌ی قدیم را (گروهِ
        اصلی هرگز به‌عنوانِ یک برگِ قابلِ‌انتخاب ظاهر نمی‌شود، فقط زیرگروهِ
        واقعی) رویِ همان دادهٔ JSON بررسی می‌کند."""
        response = self.client.get(reverse("dashboard:product-add"))
        content = response.content.decode()
        script_start = content.index('id="group-leaf-options-data"')
        script_open = content.index(">", script_start) + 1
        script_end = content.index("</script>", script_open)
        group_leaf_options = json.loads(content[script_open:script_end])
        leaf_ids_under_group = {leaf["id"] for leaf in group_leaf_options.get(str(self.main.id), [])}
        self.assertIn(self.sub.id, leaf_ids_under_group)
        self.assertNotIn(self.main.id, leaf_ids_under_group)
        # خودِ #id_category در HTMLِ خام فقط placeholderِ خالی دارد — گزینه‌ها
        # کلاینت‌ساخته‌اند، نه سرورساخته.
        category_select = content[content.index('id="id_category"'):content.index("</select>", content.index('id="id_category"'))]
        self.assertNotIn(f'value="{self.sub.id}"', category_select)

    def test_blank_icon_defaults(self):
        self.client.post(reverse("dashboard:product-add"), self._payload(icon=""))
        product = Product.objects.get(sku="SKU-NEW1")
        self.assertEqual(product.icon, "🛍️")


class ProductWizardTests(ProductViewsTestCase):
    """فرمِ افزودنِ کالا پنج بخشِ اصلی دارد (اطلاعات پایه / دسته‌بندی /
    قیمت و تنوع / تصاویر و فیلم / سئو و انتشار)، همه در یک <form> واحد
    (بدون از دست رفتنِ داده بین تب‌ها)، با اعتبارسنجیِ سمتِ سرور که کاربر
    را دقیقاً به تبِ دارایِ خطا هدایت می‌کند. تبِ قیمت خودش ساده است —
    نوعِ کالا و دکمه‌ی «تنظیمِ قیمت» (که مودال باز می‌کند)؛ مدیریتِ
    ویژگی/تنوع در صفحه‌ی جداگانه‌ی «پیکربندیِ تنوع‌ها» انجام می‌شود، نه
    داخلِ ویزارد."""

    def _payload(self, **overrides):
        payload = {
            "name": "کالای ویزارد", "sku": "SKU-WIZ1", "category": self.sub.id,
            "price": "500000", "discount_percent": "0", "stock": "10",
            "status": "active", "icon": "🎁", "description": "",
        }
        payload.update(overrides)
        return payload

    def test_form_renders_all_tabs_in_one_form(self):
        response = self.client.get(reverse("dashboard:product-add"))
        content = response.content.decode()
        self.assertEqual(content.count("<form"), 1)  # یک فرمِ واحد، نه فرم‌های جداگانه‌ی هر تب
        for ref in ["tabBasic", "tabCategory", "tabMedia", "tabPrice", "tabSeo"]:
            self.assertIn(f'x-ref="{ref}"', content)

    def test_tab_labels_present(self):
        response = self.client.get(reverse("dashboard:product-add"))
        self.assertContains(response, "اطلاعات پایه")
        self.assertContains(response, "دسته‌بندی")
        self.assertContains(response, "قیمت و تنوع")
        self.assertContains(response, "تصاویر و فیلم")
        self.assertContains(response, "سئو و انتشار")

    def test_pricing_tab_shows_simple_variable_toggle_and_inline_price_fields(self):
        """تبِ «قیمت و تنوع» طبقِ پروتوتایپِ نهایی: یک سوییچِ دوحالته‌ی
        کالای‌ساده/کالای‌دارایِ‌تنوع، و برایِ حالتِ ساده فیلدهایِ مستقیمِ
        قیمت/تخفیف/موجودی — نه دکمه‌ای که مودالِ جداگانه باز کند، و نه
        فیلدهایِ مخفی. برایِ کالایِ تازه (بدونِ ذخیره‌ی قبلی)، پنلِ
        productOptionsBody هنوز رندر نمی‌شود (چون هنوز کالایی برایِ
        اتصالِ محورهایِ تنوع وجود ندارد)."""
        response = self.client.get(reverse("dashboard:product-add"))
        content = response.content.decode()
        tab_start = content.index('x-ref="tabPrice"')
        tab_end = content.index('x-ref="tabSeo"')
        tab_html = content[tab_start:tab_end]
        self.assertIn("کالای ساده", tab_html)
        self.assertIn("کالای دارای تنوع", tab_html)
        self.assertIn('id="simpleBox"', tab_html)
        self.assertIn('name="price"', tab_html)
        self.assertIn('name="discount_percent"', tab_html)
        self.assertIn('name="stock"', tab_html)
        self.assertNotIn('type="hidden" name="price"', tab_html)
        self.assertNotIn("variant-table", tab_html)
        self.assertNotIn("id=\"productOptionsBody\"", content)

    def test_simple_price_field_has_no_fake_default_placeholder(self):
        """طبقِ الزامِ پروتوتایپ: وقتی قیمت هنوز تنظیم نشده، فیلدِ قیمت باید
        خالی/placeholderِ «تنظیم نشده» را نشان دهد — نه یک مقدارِ ساختگیِ
        از پیش‌پرشده (مثلاً «۱ تومان»)."""
        response = self.client.get(reverse("dashboard:product-add"))
        content = response.content.decode()
        tab_start = content.index('x-ref="tabPrice"')
        tab_end = content.index('x-ref="tabSeo"')
        tab_html = content[tab_start:tab_end]
        self.assertIn('placeholder="تنظیم نشده"', tab_html)
        price_input_start = tab_html.index('name="price"')
        price_input_tag = tab_html[max(0, price_input_start - 40):price_input_start + 120]
        self.assertNotIn('value="1"', price_input_tag)

    def test_basic_info_tab_contains_brand(self):
        """برند در تبِ «اطلاعات پایه» است؛ دسته‌بندی در تبِ جداگانه‌ی «دسته‌بندی»
        است (نگاه کنید به ``test_product_form_wizard_steps.py`` برای پوششِ
        دقیقِ محلِ قرارگیریِ فیلدِ دسته‌بندی)."""
        response = self.client.get(reverse("dashboard:product-add"))
        content = response.content.decode()
        tab_start = content.index('x-ref="tabBasic"')
        tab_end = content.index('x-ref="tabCategory"')
        tab_html = content[tab_start:tab_end]
        self.assertIn('name="brand"', tab_html)
        self.assertNotIn('name="category"', tab_html)

    def test_price_tab_contains_attributes_and_variant_type(self):
        """ویژگی‌های اختصاصیِ دسته‌بندی و نوعِ کالا در همان تبِ «قیمت و تنوع» هستند."""
        response = self.client.get(reverse("dashboard:product-add"))
        content = response.content.decode()
        tab_start = content.index('x-ref="tabPrice"')
        tab_end = content.index('x-ref="tabSeo"')
        tab_html = content[tab_start:tab_end]
        self.assertIn('name="product_type"', tab_html)
        self.assertIn("productAttributeFields", tab_html)

    def test_error_step_routes_to_category_tab_when_category_missing(self):
        response = self.client.post(reverse("dashboard:product-add"), self._payload(category=""))
        self.assertEqual(response.status_code, 200)
        self.assertIn("tab: 'category',", response.content.decode())

    def test_error_step_routes_to_price_tab_when_price_missing(self):
        response = self.client.post(reverse("dashboard:product-add"), self._payload(price=""))
        self.assertEqual(response.status_code, 200)
        self.assertIn("tab: 'price',", response.content.decode())

    def test_error_step_defaults_to_basic_on_fresh_get(self):
        response = self.client.get(reverse("dashboard:product-add"))
        self.assertIn("tab: 'basic',", response.content.decode())

    def test_missing_category_banner_shown_when_store_has_no_categories(self):
        Product.objects.filter(store=self.store).delete()
        Category.objects.filter(store=self.store).delete()
        response = self.client.get(reverse("dashboard:product-add"))
        self.assertContains(response, "این فروشگاه هنوز هیچ دسته‌بندی‌ای ندارد")

    def test_valid_submission_across_all_fields_still_creates_product(self):
        """اطمینان از این‌که ادغامِ مراحل هیچ فیلدی را از دست نداده است."""
        response = self.client.post(reverse("dashboard:product-add"), self._payload(
            barcode="1234567890123", weight_grams="500", requires_shipping="on",
            seo_title="عنوان سئو", seo_description="توضیح سئو",
        ))
        self.assertEqual(response.status_code, 200)
        product = Product.objects.get(sku="SKU-WIZ1")
        self.assertEqual(product.barcode, "1234567890123")
        self.assertEqual(product.seo_title, "عنوان سئو")


class ProductEditViewTests(ProductViewsTestCase):
    def test_get_prefills_form(self):
        response = self.client.get(reverse("dashboard:product-edit", args=[self.product.pk]))
        self.assertContains(response, "ویرایش کالا")
        self.assertContains(response, "گوشی هوشمند")

    def test_media_tab_is_reachable_from_the_five_step_tab_strip(self):
        """طبقِ پروتوتایپِ نهایی، دیگر دکمه‌ی میان‌بُرِ «رفتن به تبِ تصاویر»
        داخلِ تبِ «اطلاعاتِ پایه» وجود ندارد — ناوبری فقط از طریقِ نوارِ
        پنج‌مرحله‌ایِ بالای فرم انجام می‌شود (همان‌طور که پروتوتایپ نشان
        می‌دهد)؛ همان نوار باید دکمه‌ای برایِ تبِ «تصاویر و فیلم» داشته
        باشد."""
        response = self.client.get(reverse("dashboard:product-edit", args=[self.product.pk]))
        content = response.content.decode()
        self.assertNotIn("@click=\"tab = 'media'\"", content)
        self.assertIn("@click=\"tab = key\"", content)
        self.assertIn("تصاویر و فیلم", content)

    def test_media_tab_uploads_via_htmx_for_existing_product(self):
        """برایِ کالای موجود، آپلودِ تصویر در تبِ «تصاویر و ویدیو» مستقیماً با htmx
        (بدونِ رفتن به صفحه‌ی جدا) به endpointِ آپلود وصل است."""
        upload_url = reverse("dashboard:product-image-upload", args=[self.product.pk])
        response = self.client.get(reverse("dashboard:product-edit", args=[self.product.pk]))
        self.assertContains(response, f'hx-post="{upload_url}"')
        self.assertContains(response, 'hx-target="#productImagesList"')

    def test_media_tab_does_not_say_save_first_for_existing_product(self):
        response = self.client.get(reverse("dashboard:product-edit", args=[self.product.pk]))
        self.assertNotContains(response, "پس از ذخیره‌ی این کالا می‌توانید")

    def test_valid_edit_updates_product(self):
        payload = {
            "name": "گوشی هوشمند - ویرایش‌شده", "sku": "SKU-PV1", "category": self.sub.id,
            "price": "1200000", "discount_percent": "5", "stock": "3",
            "status": "active", "icon": "📱", "description": "",
        }
        response = self.client.post(reverse("dashboard:product-edit", args=[self.product.pk]), payload)
        self.assertEqual(response.status_code, 200)
        self.product.refresh_from_db()
        self.assertEqual(self.product.name, "گوشی هوشمند - ویرایش‌شده")
        self.assertEqual(self.product.stock, 3)

    def test_editing_does_not_change_slug(self):
        original_slug = self.product.slug
        payload = {
            "name": "نام کاملاً متفاوت", "sku": "SKU-PV1", "category": self.sub.id,
            "price": "1200000", "discount_percent": "0", "stock": "3",
            "status": "active", "icon": "", "description": "",
        }
        self.client.post(reverse("dashboard:product-edit", args=[self.product.pk]), payload)
        self.product.refresh_from_db()
        self.assertEqual(self.product.slug, original_slug)

    def test_sku_uniqueness_excludes_self(self):
        payload = {
            "name": "گوشی هوشمند", "sku": "SKU-PV1", "category": self.sub.id,
            "price": "1000000", "discount_percent": "0", "stock": "5",
            "status": "active", "icon": "", "description": "",
        }
        response = self.client.post(reverse("dashboard:product-edit", args=[self.product.pk]), payload)
        self.assertNotContains(response, "قبلاً استفاده شده است")


class ProductSeoAndLogisticsFieldsTests(ProductViewsTestCase):
    def _payload(self, **overrides):
        payload = {
            "name": "کالای جدید", "sku": "SKU-NEW1", "category": self.sub.id,
            "price": "500000", "discount_percent": "0", "stock": "10",
            "status": "active", "icon": "🎁", "description": "",
        }
        payload.update(overrides)
        return payload

    def test_create_persists_barcode_weight_and_seo_fields(self):
        self.client.post(reverse("dashboard:product-add"), self._payload(
            barcode="6221000000015", weight_grams="450",
            seo_title="عنوان سئوی محصول", seo_description="توضیحات متای محصول",
            requires_shipping="on",
        ))
        product = Product.objects.get(sku="SKU-NEW1")
        self.assertEqual(product.barcode, "6221000000015")
        self.assertEqual(product.weight_grams, 450)
        self.assertTrue(product.requires_shipping)
        self.assertEqual(product.seo_title, "عنوان سئوی محصول")
        self.assertEqual(product.seo_description, "توضیحات متای محصول")

    def test_requires_shipping_unchecked_is_persisted_as_false(self):
        self.client.post(reverse("dashboard:product-add"), self._payload())
        product = Product.objects.get(sku="SKU-NEW1")
        self.assertFalse(product.requires_shipping)

    def test_negative_weight_rejected(self):
        response = self.client.post(reverse("dashboard:product-add"), self._payload(weight_grams="-5"))
        self.assertContains(response, "وزن نمی‌تواند منفی باشد")
        self.assertFalse(Product.objects.filter(sku="SKU-NEW1").exists())

    def test_non_numeric_weight_rejected(self):
        response = self.client.post(reverse("dashboard:product-add"), self._payload(weight_grams="سنگین"))
        self.assertContains(response, "وزن باید یک عدد صحیح باشد")
        self.assertFalse(Product.objects.filter(sku="SKU-NEW1").exists())

    def test_blank_weight_saved_as_none(self):
        self.client.post(reverse("dashboard:product-add"), self._payload(weight_grams=""))
        product = Product.objects.get(sku="SKU-NEW1")
        self.assertIsNone(product.weight_grams)

    def test_edit_prefills_seo_and_logistics_fields(self):
        self.product.barcode = "1112223334445"
        self.product.weight_grams = 200
        self.product.seo_title = "عنوان قدیمی"
        self.product.save()
        response = self.client.get(reverse("dashboard:product-edit", args=[self.product.pk]))
        self.assertContains(response, "1112223334445")
        self.assertContains(response, "عنوان قدیمی")

    def test_brand_assignment_on_create(self):
        brand = Brand.objects.create(store=self.store, name="برند من", slug="brand-pv")
        response = self.client.post(reverse("dashboard:product-add"), self._payload(brand=brand.pk))
        self.assertEqual(response.status_code, 200)
        product = Product.objects.get(sku="SKU-NEW1")
        self.assertEqual(product.brand_id, brand.pk)

    def test_blank_brand_allowed(self):
        self.client.post(reverse("dashboard:product-add"), self._payload(brand=""))
        product = Product.objects.get(sku="SKU-NEW1")
        self.assertIsNone(product.brand_id)

    def test_other_store_brand_rejected(self):
        other_store = Store.objects.create(name="فروشگاه دیگر", slug="other-pv-brand", status=Store.Status.ACTIVE)
        other_brand = Brand.objects.create(store=other_store, name="برند دیگر", slug="other-brand-pv")
        response = self.client.post(reverse("dashboard:product-add"), self._payload(brand=other_brand.pk))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Product.objects.filter(sku="SKU-NEW1").exists())


class ProductUnitModelCodeCountryFieldsTests(ProductViewsTestCase):
    """واحدِ شمارش/مدل-کدِ فنی/کشورِ سازنده (Product Entry final wave 1) —
    هر سه در تبِ «دسته‌بندی» فرم هستند، هر سه اختیاری به‌جز unit (که همیشه
    یک مقدارِ پیش‌فرضِ معتبر دارد و هرگز واقعاً «الزامی» به‌معنایِ نمایشِ
    خطا نیست)."""

    def _payload(self, **overrides):
        payload = {
            "name": "کالای واحد", "sku": "SKU-UNIT1", "category": self.sub.id,
            "price": "500000", "discount_percent": "0", "stock": "10",
            "status": "active", "icon": "🎁", "description": "",
        }
        payload.update(overrides)
        return payload

    def test_existing_products_default_to_piece_unit(self):
        """مایگریشنِ افزودنِ این فیلد بدونِ RunPython، فقط با defaultِ سطحِ
        اسکیما — کالاهایِ از قبل موجود باید همان لحظه piece شوند."""
        self.assertEqual(self.product.unit, Product.Unit.PIECE)

    def test_create_persists_unit_model_code_and_country(self):
        self.client.post(reverse("dashboard:product-add"), self._payload(
            unit="kg", model_code="MC-100", country_of_origin="آلمان",
        ))
        product = Product.objects.get(sku="SKU-UNIT1")
        self.assertEqual(product.unit, "kg")
        self.assertEqual(product.model_code, "MC-100")
        self.assertEqual(product.country_of_origin, "آلمان")

    def test_blank_model_code_and_country_accepted(self):
        response = self.client.post(reverse("dashboard:product-add"), self._payload(
            model_code="", country_of_origin="",
        ))
        self.assertEqual(response.status_code, 200)
        product = Product.objects.get(sku="SKU-UNIT1")
        self.assertEqual(product.model_code, "")
        self.assertEqual(product.country_of_origin, "")

    def test_missing_unit_falls_back_to_piece_not_an_error(self):
        payload = self._payload()
        payload.pop("unit", None)
        response = self.client.post(reverse("dashboard:product-add"), payload)
        self.assertEqual(response.status_code, 200)
        product = Product.objects.get(sku="SKU-UNIT1")
        self.assertEqual(product.unit, Product.Unit.PIECE)

    def test_invalid_unit_choice_rejected(self):
        response = self.client.post(reverse("dashboard:product-add"), self._payload(unit="not-a-real-unit"))
        self.assertFalse(Product.objects.filter(sku="SKU-UNIT1").exists())
        self.assertEqual(response.status_code, 200)

    def test_edit_prefills_unit_model_code_and_country(self):
        self.product.unit = "liter"
        self.product.model_code = "MC-200"
        self.product.country_of_origin = "ایتالیا"
        self.product.save()
        response = self.client.get(reverse("dashboard:product-edit", args=[self.product.pk]))
        html = response.content.decode()
        self.assertIn('<option value="liter" selected>', html)
        self.assertIn('value="MC-200"', html)
        self.assertIn('value="ایتالیا"', html)

    def test_edit_updates_unit_model_code_and_country(self):
        payload = {
            "name": self.product.name, "sku": self.product.sku, "category": self.sub.id,
            "price": "500000", "discount_percent": "0", "stock": "10", "status": "active",
            "unit": "gram", "model_code": "MC-300", "country_of_origin": "چین",
        }
        self.client.post(reverse("dashboard:product-edit", args=[self.product.pk]), payload)
        self.product.refresh_from_db()
        self.assertEqual(self.product.unit, "gram")
        self.assertEqual(self.product.model_code, "MC-300")
        self.assertEqual(self.product.country_of_origin, "چین")

    def test_validation_error_preserves_unit_and_model_code(self):
        """وقتی اعتبارسنجیِ سرور به دلیلِ خطایِ فیلدِ دیگری شکست می‌خورد،
        مقادیرِ واردشده برایِ واحد/مدل‌کد نباید بی‌سروصدا از دست بروند."""
        response = self.client.post(reverse("dashboard:product-add"), self._payload(
            sku="", unit="kg", model_code="MC-100",
        ))
        html = response.content.decode()
        self.assertIn('<option value="kg" selected>', html)
        self.assertIn('value="MC-100"', html)
        self.assertIn("tab: 'basic',", html)

    def test_keep_open_preserves_unit_and_model_code(self):
        response = self.client.post(reverse("dashboard:product-add"), self._payload(
            sku="SKU-UNIT2", product_type="variable", unit="kg", model_code="MC-100", keep_open="1",
        ))
        html = response.content.decode()
        self.assertIn('<option value="kg" selected>', html)
        self.assertIn('value="MC-100"', html)


class ProductDeleteViewTests(ProductViewsTestCase):
    def test_deletes_product(self):
        response = self.client.post(reverse("dashboard:product-delete", args=[self.product.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Product.objects.filter(pk=self.product.pk).exists())
        trigger = json.loads(response.headers["HX-Trigger"])
        self.assertIn("حذف شد", trigger["toast"]["message"])

    def test_get_not_allowed(self):
        response = self.client.get(reverse("dashboard:product-delete", args=[self.product.pk]))
        self.assertEqual(response.status_code, 405)

    def test_non_staff_cannot_delete(self):
        self.client.logout()
        other = User.objects.create_user(username="09121122099", password="pass12345", is_staff=False)
        self.client.login(username="09121122099", password="pass12345")
        response = self.client.post(reverse("dashboard:product-delete", args=[self.product.pk]))
        self.assertRedirects(response, reverse("catalog:home"), fetch_redirect_response=False)
        self.assertTrue(Product.objects.filter(pk=self.product.pk).exists())


class ProductPreviewViewTests(ProductViewsTestCase):
    def test_draft_product_renders_for_staff(self):
        self.product.status = Product.Status.DRAFT
        self.product.save(update_fields=["status"])
        response = self.client.get(reverse("dashboard:product-preview", args=[self.product.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.product.name)
        self.assertContains(response, "پیش‌نمایشِ مدیریتی")

    def test_preview_banner_shown_even_for_active_product(self):
        """پیش‌نمایش همیشه با بنر مشخص می‌شود — صرف‌نظر از وضعیتِ کالا — تا
        مدیر هرگز آن را با صفحه‌ی واقعیِ فروشگاه اشتباه نگیرد."""
        response = self.client.get(reverse("dashboard:product-preview", args=[self.product.pk]))
        self.assertContains(response, "پیش‌نمایشِ مدیریتی")

    def test_anonymous_denied(self):
        self.client.logout()
        response = self.client.get(reverse("dashboard:product-preview", args=[self.product.pk]))
        self.assertEqual(response.status_code, 302)
        self.assertIn("admin_return=", response.url)

    def test_other_store_product_404s(self):
        other_store = Store.objects.create(name="Other", slug="preview-other-store", status=Store.Status.ACTIVE)
        other_vendor = Vendor.objects.create(store=other_store, name="V", slug="preview-other-vendor")
        other_category = Category.objects.create(store=other_store, name="C", slug="preview-other-cat")
        other_product = Product.objects.create(
            store=other_store, vendor=other_vendor, category=other_category, name="کالای دیگر",
            slug="preview-other-product", sku="SKU-PREVIEW-OTHER", price=Decimal("1000"),
        )
        response = self.client.get(reverse("dashboard:product-preview", args=[other_product.pk]))
        self.assertEqual(response.status_code, 404)


@override_settings(ALLOWED_HOSTS=[HOST, "testserver"])
class ProductCreationWithoutVendorTests(TestCase):
    """A merchant must be able to create a product on day one, before ever
    hearing the word "Vendor" — RastiSi is a single-merchant store builder,
    so the Store itself stands in as the seller (see catalog_admin_service.default_vendor)."""

    def setUp(self):
        self.store = Store.objects.create(name="فروشگاه تازه", slug="fresh-store-pv", status=Store.Status.ACTIVE)
        self.store.admin_subdomain = HOST.split(".")[0]
        self.store.save(update_fields=["admin_subdomain"])
        main = Category.objects.create(store=self.store, name="دیجیتال", slug="main-fresh-pv")
        self.sub = Category.objects.create(store=self.store, name="موبایل", slug="sub-fresh-pv", parent=main)
        self.owner = User.objects.create_user(username="09121122900", password="pass12345", is_staff=True)
        StoreMembership.objects.create(
            store=self.store, user=self.owner, role=StoreMembership.Role.OWNER,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )
        self.client = Client(HTTP_HOST=HOST)
        self.client.login(username="09121122900", password="pass12345")

    def test_product_creation_succeeds_with_no_vendor_ever_created(self):
        self.assertFalse(Vendor.objects.filter(store=self.store).exists())
        response = self.client.post(reverse("dashboard:product-add"), {
            "name": "کالای بدون فروشنده", "sku": "SKU-NOVENDOR1", "category": self.sub.id,
            "price": "500000", "discount_percent": "0", "stock": "10",
            "status": "active", "icon": "🎁", "description": "",
        })
        self.assertEqual(response.status_code, 200)
        product = Product.objects.get(sku="SKU-NOVENDOR1")
        self.assertIsNotNone(product.vendor)
        self.assertEqual(product.vendor.name, self.store.name)
        self.assertEqual(product.vendor.owner_id, self.owner.pk)


@override_settings(ALLOWED_HOSTS=[HOST, "testserver"], MEDIA_ROOT=tempfile.mkdtemp())
class ProductMediaStagingTests(ProductViewsTestCase):
    """تصاویر و ویدیو باید هم‌زمان با ساختِ کالای *جدید* ذخیره شوند — بدونِ
    نیاز به ذخیره‌ی قبلیِ کالا (نگاه کنید به ``_save_staged_product_media``)."""

    @classmethod
    def tearDownClass(cls):
        from django.conf import settings

        shutil.rmtree(settings.MEDIA_ROOT, ignore_errors=True)
        super().tearDownClass()

    def _payload(self, **overrides):
        payload = {
            "name": "کالای با رسانه", "sku": "SKU-MEDIA1", "category": self.sub.id,
            "price": "500000", "discount_percent": "0", "stock": "10",
            "status": "draft", "icon": "🎁", "description": "",
        }
        payload.update(overrides)
        return payload

    def test_new_product_form_does_not_say_save_first(self):
        response = self.client.get(reverse("dashboard:product-add"))
        self.assertNotContains(response, "پس از ذخیره‌ی این کالا می‌توانید")

    def test_images_saved_atomically_with_new_product(self):
        payload = self._payload()
        payload["images"] = [_make_image_file("a.jpg"), _make_image_file("b.jpg")]
        response = self.client.post(reverse("dashboard:product-add"), payload)
        self.assertEqual(response.status_code, 200)
        product = Product.objects.get(sku="SKU-MEDIA1")
        self.assertEqual(product.images.count(), 2)

    def test_cover_index_selects_cover_image(self):
        payload = self._payload()
        payload["images"] = [_make_image_file("a.jpg"), _make_image_file("b.jpg")]
        payload["cover_index"] = "1"
        self.client.post(reverse("dashboard:product-add"), payload)
        product = Product.objects.get(sku="SKU-MEDIA1")
        cover = product.images.get(is_cover=True)
        # بدونِ cover_index، تصویرِ اول (order=0) خودکار کاور می‌شود؛ اینجا
        # صراحتاً دومین تصویر (order=1) به‌عنوانِ کاور انتخاب شده است.
        self.assertEqual(cover.order, 1)

    def test_video_saved_with_new_product(self):
        payload = self._payload(video_url="https://www.youtube.com/watch?v=dQw4w9WgXcQ", video_title="معرفی")
        response = self.client.post(reverse("dashboard:product-add"), payload)
        self.assertEqual(response.status_code, 200)
        product = Product.objects.get(sku="SKU-MEDIA1")
        video = product.videos.get()
        self.assertEqual(video.provider, ProductVideo.Provider.YOUTUBE)
        self.assertEqual(video.title, "معرفی")

    def test_invalid_video_url_blocks_product_creation_with_clear_error(self):
        payload = self._payload(video_url="https://example.com/not-a-video")
        response = self.client.post(reverse("dashboard:product-add"), payload)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "این لینک شناخته‌شده نیست")
        self.assertFalse(Product.objects.filter(sku="SKU-MEDIA1").exists())

    def test_invalid_video_url_preserves_entered_text_fields(self):
        payload = self._payload(video_url="https://example.com/not-a-video")
        response = self.client.post(reverse("dashboard:product-add"), payload)
        self.assertContains(response, "کالای با رسانه")

    def test_invalid_video_rolls_back_already_processed_images(self):
        """اگر ویدیو نامعتبر باشد، کلِ تراکنش (شاملِ تصاویرِ همان درخواست) برمی‌گردد."""
        payload = self._payload(video_url="https://example.com/not-a-video")
        payload["images"] = [_make_image_file("a.jpg")]
        self.client.post(reverse("dashboard:product-add"), payload)
        self.assertFalse(Product.objects.filter(sku="SKU-MEDIA1").exists())
        self.assertEqual(ProductImage.objects.filter(product__sku="SKU-MEDIA1").count(), 0)

    def test_editing_existing_product_ignores_staged_image_fields(self):
        """مسیرِ ویرایش نباید از فیلدهایِ ``images``/``video_url`` استفاده کند —
        کالای موجود از آپلودِ فوریِ همان تب استفاده می‌کند."""
        payload = {
            "name": self.product.name, "sku": self.product.sku, "category": self.sub.id,
            "price": "1000000", "discount_percent": "0", "stock": "5",
            "status": "active", "icon": "📱", "description": "",
            "video_url": "https://example.com/not-a-video",
        }
        response = self.client.post(reverse("dashboard:product-edit", args=[self.product.pk]), payload)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.product.videos.count(), 0)
