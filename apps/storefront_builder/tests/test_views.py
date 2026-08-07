from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.catalog.models import IndustryTemplate, StoreIndustryInstallation
from apps.storefront_builder.models import StorefrontLayoutVersion, StorefrontSection
from apps.storefront_builder.services import layout_service as svc
from apps.stores.authorization import STOREFRONT_LAYOUT_MANAGE
from apps.stores.models import Store, StoreMembership

User = get_user_model()

HOST = "sfb-test.rastisi.localhost"


def _akhlaghi():
    return Store.objects.get(slug="akhlaghi")


class StorefrontBuilderViewsTestCase(TestCase):
    def setUp(self):
        cache.clear()
        self.store = _akhlaghi()
        self.store.admin_subdomain = HOST.split(".")[0]
        self.store.save(update_fields=["admin_subdomain"])
        self.staff = User.objects.create_user(username="sfb_owner", password="pass12345", is_staff=True)
        StoreMembership.objects.create(
            store=self.store, user=self.staff, role=StoreMembership.Role.OWNER,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )
        self.client = Client(HTTP_HOST=HOST)
        self.client.login(username="sfb_owner", password="pass12345")


class EditorAccessTests(StorefrontBuilderViewsTestCase):
    def test_editor_accessible_to_owner(self):
        resp = self.client.get(reverse("dashboard:storefront-builder-editor"))
        self.assertEqual(resp.status_code, 200)

    def test_anonymous_denied(self):
        self.client.logout()
        resp = self.client.get(reverse("dashboard:storefront-builder-editor"))
        self.assertEqual(resp.status_code, 302)
        self.assertNotIn("/admin-portal/login/", resp.url)
        self.assertIn("admin_return=", resp.url)

    def test_content_editor_without_storefront_permission_denied(self):
        from apps.stores.authorization import ROLE_PERMISSIONS
        self.assertNotIn(STOREFRONT_LAYOUT_MANAGE, ROLE_PERMISSIONS[StoreMembership.Role.ANALYST])
        analyst = User.objects.create_user(username="sfb_analyst", password="pass12345", is_staff=True)
        StoreMembership.objects.create(
            store=self.store, user=analyst, role=StoreMembership.Role.ANALYST,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )
        client = Client(HTTP_HOST=HOST)
        client.login(username="sfb_analyst", password="pass12345")
        resp = client.get(reverse("dashboard:storefront-builder-editor"))
        self.assertEqual(resp.status_code, 403)

    def test_editor_creates_bootstrapped_draft_on_first_visit(self):
        self.client.get(reverse("dashboard:storefront-builder-editor"))
        layout = svc.get_or_create_layout(self.store)
        self.assertIsNotNone(layout.draft_version_id)
        self.assertEqual(layout.draft_version.source, StorefrontLayoutVersion.Source.LEGACY_BOOTSTRAP)

    def test_preview_accessible_to_staff_only(self):
        resp = self.client.get(reverse("dashboard:storefront-builder-preview"))
        self.assertEqual(resp.status_code, 200)

    def test_preview_never_shows_another_stores_draft(self):
        other_store = Store.objects.create(
            name="فروشگاه دیگر", slug="sfb-other", admin_subdomain="sfb-other", status=Store.Status.ACTIVE,
        )
        other_staff = User.objects.create_user(username="sfb_other_owner", password="pass12345", is_staff=True)
        StoreMembership.objects.create(
            store=other_store, user=other_staff, role=StoreMembership.Role.OWNER,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )
        draft = svc.get_or_create_draft(self.store)
        StorefrontSection.objects.create(version=draft, section_key="rich_text", order=0, settings={"body_html": "SECRET-STORE-A-TEXT"})

        other_store.admin_subdomain = "sfb-other-host"
        other_store.save(update_fields=["admin_subdomain"])
        other_client = Client(HTTP_HOST="sfb-other-host.rastisi.localhost")
        other_client.login(username="sfb_other_owner", password="pass12345")
        resp = other_client.get(reverse("dashboard:storefront-builder-preview"))
        self.assertNotContains(resp, "SECRET-STORE-A-TEXT")


