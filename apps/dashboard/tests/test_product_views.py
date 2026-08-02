import json
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.catalog.models import Brand, Category, Product, Vendor
from apps.stores.models import Store, StoreMembership

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
        """The product's own category <select> (#id_category) must only offer
        leaf categories — a top-level group may still legitimately appear
        elsewhere on the page, in the quick-add-category panel's group picker."""
        response = self.client.get(reverse("dashboard:product-add"))
        content = response.content.decode()
        category_select = content[content.index('id="id_category"'):content.index("</select>", content.index('id="id_category"'))]
        self.assertNotIn(f'value="{self.main.id}"', category_select)
        self.assertIn(f'value="{self.sub.id}"', category_select)

    def test_blank_icon_defaults(self):
        self.client.post(reverse("dashboard:product-add"), self._payload(icon=""))
        product = Product.objects.get(sku="SKU-NEW1")
        self.assertEqual(product.icon, "🛍️")


class ProductWizardTests(ProductViewsTestCase):
    """فرمِ افزودنِ کالا سه بخشِ اصلی دارد (Product Entry rebuild: اطلاعات
    پایه / قیمت و ویژگی‌ها / سئو و انتشار)، همه در یک <form> واحد (بدون از
    دست رفتنِ داده بین تب‌ها)، با اعتبارسنجیِ سمتِ سرور که کاربر را دقیقاً
    به تبِ دارایِ خطا هدایت می‌کند."""

    def _payload(self, **overrides):
        payload = {
            "name": "کالای ویزارد", "sku": "SKU-WIZ1", "category": self.sub.id,
            "price": "500000", "discount_percent": "0", "stock": "10",
            "status": "active", "icon": "🎁", "description": "",
        }
        payload.update(overrides)
        return payload

    def test_form_renders_all_three_tabs_in_one_form(self):
        response = self.client.get(reverse("dashboard:product-add"))
        content = response.content.decode()
        self.assertEqual(content.count("<form"), 1)  # یک فرمِ واحد، نه فرم‌های جداگانه‌ی هر تب
        for ref in ["tabBasic", "tabPrice", "tabSeo"]:
            self.assertIn(f'x-ref="{ref}"', content)

    def test_tab_labels_present(self):
        response = self.client.get(reverse("dashboard:product-add"))
        self.assertContains(response, "اطلاعات پایه")
        self.assertContains(response, "قیمت و ویژگی‌ها")
        self.assertContains(response, "سئو و انتشار")

    def test_basic_info_tab_contains_category_and_brand(self):
        """دسته‌بندی و برند در تبِ «اطلاعات پایه» هستند."""
        response = self.client.get(reverse("dashboard:product-add"))
        content = response.content.decode()
        tab_start = content.index('x-ref="tabBasic"')
        tab_end = content.index('x-ref="tabPrice"')
        tab_html = content[tab_start:tab_end]
        self.assertIn('name="category"', tab_html)
        self.assertIn('name="brand"', tab_html)

    def test_price_tab_contains_attributes_and_variant_type(self):
        """ویژگی‌ها و نوعِ کالا در همان تبِ «قیمت و ویژگی‌ها» هستند."""
        response = self.client.get(reverse("dashboard:product-add"))
        content = response.content.decode()
        tab_start = content.index('x-ref="tabPrice"')
        tab_end = content.index('x-ref="tabSeo"')
        tab_html = content[tab_start:tab_end]
        self.assertIn('name="product_type"', tab_html)
        self.assertIn("productAttributeFields", tab_html)

    def test_error_step_routes_to_basic_tab_when_category_missing(self):
        response = self.client.post(reverse("dashboard:product-add"), self._payload(category=""))
        self.assertEqual(response.status_code, 200)
        self.assertIn("tab: 'basic',", response.content.decode())

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

    def test_media_management_link_opens_via_htmx_not_full_navigation(self):
        """لینکِ «مدیریتِ تصاویرِ این کالا» در مرحله‌ی رسانه‌ی ویزارد باید با htmx باز شود،
        نه با ناوبریِ کاملِ صفحه — چون صفحه‌ی مودالِ تصاویر بدونِ لایه‌ی اصلی رندر می‌شود."""
        images_url = reverse("dashboard:product-images", args=[self.product.pk])
        response = self.client.get(reverse("dashboard:product-edit", args=[self.product.pk]))
        self.assertContains(response, f'hx-get="{images_url}"')
        self.assertContains(response, 'hx-target="#admin-modal-content"')

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
