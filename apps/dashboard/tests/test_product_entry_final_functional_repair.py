"""رگرسیونِ رفعِ باگ‌هایِ تأییدشده‌ی «تعمیرِ نهاییِ کارکردیِ صفحه‌ی افزودن/ویرایشِ
کالا» — نگاه کنید به docs/reports/PRODUCT_ENTRY_FINAL_FUNCTIONAL_REPAIR_AUDIT.md
برایِ ریشه‌یِ هر باگ. این فایل فقط بخش‌هایِ قابلِ‌تست از طریقِ Django test
client را پوشش می‌دهد؛ رفتارهایِ کاملاً سمتِ مرورگر (کلیکِ dropzoneِ تصویر،
ماونتِ CKEditor) با Playwrightِ واقعی تأیید شده‌اند، نه این‌جا."""

import json
from decimal import Decimal

from django.test import override_settings
from django.urls import reverse

from apps.catalog.models import Product, ProductOption, ProductOptionValue, ProductVariant, ProductVideo
from apps.catalog.services.variant_engine_service import add_option_value, add_product_option, generate_variants
from apps.dashboard.tests.test_product_entry_ui_cleanup import HOST, ProductEntryUiCleanupTestCase


def _toast_message(response) -> str:
    return json.loads(response.headers["HX-Trigger"])["toast"]["message"]


@override_settings(ALLOWED_HOSTS=[HOST, "testserver"])
class SaveCategoryGroupPreservationTests(ProductEntryUiCleanupTestCase):
    """باگِ ۱آ: انتخابِ «گروهِ اصلی» با هر بارِ شکستِ اعتبارسنجی خالی می‌شد."""

    def _base_payload(self, **overrides):
        payload = {
            "current_tab": "category", "name": "کالای تست ذخیره", "sku": "SAVE-REPAIR-SKU1", "brand": "",
            "quick_brand_name": "", "unit": "piece", "model_code": "", "tags": "", "description": "",
            "category_group": str(self.main.pk), "category": "", "second_group": "", "quick_collection_name": "",
            "country_of_origin": "", "product_type": "simple", "price": "150000", "discount_percent": "0",
            "stock": "0", "tax_class": "", "barcode": "", "weight_grams": "", "requires_shipping": "on",
            "seo_title": "", "slug": "", "status": "active", "seo_description": "", "visibility": "public",
            "publish_at": "",
        }
        payload.update(overrides)
        return payload

    def _new_draft_pk(self):
        response = self.client.get(reverse("dashboard:product-add"), follow=True)
        return response.context["product"].pk

    def test_group_selection_survives_failed_save_when_leaf_not_chosen(self):
        draft_pk = self._new_draft_pk()
        response = self.client.post(
            reverse("dashboard:product-edit", args=[draft_pk]), self._base_payload(),
        )
        # سلکتِ «گروهِ اصلی» با Alpine (``x-model="selectedGroupId"``، مقداردهیِ
        # اولیه از رویِ همین کانتکست) کار می‌کند، نه با ``selected`` استاتیکِ
        # سمتِ سرور — پس خودِ کانتکستِ رندرشده را بررسی می‌کنیم.
        self.assertEqual(response.context["selected_category_group_id"], self.main.pk)
        self.assertIn("category", response.context["form"].errors)

    def test_leaf_only_needs_to_be_picked_on_retry(self):
        draft_pk = self._new_draft_pk()
        self.client.post(reverse("dashboard:product-edit", args=[draft_pk]), self._base_payload())
        retry = self.client.post(
            reverse("dashboard:product-edit", args=[draft_pk]),
            self._base_payload(category=str(self.sub.pk)),
        )
        product = Product.objects.get(pk=draft_pk)
        self.assertEqual(product.category_id, self.sub.pk)
        self.assertFalse(product.is_draft_placeholder)
        self.assertEqual(retry.status_code, 200)