class SectionActionTests(StorefrontBuilderViewsTestCase):
    def setUp(self):
        super().setUp()
        self.draft = svc.get_or_create_draft(self.store)
        self.draft.sections.all().delete()

    def test_add_section(self):
        resp = self.client.post(reverse("dashboard:storefront-builder-section-add"), {"section_key": "rich_text"})
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(self.draft.sections.filter(section_key="rich_text").exists())

    def test_add_unknown_section_key_rejected(self):
        resp = self.client.post(reverse("dashboard:storefront-builder-section-add"), {"section_key": "<script>alert(1)</script>"})
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(self.draft.sections.count(), 0)

    def test_add_beyond_max_instances_rejected(self):
        StorefrontSection.objects.create(version=self.draft, section_key="hero_banner", order=0)
        self.client.post(reverse("dashboard:storefront-builder-section-add"), {"section_key": "hero_banner"})
        self.assertEqual(self.draft.sections.filter(section_key="hero_banner").count(), 1)

    def test_remove_section(self):
        section = StorefrontSection.objects.create(version=self.draft, section_key="rich_text", order=0)
        self.client.post(reverse("dashboard:storefront-builder-section-remove", args=[section.pk]))
        self.assertFalse(StorefrontSection.objects.filter(pk=section.pk).exists())

    def test_remove_requires_post(self):
        section = StorefrontSection.objects.create(version=self.draft, section_key="rich_text", order=0)
        resp = self.client.get(reverse("dashboard:storefront-builder-section-remove", args=[section.pk]))
        self.assertEqual(resp.status_code, 405)

    def test_toggle_section(self):
        section = StorefrontSection.objects.create(version=self.draft, section_key="rich_text", order=0, is_active=True)
        self.client.post(reverse("dashboard:storefront-builder-section-toggle", args=[section.pk]))
        section.refresh_from_db()
        self.assertFalse(section.is_active)

    def test_collapse_toggle_default_is_false(self):
        section = StorefrontSection.objects.create(version=self.draft, section_key="rich_text", order=0)
        self.assertFalse(section.collapsed_in_editor)

    def test_collapse_toggle_flips_state_and_persists(self):
        section = StorefrontSection.objects.create(version=self.draft, section_key="rich_text", order=0)
        resp = self.client.post(reverse("dashboard:storefront-builder-section-collapse", args=[section.pk]))
        self.assertEqual(resp.status_code, 200)
        section.refresh_from_db()
        self.assertTrue(section.collapsed_in_editor)

        self.client.post(reverse("dashboard:storefront-builder-section-collapse", args=[section.pk]))
        section.refresh_from_db()
        self.assertFalse(section.collapsed_in_editor)

    def test_collapsing_does_not_disable_section(self):
        section = StorefrontSection.objects.create(version=self.draft, section_key="rich_text", order=0, is_active=True)
        self.client.post(reverse("dashboard:storefront-builder-section-collapse", args=[section.pk]))
        section.refresh_from_db()
        self.assertTrue(section.collapsed_in_editor)
        self.assertTrue(section.is_active)

    def test_inactive_section_can_be_collapsed_and_expanded_independently(self):
        section = StorefrontSection.objects.create(version=self.draft, section_key="rich_text", order=0, is_active=False)
        self.client.post(reverse("dashboard:storefront-builder-section-collapse", args=[section.pk]))
        section.refresh_from_db()
        self.assertTrue(section.collapsed_in_editor)
        self.assertFalse(section.is_active)
        self.client.post(reverse("dashboard:storefront-builder-section-collapse", args=[section.pk]))
        section.refresh_from_db()
        self.assertFalse(section.collapsed_in_editor)
        self.assertFalse(section.is_active)

    def test_collapsed_active_section_still_renders_publicly_after_publish(self):
        section = StorefrontSection.objects.create(
            version=self.draft, section_key="rich_text", order=0, is_active=True,
            settings={"body_html": "COLLAPSED-BUT-VISIBLE-MARKER"},
        )
        self.client.post(reverse("dashboard:storefront-builder-section-collapse", args=[section.pk]))
        svc.publish(self.store)
        resp = self.client.get(reverse("catalog:home"))
        self.assertContains(resp, "COLLAPSED-BUT-VISIBLE-MARKER")

    def test_cannot_collapse_another_stores_section(self):
        other_store = Store.objects.create(name="فروشگاه ث", slug="sfb-collapse-cross", admin_subdomain="sfb-collapse-cross")
        other_draft = svc.get_or_create_draft(other_store)
        other_section = StorefrontSection.objects.create(version=other_draft, section_key="rich_text", order=0)

        resp = self.client.post(reverse("dashboard:storefront-builder-section-collapse", args=[other_section.pk]))
        self.assertEqual(resp.status_code, 404)
        other_section.refresh_from_db()
        self.assertFalse(other_section.collapsed_in_editor)

    def test_cannot_collapse_published_section_via_draft_endpoint(self):
        section = StorefrontSection.objects.create(version=self.draft, section_key="rich_text", order=0)
        svc.publish(self.store)
        section.refresh_from_db()
        self.assertEqual(section.version.status, StorefrontLayoutVersion.Status.PUBLISHED)

        resp = self.client.post(reverse("dashboard:storefront-builder-section-collapse", args=[section.pk]))
        self.assertEqual(resp.status_code, 404)
        section.refresh_from_db()
        self.assertFalse(section.collapsed_in_editor)

    def test_duplicate_section(self):
        section = StorefrontSection.objects.create(version=self.draft, section_key="rich_text", order=0, settings={"body_html": "x"})
        self.client.post(reverse("dashboard:storefront-builder-section-duplicate", args=[section.pk]))
        self.assertEqual(self.draft.sections.filter(section_key="rich_text").count(), 2)

    def test_duplicate_non_duplicable_rejected(self):
        section = StorefrontSection.objects.create(version=self.draft, section_key="hero_banner", order=0)
        self.client.post(reverse("dashboard:storefront-builder-section-duplicate", args=[section.pk]))
        self.assertEqual(self.draft.sections.filter(section_key="hero_banner").count(), 1)

    def test_move_up(self):
        a = StorefrontSection.objects.create(version=self.draft, section_key="rich_text", order=0)
        b = StorefrontSection.objects.create(version=self.draft, section_key="image_text", order=1)
        self.client.post(reverse("dashboard:storefront-builder-section-move", args=[b.pk]), {"direction": "up"})
        a.refresh_from_db()
        b.refresh_from_db()
        self.assertLess(b.order, a.order)

    def test_move_up_at_top_noop(self):
        a = StorefrontSection.objects.create(version=self.draft, section_key="rich_text", order=0)
        self.client.post(reverse("dashboard:storefront-builder-section-move", args=[a.pk]), {"direction": "up"})
        a.refresh_from_db()
        self.assertEqual(a.order, 0)

    def test_reorder(self):
        a = StorefrontSection.objects.create(version=self.draft, section_key="rich_text", order=0)
        b = StorefrontSection.objects.create(version=self.draft, section_key="image_text", order=1)
        self.client.post(reverse("dashboard:storefront-builder-section-reorder"), {"section_ids": [str(b.pk), str(a.pk)]})
        a.refresh_from_db()
        b.refresh_from_db()
        self.assertEqual(b.order, 0)
        self.assertEqual(a.order, 1)

    def test_reorder_drops_invalid_ids(self):
        a = StorefrontSection.objects.create(version=self.draft, section_key="rich_text", order=0)
        resp = self.client.post(reverse("dashboard:storefront-builder-section-reorder"), {"section_ids": [str(a.pk), "999999", "not-a-number"]})
        self.assertEqual(resp.status_code, 200)
        a.refresh_from_db()
        self.assertEqual(a.order, 0)

    def test_reorder_rejects_duplicate_ids_no_rows_changed(self):
        """A4: شناسه‌ی تکراری کل عملیات را رد می‌کند — هیچ ردیفی تغییر نمی‌کند."""
        a = StorefrontSection.objects.create(version=self.draft, section_key="rich_text", order=0)
        b = StorefrontSection.objects.create(version=self.draft, section_key="image_text", order=1)
        resp = self.client.post(reverse("dashboard:storefront-builder-section-reorder"), {
            "section_ids": [str(b.pk), str(b.pk), str(a.pk)],
        })
        self.assertEqual(resp.status_code, 200)
        a.refresh_from_db()
        b.refresh_from_db()
        self.assertEqual(a.order, 0)
        self.assertEqual(b.order, 1)

    def test_reorder_mid_operation_failure_rolls_back_completely(self):
        from unittest.mock import patch

        from django.db.models.query import QuerySet

        a = StorefrontSection.objects.create(version=self.draft, section_key="rich_text", order=0)
        b = StorefrontSection.objects.create(version=self.draft, section_key="image_text", order=1)
        c = StorefrontSection.objects.create(version=self.draft, section_key="hero_banner", order=2)
        original_order = {s.pk: s.order for s in [a, b, c]}

        original_update = QuerySet.update
        call_count = {"n": 0}

        def flaky_update(self_qs, *args, **kwargs):
            call_count["n"] += 1
            if call_count["n"] == 2:
                raise RuntimeError("simulated mid-operation failure")
            return original_update(self_qs, *args, **kwargs)

        with patch.object(QuerySet, "update", flaky_update):
            with self.assertRaises(RuntimeError):
                self.client.post(reverse("dashboard:storefront-builder-section-reorder"), {
                    "section_ids": [str(c.pk), str(a.pk), str(b.pk)],
                })

        for section in [a, b, c]:
            section.refresh_from_db()
            self.assertEqual(section.order, original_order[section.pk])

    def test_cannot_reorder_another_stores_sections(self):
        other_store = Store.objects.create(name="فروشگاه ب", slug="sfb-cross", admin_subdomain="sfb-cross")
        other_layout = svc.get_or_create_layout(other_store)
        other_draft = svc.get_or_create_draft(other_store)
        other_section = StorefrontSection.objects.create(version=other_draft, section_key="rich_text", order=0)

        self.client.post(reverse("dashboard:storefront-builder-section-reorder"), {"section_ids": [str(other_section.pk)]})
        other_section.refresh_from_db()
        self.assertEqual(other_section.order, 0)

    def test_cannot_remove_another_stores_section(self):
        other_store = Store.objects.create(name="فروشگاه پ", slug="sfb-cross2", admin_subdomain="sfb-cross2")
        other_draft = svc.get_or_create_draft(other_store)
        other_section = StorefrontSection.objects.create(version=other_draft, section_key="rich_text", order=0)

        resp = self.client.post(reverse("dashboard:storefront-builder-section-remove", args=[other_section.pk]))
        self.assertEqual(resp.status_code, 404)
        self.assertTrue(StorefrontSection.objects.filter(pk=other_section.pk).exists())


