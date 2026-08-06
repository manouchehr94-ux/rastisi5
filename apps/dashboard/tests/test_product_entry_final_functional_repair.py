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

    def test_bulk_activate_requires_selection(self):
        response = self.client.post(
            reverse("dashboard:product-variants-bulk-activate", args=[self.product.pk]),
            {"variant_ids": [], "activate": "0"},
        )
        self.assertIn("هیچ تنوعی انتخاب نشده است", _toast_message(response))
        for variant in self.variants:
            variant.refresh_from_db()
            self.assertTrue(variant.is_active)

    def test_bulk_activate_rejects_variant_from_a_different_product(self):
        """امنیت: شناسه‌ی تنوعِ یک کالای دیگر (حتی در همان فروشگاه) هرگز
        نباید توسطِ اندپوینتِ عملِ گروهیِ *این* کالا اثر بگیرد — نگاه کنید به
        ``_get_scoped_product``/``product.variants.filter(pk__in=...)``."""
        other_product = Product.objects.create(
            store=self.store, vendor=self.vendor, category=self.sub, name="کالای دیگر",
            slug="uicleanup-other-product", sku="UICLEAN-OTHER-SKU1", price=Decimal("50000"),
            product_type=Product.ProductType.VARIABLE,
        )
        other_axis = add_product_option(other_product, label="سایز")
        add_option_value(other_axis, "بزرگ")
        generate_variants(other_product)
        other_variant = other_product.variants.get()
        self.assertTrue(other_variant.is_active)

        response = self.client.post(
            reverse("dashboard:product-variants-bulk-activate", args=[self.product.pk]),
            {"variant_ids": [other_variant.pk], "activate": "0"},
        )
        self.assertEqual(response.status_code, 200)
        other_variant.refresh_from_db()
        self.assertTrue(other_variant.is_active, "تنوعِ یک کالای دیگر نباید تغییر کند")

    def test_bulk_delete_requires_selection(self):
        response = self.client.post(
            reverse("dashboard:product-variants-bulk-delete", args=[self.product.pk]),
            {"delete_variant_ids": []},
        )
        self.assertIn("هیچ تنوعی انتخاب نشده است", _toast_message(response))
        self.assertEqual(self.product.variants.count(), 3)

    def test_bulk_update_no_longer_reads_is_active(self):
        """رگرسیون: حذفِ چک‌باکسِ وضعیت از قالب نباید با کلیکِ «ذخیره‌ی
        تغییرات» باعثِ غیرفعال‌شدنِ خاموشِ همه‌ی تنوع‌ها شود — این ویو دیگر
        اصلاً فیلدِ ``variant_*_is_active`` را نمی‌خواند."""
        payload = {"variant_ids": [v.pk for v in self.variants]}
        for variant in self.variants:
            prefix = f"variant_{variant.pk}_"
            payload[f"{prefix}sku"] = variant.sku
            payload[f"{prefix}stock"] = "0"
        response = self.client.post(
            reverse("dashboard:product-variants-bulk-update", args=[self.product.pk]), payload,
        )
        self.assertEqual(response.status_code, 200)
        for variant in self.variants:
            variant.refresh_from_db()
            self.assertTrue(variant.is_active, "بدونِ فیلدِ is_active در payload، وضعیت نباید تغییر کند")

    def test_status_pill_has_no_checkbox_in_table_or_card_view(self):
        """رگرسیون: «Explicit status — no checkbox» — نه در نمایِ جدول و نه
        در نمایِ کارت، هیچ ``<input type="checkbox" name="variant_*_is_active">``ی
        نباید باقی مانده باشد؛ تنها یک پیلِ فقط‌خواندنی مجاز است."""
        response = self.client.get(reverse("dashboard:product-edit", args=[self.product.pk]))
        content = response.content.decode()
        self.assertNotIn("_is_active", content)
        self.assertIn('class="pill on"', content)

    def test_confirmation_dialog_text_present_for_all_three_bulk_actions(self):
        response = self.client.get(reverse("dashboard:product-edit", args=[self.product.pk]))
        content = response.content.decode()
        self.assertIn("از فعال‌سازی تنوع‌های انتخاب‌شده مطمئن هستید؟", content)
        self.assertIn("از غیرفعال‌سازی تنوع‌های انتخاب‌شده مطمئن هستید؟", content)
        self.assertIn("از حذف تنوع‌های انتخاب‌شده مطمئن هستید؟ این عملیات قابل بازگشت نیست.", content)
        self.assertNotIn('hx-confirm="تنوع‌های انتخاب‌شده حذف شوند', content)