@override_settings(ALLOWED_HOSTS=[HOST, "testserver"])
class DraftSaveOptionalPriceTests(ProductEntryUiCleanupTestCase):
    """باگِ ۱ب: «ذخیره‌ی پیش‌نویس» با قیمتِ خالی همیشه شکست می‌خورد."""

    def _payload(self, *, status, price):
        return {
            "current_tab": "price", "name": "پیش‌نویسِ بدونِ قیمت", "sku": "DRAFT-NOPRICE-SKU1", "brand": "",
            "quick_brand_name": "", "unit": "piece", "model_code": "", "tags": "", "description": "",
            "category_group": str(self.main.pk), "category": str(self.sub.pk), "second_group": "",
            "quick_collection_name": "", "country_of_origin": "", "product_type": "simple", "price": price,
            "discount_percent": "0", "stock": "0", "tax_class": "", "barcode": "", "weight_grams": "",
            "requires_shipping": "on", "seo_title": "", "slug": "", "status": status, "seo_description": "",
            "visibility": "public", "publish_at": "",
        }

    def _new_draft_pk(self):
        response = self.client.get(reverse("dashboard:product-add"), follow=True)
        return response.context["product"].pk

    def test_draft_save_succeeds_with_blank_price(self):
        draft_pk = self._new_draft_pk()
        self.client.post(
            reverse("dashboard:product-edit", args=[draft_pk]), self._payload(status="draft", price=""),
        )
        product = Product.objects.get(pk=draft_pk)
        self.assertEqual(product.name, "پیش‌نویسِ بدونِ قیمت")
        self.assertEqual(product.price, 0)
        self.assertEqual(product.status, Product.Status.DRAFT)
        self.assertFalse(product.is_draft_placeholder)

    def test_active_status_still_requires_price(self):
        draft_pk = self._new_draft_pk()
        response = self.client.post(
            reverse("dashboard:product-edit", args=[draft_pk]), self._payload(status="active", price=""),
        )
        product = Product.objects.get(pk=draft_pk)
        self.assertEqual(product.name, "")
        self.assertTrue(product.is_draft_placeholder)
        self.assertIn("price", response.context["form"].errors)

    def test_valid_price_still_enforced_for_draft(self):
        draft_pk = self._new_draft_pk()
        response = self.client.post(
            reverse("dashboard:product-edit", args=[draft_pk]), self._payload(status="draft", price="0"),
        )
        self.assertIn("price", response.context["form"].errors)


@override_settings(ALLOWED_HOSTS=[HOST, "testserver"])
class BulkVariantActionEndpointTests(ProductEntryUiCleanupTestCase):
    """سمتِ سرور: مطمئن می‌شویم اندپوینت‌هایِ عملِ گروهی فقط رویِ شناسه‌هایِ
    ارسالی اثر می‌گذارند. باگِ واقعیِ ``$el`` سمتِ مرورگر بود (کلیکِ واقعی هیچ
    ``variant_ids``ای نمی‌فرستاد)؛ Playwright آن را جداگانه تأیید کرده است."""

    def setUp(self):
        super().setUp()
        self.axis = add_product_option(self.product, label="رنگ")
        for label in ["قرمز", "آبی", "سبز"]:
            add_option_value(self.axis, label)
        generate_variants(self.product)
        self.variants = list(self.product.variants.order_by("pk"))

    def test_bulk_activate_only_affects_selected(self):
        selected = [self.variants[0].pk, self.variants[1].pk]
        self.client.post(
            reverse("dashboard:product-variants-bulk-activate", args=[self.product.pk]),
            {"variant_ids": selected, "activate": "0"},
        )
        self.variants[0].refresh_from_db()
        self.variants[1].refresh_from_db()
        self.variants[2].refresh_from_db()
        self.assertFalse(self.variants[0].is_active)
        self.assertFalse(self.variants[1].is_active)
        self.assertTrue(self.variants[2].is_active)

    def test_bulk_stock_only_affects_selected(self):
        selected = [self.variants[0].pk, self.variants[2].pk]
        response = self.client.post(
            reverse("dashboard:product-variants-bulk-stock", args=[self.product.pk]),
            {"variant_ids": selected, "stock": "25"},
        )
        self.assertEqual(response.status_code, 200)
        self.variants[0].refresh_from_db()
        self.variants[1].refresh_from_db()
        self.variants[2].refresh_from_db()
        self.assertEqual(self.variants[0].stock, 25)
        self.assertEqual(self.variants[1].stock, 0)
        self.assertEqual(self.variants[2].stock, 25)

    def test_bulk_stock_rejects_negative(self):
        response = self.client.post(
            reverse("dashboard:product-variants-bulk-stock", args=[self.product.pk]),
            {"variant_ids": [self.variants[0].pk], "stock": "-5"},
        )
        self.assertEqual(response.status_code, 200)
        self.variants[0].refresh_from_db()
        self.assertEqual(self.variants[0].stock, 0)

    def test_bulk_stock_requires_selection(self):
        response = self.client.post(
            reverse("dashboard:product-variants-bulk-stock", args=[self.product.pk]),
            {"variant_ids": [], "stock": "10"},
        )
        self.assertIn("هیچ تنوعی انتخاب نشده است", _toast_message(response))

    def test_bulk_sales_limit_only_affects_selected(self):
        selected = [self.variants[1].pk]
        self.client.post(
            reverse("dashboard:product-variants-bulk-sales-limit", args=[self.product.pk]),
            {"variant_ids": selected, "sales_limit_min": "1", "sales_limit_max": "5"},
        )
        self.variants[0].refresh_from_db()
        self.variants[1].refresh_from_db()
        self.assertIsNone(self.variants[0].sales_limit)
        self.assertEqual(self.variants[1].sales_limit_min, 1)
        self.assertEqual(self.variants[1].sales_limit, 5)