class SectionSettingsFormTests(StorefrontBuilderViewsTestCase):
    def setUp(self):
        super().setUp()
        self.draft = svc.get_or_create_draft(self.store)
        self.section = StorefrontSection.objects.create(version=self.draft, section_key="rich_text", order=0)

    def test_settings_form_get(self):
        resp = self.client.get(reverse("dashboard:storefront-builder-section-settings", args=[self.section.pk]))
        self.assertEqual(resp.status_code, 200)

    def test_settings_form_save(self):
        resp = self.client.post(reverse("dashboard:storefront-builder-section-settings", args=[self.section.pk]), {
            "body_html": "<p>متن تست</p>",
        })
        self.assertEqual(resp.status_code, 302)
        self.section.refresh_from_db()
        self.assertIn("متن تست", self.section.settings["body_html"])

    def test_settings_form_sanitizes_script_tag(self):
        self.client.post(reverse("dashboard:storefront-builder-section-settings", args=[self.section.pk]), {
            "body_html": "<p>ok</p><script>alert(1)</script>",
        })
        self.section.refresh_from_db()
        # validate_settings stores raw body_html (sanitization happens at
        # render time via sanitize_rich_text) — assert render-time safety instead.
        from apps.storefront_builder.templatetags.storefront_builder_extras import sanitize_rich_text
        rendered = str(sanitize_rich_text(self.section.settings["body_html"]))
        self.assertNotIn("<script>", rendered)

    def test_settings_form_404_for_type_without_settings(self):
        section = StorefrontSection.objects.create(version=self.draft, section_key="hero_banner", order=1)
        resp = self.client.get(reverse("dashboard:storefront-builder-section-settings", args=[section.pk]))
        self.assertEqual(resp.status_code, 404)

    def test_image_text_rejects_dangerous_url(self):
        section = StorefrontSection.objects.create(version=self.draft, section_key="image_text", order=1)
        resp = self.client.post(reverse("dashboard:storefront-builder-section-settings", args=[section.pk]), {
            "image_url": "javascript:alert(1)", "body_html": "", "title": "",
        })
        self.assertEqual(resp.status_code, 200)  # stays on form with error
        section.refresh_from_db()
        self.assertEqual(section.settings.get("image_url", ""), "")