@override_settings(ALLOWED_HOSTS=[HOST, "testserver"])
class ProductVideoTests(ProductEntryUiCleanupTestCase):
    """باگِ ۵: نامِ فیلدِ POST با آنچه ویو می‌خواند مطابقت نداشت، پس افزودنِ
    ویدیو برایِ هیچ سرویسی هرگز کار نمی‌کرد."""

    def test_youtube_video_add_with_actual_field_names(self):
        response = self.client.post(
            reverse("dashboard:product-video-add", args=[self.product.pk]),
            {"video_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ", "video_title": "معرفی"},
        )
        self.assertEqual(response.status_code, 200)
        video = self.product.videos.get()
        self.assertEqual(video.provider, ProductVideo.Provider.YOUTUBE)
        self.assertEqual(video.embed_url, "https://www.youtube.com/embed/dQw4w9WgXcQ")

    def test_aparat_video_add(self):
        self.client.post(
            reverse("dashboard:product-video-add", args=[self.product.pk]),
            {"video_url": "https://www.aparat.com/v/abc123", "video_title": ""},
        )
        video = self.product.videos.get()
        self.assertEqual(video.provider, ProductVideo.Provider.APARAT)

    def test_instagram_reel_video_add(self):
        self.client.post(
            reverse("dashboard:product-video-add", args=[self.product.pk]),
            {"video_url": "https://www.instagram.com/reel/CzXyZ12345/", "video_title": ""},
        )
        video = self.product.videos.get()
        self.assertEqual(video.provider, ProductVideo.Provider.INSTAGRAM)
        self.assertIsNone(video.embed_url)
        self.assertEqual(video.instagram_permalink, "https://www.instagram.com/reel/CzXyZ12345/")

    def test_instagram_profile_url_rejected(self):
        response = self.client.post(
            reverse("dashboard:product-video-add", args=[self.product.pk]),
            {"video_url": "https://www.instagram.com/someaccount/", "video_title": ""},
        )
        self.assertFalse(self.product.videos.exists())
        self.assertIn("شناخته‌شده نیست", _toast_message(response))

    def test_unsupported_host_rejected(self):
        response = self.client.post(
            reverse("dashboard:product-video-add", args=[self.product.pk]),
            {"video_url": "https://example.com/watch", "video_title": ""},
        )
        self.assertFalse(self.product.videos.exists())
        self.assertIn("شناخته‌شده نیست", _toast_message(response))

    def test_javascript_scheme_url_rejected(self):
        response = self.client.post(
            reverse("dashboard:product-video-add", args=[self.product.pk]),
            {"video_url": "javascript:alert(1)//youtube.com/watch?v=dQw4w9WgXcQ", "video_title": ""},
        )
        self.assertFalse(self.product.videos.exists())
        self.assertIn("شناخته‌شده نیست", _toast_message(response))

    def test_homepage_url_rejected(self):
        response = self.client.post(
            reverse("dashboard:product-video-add", args=[self.product.pk]),
            {"video_url": "https://www.youtube.com/", "video_title": ""},
        )
        self.assertFalse(self.product.videos.exists())
        self.assertIn("شناخته‌شده نیست", _toast_message(response))

    def test_success_response_triggers_video_added_event(self):
        response = self.client.post(
            reverse("dashboard:product-video-add", args=[self.product.pk]),
            {"video_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ", "video_title": ""},
        )
        trigger = json.loads(response.headers["HX-Trigger"])
        self.assertTrue(trigger.get("video-added"))

    def test_rejected_response_does_not_trigger_video_added_event(self):
        response = self.client.post(
            reverse("dashboard:product-video-add", args=[self.product.pk]),
            {"video_url": "https://example.com/watch", "video_title": ""},
        )
        trigger = json.loads(response.headers["HX-Trigger"])
        self.assertNotIn("video-added", trigger)
        self.assertIn("video-error", trigger)