@override_settings(ALLOWED_HOSTS=[HOST, "testserver"])
class ProductVideoTests(ProductEntryUiCleanupTestCase):
    """باگِ ۵: نامِ فیلدِ POST با آنچه ویو می‌خواند مطابقت نداشت، پس افزودنِ
    ویدیو برایِ هیچ سرویسی هرگز کار نمی‌کرد."""

    def test_youtube_video_add_with_actual_field_names(self):
        response = self.client.post(
            reverse("dashboard:product-video-add", args=[self.product.pk]),
            {"__edit_video_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ", "__edit_video_title": "معرفی"},
        )
        self.assertEqual(response.status_code, 200)
        video = self.product.videos.get()
        self.assertEqual(video.provider, ProductVideo.Provider.YOUTUBE)
        self.assertEqual(video.embed_url, "https://www.youtube.com/embed/dQw4w9WgXcQ")

    def test_aparat_video_add(self):
        self.client.post(
            reverse("dashboard:product-video-add", args=[self.product.pk]),
            {"__edit_video_url": "https://www.aparat.com/v/abc123", "__edit_video_title": ""},
        )
        video = self.product.videos.get()
        self.assertEqual(video.provider, ProductVideo.Provider.APARAT)

    def test_instagram_reel_video_add(self):
        self.client.post(
            reverse("dashboard:product-video-add", args=[self.product.pk]),
            {"__edit_video_url": "https://www.instagram.com/reel/CzXyZ12345/", "__edit_video_title": ""},
        )
        video = self.product.videos.get()
        self.assertEqual(video.provider, ProductVideo.Provider.INSTAGRAM)
        self.assertIsNone(video.embed_url)
        self.assertEqual(video.instagram_permalink, "https://www.instagram.com/reel/CzXyZ12345/")

    def test_instagram_profile_url_rejected(self):
        response = self.client.post(
            reverse("dashboard:product-video-add", args=[self.product.pk]),
            {"__edit_video_url": "https://www.instagram.com/someaccount/", "__edit_video_title": ""},
        )
        self.assertFalse(self.product.videos.exists())
        self.assertIn("شناخته‌شده نیست", _toast_message(response))

    def test_unsupported_host_rejected(self):
        response = self.client.post(
            reverse("dashboard:product-video-add", args=[self.product.pk]),
            {"__edit_video_url": "https://example.com/watch", "__edit_video_title": ""},
        )
        self.assertFalse(self.product.videos.exists())
        self.assertIn("شناخته‌شده نیست", _toast_message(response))