class ProductSectionSettingsFormTests(StorefrontBuilderViewsTestCase):
    def setUp(self):
        super().setUp()
        self.draft = svc.get_or_create_draft(self.store)
        self.section = StorefrontSection.objects.create(
            version=self.draft, section_key="product_section", order=0,
            settings={
                "data_source": "newest", "source_id": None, "product_ids": [],
                "item_limit": 8, "display_mode": "carousel", "show_view_all": True,
                "title": "", "subtitle": "",
            },
        )

    def test_settings_form_get(self):
        resp = self.client.get(reverse("dashboard:storefront-builder-section-settings", args=[self.section.pk]))
        self.assertEqual(resp.status_code, 200)

    def test_save_collection_source(self):
        from apps.catalog.services import collection_service
        collection = collection_service.create_collection(self.store, name="کالکشن تنظیمات")
        resp = self.client.post(reverse("dashboard:storefront-builder-section-settings", args=[self.section.pk]), {
            "data_source": "collection", "source_id": str(collection.pk), "item_limit": "8",
            "display_mode": "carousel", "title": "وایر شمع",
        })
        self.assertEqual(resp.status_code, 302)
        self.section.refresh_from_db()
        self.assertEqual(self.section.settings["data_source"], "collection")
        self.assertEqual(self.section.settings["source_id"], collection.pk)
        self.assertEqual(self.section.settings["title"], "وایر شمع")

    def test_save_manual_products(self):
        from decimal import Decimal

        from apps.catalog.models import Category, Product, Vendor

        vendor = Vendor.objects.create(store=self.store, name="فروشنده تنظیمات", slug="v-ps-settings")
        category = Category.objects.create(store=self.store, name="دسته تنظیمات", slug="c-ps-settings")
        product = Product.objects.create(
            store=self.store, vendor=vendor, category=category, name="کالای تنظیمات",
            slug="ps-settings-p1", sku="SKU-PS-SETTINGS-1", price=Decimal("10000"), status=Product.Status.ACTIVE,
        )
        resp = self.client.post(reverse("dashboard:storefront-builder-section-settings", args=[self.section.pk]), {
            "data_source": "manual", "product_ids": [str(product.pk)], "item_limit": "8",
            "display_mode": "grid", "title": "دستی",
        })
        self.assertEqual(resp.status_code, 302)
        self.section.refresh_from_db()
        self.assertEqual(self.section.settings["product_ids"], [product.pk])
        self.assertEqual(self.section.settings["display_mode"], "grid")

    def test_manual_without_products_shows_error(self):
        resp = self.client.post(reverse("dashboard:storefront-builder-section-settings", args=[self.section.pk]), {
            "data_source": "manual", "item_limit": "8", "display_mode": "carousel",
        })
        self.assertEqual(resp.status_code, 200)
        self.section.refresh_from_db()
        self.assertEqual(self.section.settings["data_source"], "newest")  # unchanged

    def test_collection_without_source_id_shows_error(self):
        resp = self.client.post(reverse("dashboard:storefront-builder-section-settings", args=[self.section.pk]), {
            "data_source": "collection", "item_limit": "8", "display_mode": "carousel",
        })
        self.assertEqual(resp.status_code, 200)
        self.section.refresh_from_db()
        self.assertEqual(self.section.settings["data_source"], "newest")  # unchanged

    def test_cross_store_collection_rejected_by_data_service_not_crash(self):
        """انتخابِ یک کالکشنِ متعلق به فروشگاهِ دیگر (مثلاً با دستکاریِ
        فرم) نباید کرش کند — در سطحِ section_registry هر source_id مثبت
        پذیرفته می‌شود (بدونِ چکِ مالکیت)؛ مالکیت در section_data_service
        در زمانِ رندر چک می‌شود، نه اینجا."""
        other_store = Store.objects.create(
            name="فروشگاه دیگر تنظیمات", slug="ps-settings-other-store", admin_subdomain="ps-settings-other-store",
        )
        from apps.catalog.services import collection_service
        other_collection = collection_service.create_collection(other_store, name="کالکشن فروشگاه دیگر")
        resp = self.client.post(reverse("dashboard:storefront-builder-section-settings", args=[self.section.pk]), {
            "data_source": "collection", "source_id": str(other_collection.pk), "item_limit": "8",
            "display_mode": "carousel",
        })
        self.assertEqual(resp.status_code, 302)
        self.section.refresh_from_db()
        self.assertEqual(self.section.settings["source_id"], other_collection.pk)

    def test_duplicate_then_independent_edit_does_not_affect_original(self):
        """سناریوی «دو نمونه‌ی مستقلِ product_section» (Playwright B) از
        مسیر تکرار هم: تکرار، تنظیماتِ فعلی را کپی می‌کند؛ اما ویرایشِ
        بعدیِ نمونه‌ی دوم نباید نمونه‌ی اول را تغییر دهد (دو رکورد کاملاً
        مستقل در دیتابیس‌اند، فقط JSON اولیه‌شان یکسان بوده)."""
        from apps.catalog.services import collection_service

        first_collection = collection_service.create_collection(self.store, name="کالکشن اول تکرار")
        self.client.post(reverse("dashboard:storefront-builder-section-settings", args=[self.section.pk]), {
            "data_source": "collection", "source_id": str(first_collection.pk), "item_limit": "8",
            "display_mode": "carousel", "title": "اول",
        })
        self.client.post(reverse("dashboard:storefront-builder-section-duplicate", args=[self.section.pk]))
        duplicate = self.draft.sections.filter(section_key="product_section").exclude(pk=self.section.pk).get()

        second_collection = collection_service.create_collection(self.store, name="کالکشن دوم تکرار")
        self.client.post(reverse("dashboard:storefront-builder-section-settings", args=[duplicate.pk]), {
            "data_source": "collection", "source_id": str(second_collection.pk), "item_limit": "8",
            "display_mode": "carousel", "title": "دوم",
        })

        self.section.refresh_from_db()
        duplicate.refresh_from_db()
        self.assertEqual(self.section.settings["source_id"], first_collection.pk)
        self.assertEqual(self.section.settings["title"], "اول")
        self.assertEqual(duplicate.settings["source_id"], second_collection.pk)
        self.assertEqual(duplicate.settings["title"], "دوم")

    def test_deactivating_section_does_not_affect_collection(self):
        """سناریوی D (Playwright): غیرفعال‌سازیِ Section نباید خودِ
        کالکشن را تحت تأثیر قرار دهد — is_active فقط روی StorefrontSection
        است، MerchantCollection.is_active کاملاً جداست."""
        from apps.catalog.services import collection_service

        collection = collection_service.create_collection(self.store, name="کالکشن غیرفعال‌سازی سکشن")
        self.section.settings = {
            "data_source": "collection", "source_id": collection.pk, "product_ids": [],
            "item_limit": 8, "display_mode": "carousel", "show_view_all": True, "title": "", "subtitle": "",
        }
        self.section.save(update_fields=["settings"])

        self.client.post(reverse("dashboard:storefront-builder-section-toggle", args=[self.section.pk]))
        self.section.refresh_from_db()
        collection.refresh_from_db()
        self.assertFalse(self.section.is_active)
        self.assertTrue(collection.is_active)