@override_settings(ALLOWED_HOSTS=[HOST, "testserver"])
class ProductVideoRefreshPersistenceTests(ProductEntryUiCleanupTestCase):
    """باگِ اصلیِ ویدیو: ذخیره‌سازی در دیتابیس درست کار می‌کرد، اما
    ``_product_form_extra_context`` هرگز متغیرِ ``videos`` را برای رندرِ
    GET/رفرشِ کاملِ صفحه تعریف نمی‌کرد — پس ویدیویِ ذخیره‌شده، بعد از هر
    Refresh، انگار هرگز اضافه نشده بود."""

    def test_video_appears_in_full_page_get_after_add(self):
        self.client.post(
            reverse("dashboard:product-video-add", args=[self.product.pk]),
            {"video_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ", "video_title": "معرفی"},
        )
        response = self.client.get(reverse("dashboard:product-edit", args=[self.product.pk]))
        self.assertEqual(list(response.context["videos"]), list(self.product.videos.all()))
        self.assertContains(response, "https://www.youtube.com/embed/dQw4w9WgXcQ")

    def test_video_still_listed_after_second_full_page_load(self):
        self.client.post(
            reverse("dashboard:product-video-add", args=[self.product.pk]),
            {"video_url": "https://www.aparat.com/v/abc123", "video_title": ""},
        )
        first = self.client.get(reverse("dashboard:product-edit", args=[self.product.pk]))
        second = self.client.get(reverse("dashboard:product-edit", args=[self.product.pk]))
        self.assertEqual(len(first.context["videos"]), 1)
        self.assertEqual(len(second.context["videos"]), 1)

    def test_video_delete_persists_after_refresh(self):
        self.client.post(
            reverse("dashboard:product-video-add", args=[self.product.pk]),
            {"video_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ", "video_title": ""},
        )
        video = self.product.videos.get()
        self.client.post(reverse("dashboard:product-video-delete", args=[self.product.pk, video.pk]))
        response = self.client.get(reverse("dashboard:product-edit", args=[self.product.pk]))
        self.assertEqual(len(response.context["videos"]), 0)

    def test_product_with_no_video_yet_still_has_empty_videos_context(self):
        response = self.client.get(reverse("dashboard:product-edit", args=[self.product.pk]))
        self.assertIn("videos", response.context)
        self.assertEqual(len(response.context["videos"]), 0)


@override_settings(ALLOWED_HOSTS=[HOST, "testserver"])
class ProductVideoCanonicalFieldContractTests(ProductEntryUiCleanupTestCase):
    """نامِ فیلد باید فقط ``video_url``/``video_title`` باشد — نه نامِ
    موازیِ قدیمیِ ``__edit_video_url``/``url``."""

    def test_legacy_dunder_field_name_no_longer_recognized(self):
        self.client.post(
            reverse("dashboard:product-video-add", args=[self.product.pk]),
            {"__edit_video_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ", "__edit_video_title": ""},
        )
        self.assertFalse(self.product.videos.exists())

    def test_bare_url_field_name_no_longer_recognized(self):
        self.client.post(
            reverse("dashboard:product-video-add", args=[self.product.pk]),
            {"url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ", "title": ""},
        )
        self.assertFalse(self.product.videos.exists())