class ProductSectionProductSearchTests(StorefrontBuilderViewsTestCase):
    def setUp(self):
        super().setUp()
        self.draft = svc.get_or_create_draft(self.store)
        self.section = StorefrontSection.objects.create(version=self.draft, section_key="product_section", order=0)

    def test_empty_query_returns_no_results(self):
        resp = self.client.get(reverse("dashboard:storefront-builder-section-product-search", args=[self.section.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertNotIn(b"pp-result-row", resp.content)

    def test_matching_query_returns_result(self):
        from decimal import Decimal

        from apps.catalog.models import Category, Product, Vendor

        vendor = Vendor.objects.create(store=self.store, name="فروشنده جست‌وجو", slug="v-ps-search")
        category = Category.objects.create(store=self.store, name="دسته جست‌وجو", slug="c-ps-search")
        Product.objects.create(
            store=self.store, vendor=vendor, category=category, name="کالای جست‌وجوی خاص",
            slug="ps-search-p1", sku="SKU-PS-SEARCH-1", price=Decimal("10000"), status=Product.Status.ACTIVE,
        )
        resp = self.client.get(
            reverse("dashboard:storefront-builder-section-product-search", args=[self.section.pk]), {"q": "جست‌وجوی خاص"},
        )
        self.assertContains(resp, "کالای جست‌وجوی خاص")

    def test_other_store_section_pk_rejected(self):
        other_store = Store.objects.create(
            name="فروشگاه دیگر جست‌وجو", slug="ps-search-other-store", admin_subdomain="ps-search-other-store",
        )
        other_draft = svc.get_or_create_draft(other_store)
        other_section = StorefrontSection.objects.create(version=other_draft, section_key="product_section", order=0)
        resp = self.client.get(
            reverse("dashboard:storefront-builder-section-product-search", args=[other_section.pk]), {"q": "test"},
        )
        self.assertEqual(resp.status_code, 404)


class PublishDiscardRestoreViewTests(StorefrontBuilderViewsTestCase):
    def test_publish_redirects_and_sets_flag(self):
        svc.get_or_create_draft(self.store)
        resp = self.client.post(reverse("dashboard:storefront-builder-publish"))
        self.assertRedirects(resp, reverse("dashboard:storefront-builder-editor"))
        layout = svc.get_or_create_layout(self.store)
        self.assertTrue(layout.uses_visual_storefront_layout)

    def test_discard_redirects(self):
        svc.get_or_create_draft(self.store)
        resp = self.client.post(reverse("dashboard:storefront-builder-discard"))
        # fetch_redirect_response=False: the editor page itself lazily
        # re-creates a draft (get_or_create_draft) — following the redirect
        # here would create a fresh draft as a side effect and defeat the
        # "draft was actually discarded" assertion below.
        self.assertRedirects(resp, reverse("dashboard:storefront-builder-editor"), fetch_redirect_response=False)
        layout = svc.get_or_create_layout(self.store)
        self.assertIsNone(layout.draft_version_id)

    def test_history_lists_versions(self):
        svc.get_or_create_draft(self.store)
        svc.publish(self.store)
        resp = self.client.get(reverse("dashboard:storefront-builder-history"))
        self.assertEqual(resp.status_code, 200)

    def test_restore_creates_draft_not_publish(self):
        svc.get_or_create_draft(self.store)
        v1 = svc.publish(self.store)
        svc.get_or_create_draft(self.store)
        svc.publish(self.store)

        resp = self.client.post(reverse("dashboard:storefront-builder-restore", args=[v1.pk]))
        self.assertRedirects(resp, reverse("dashboard:storefront-builder-editor"))
        layout = svc.get_or_create_layout(self.store)
        self.assertNotEqual(layout.published_version_id, v1.pk)
        self.assertIsNotNone(layout.draft_version_id)

    def test_restore_cross_store_returns_404(self):
        other_store = Store.objects.create(name="فروشگاه ت", slug="sfb-restore-x", admin_subdomain="sfb-restore-x")
        svc.get_or_create_draft(other_store)
        other_version = svc.publish(other_store)

        resp = self.client.post(reverse("dashboard:storefront-builder-restore", args=[other_version.pk]))
        self.assertEqual(resp.status_code, 404)


class ApplyIndustryLayoutViewTests(StorefrontBuilderViewsTestCase):
    def _install_template(self, slug="sfb-view-industry", section_keys=None):
        template = IndustryTemplate.objects.create(
            slug=slug, name="صنف تست ویو",
            default_section_keys=section_keys if section_keys is not None else ["hero_banner", "trust_features"],
        )
        StoreIndustryInstallation.objects.create(
            store=self.store, industry_template=template, installed_version=template.version,
        )
        return template

    def test_404_when_store_has_no_industry_installation(self):
        resp = self.client.post(reverse("dashboard:storefront-builder-apply-industry-layout"))
        self.assertEqual(resp.status_code, 404)

    def test_applies_directly_when_never_published(self):
        self._install_template()
        resp = self.client.post(reverse("dashboard:storefront-builder-apply-industry-layout"))
        self.assertRedirects(resp, reverse("dashboard:storefront-builder-editor"))
        layout = svc.get_or_create_layout(self.store)
        self.assertEqual(layout.draft_version.source, StorefrontLayoutVersion.Source.INDUSTRY_TEMPLATE)
        self.assertEqual(
            list(layout.draft_version.sections.order_by("order").values_list("section_key", flat=True)),
            ["hero_banner", "trust_features"],
        )

    def test_rejected_without_confirm_when_already_published(self):
        svc.get_or_create_draft(self.store)
        svc.publish(self.store)
        self._install_template()
        resp = self.client.post(reverse("dashboard:storefront-builder-apply-industry-layout"))
        self.assertRedirects(resp, reverse("dashboard:storefront-builder-editor"))
        layout = svc.get_or_create_layout(self.store)
        self.assertNotEqual(layout.draft_version.source, StorefrontLayoutVersion.Source.INDUSTRY_TEMPLATE)

    def test_applied_with_explicit_confirm_when_already_published(self):
        svc.get_or_create_draft(self.store)
        published = svc.publish(self.store)
        self._install_template()
        resp = self.client.post(
            reverse("dashboard:storefront-builder-apply-industry-layout"), {"confirm": "1"},
        )
        self.assertRedirects(resp, reverse("dashboard:storefront-builder-editor"))
        layout = svc.get_or_create_layout(self.store)
        self.assertEqual(layout.draft_version.source, StorefrontLayoutVersion.Source.INDUSTRY_TEMPLATE)
        self.assertEqual(layout.published_version_id, published.pk)


class HeaderFooterEditorTests(StorefrontBuilderViewsTestCase):
    def test_header_editor_get(self):
        resp = self.client.get(reverse("dashboard:storefront-builder-header"))
        self.assertEqual(resp.status_code, 200)

    def test_header_editor_saves_config(self):
        resp = self.client.post(reverse("dashboard:storefront-builder-header"), {
            "show_search": "on", "show_cart": "on", "announcement_text": "پیام تست",
        })
        self.assertEqual(resp.status_code, 302)
        draft = svc.get_or_create_draft(self.store)
        self.assertTrue(draft.header_config["show_search"])
        self.assertFalse(draft.header_config["show_account"])
        self.assertTrue(draft.header_config["show_cart"])
        self.assertEqual(draft.header_config["announcement_text"], "پیام تست")

    def test_header_editor_rejects_hidden_cart(self):
        """A2: هدر بدون امکان دسترسی به سبد خرید نباید ذخیره شود — هیچ مسیر
        جایگزینی برای رسیدن مشتری به سبد خرید در معماری فعلی وجود ندارد."""
        draft_before = svc.get_or_create_draft(self.store)
        original_config = dict(draft_before.header_config or {})
        resp = self.client.post(reverse("dashboard:storefront-builder-header"), {
            "show_search": "on",
        })
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "سبد خرید")
        draft_after = svc.get_or_create_draft(self.store)
        self.assertEqual(draft_after.header_config, original_config)

    def test_footer_editor_get(self):
        resp = self.client.get(reverse("dashboard:storefront-builder-footer"))
        self.assertEqual(resp.status_code, 200)

    def test_footer_editor_saves_config(self):
        resp = self.client.post(reverse("dashboard:storefront-builder-footer"), {
            "show_about": "on", "show_contact": "on",
        })
        self.assertEqual(resp.status_code, 302)
        draft = svc.get_or_create_draft(self.store)
        self.assertTrue(draft.footer_config["show_about"])
        self.assertFalse(draft.footer_config["show_social"])

    def test_footer_editor_rejects_all_blocks_disabled(self):
        """A2: فوتر کاملاً خالی (همه بخش‌ها غیرفعال) نباید ذخیره شود."""
        draft_before = svc.get_or_create_draft(self.store)
        original_config = dict(draft_before.footer_config or {})
        resp = self.client.post(reverse("dashboard:storefront-builder-footer"), {})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "فوتر")
        draft_after = svc.get_or_create_draft(self.store)
        self.assertEqual(draft_after.footer_config, original_config)

    def test_footer_editor_accepts_single_active_block(self):
        resp = self.client.post(reverse("dashboard:storefront-builder-footer"), {
            "show_copyright": "on",
        })
        self.assertEqual(resp.status_code, 302)
        draft = svc.get_or_create_draft(self.store)
        self.assertTrue(draft.footer_config["show_copyright"])
        self.assertFalse(draft.footer_config["show_about"])
