from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.catalog.models import IndustryTemplate, StoreIndustryInstallation
from apps.storefront_builder.models import StorefrontLayoutVersion, StorefrontPage, StorefrontSection
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

    def test_editor_add_section_library_is_grouped_by_business_category(self):
        """چکپوینتِ ۱۰: کتابخانه‌ی «افزودن بخش جدید» باید در گروه‌های
        کسب‌وکاری آکاردئونی نمایش داده شود، نه یک فهرستِ تخت."""
        resp = self.client.get(reverse("dashboard:storefront-builder-editor"))
        for category in ("محصولات", "تصاویر و تبلیغات", "کشف و خرید", "محتوا", "ساختار"):
            self.assertContains(resp, category)
        self.assertContains(resp, "sfb-add-section-category")
        # نوارِ اعلانِ section نباید در کتابخانه ظاهر شود (چکپوینتِ ۹)
        self.assertNotContains(resp, 'section_key": "announcement_bar"')

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

    def test_preview_exposes_section_ids_for_direct_selection(self):
        """چکپوینتِ Direct Visual Editing — برخلافِ صفحه‌ی عمومی، Preview
        (فقط staff همین فروشگاه) باید data-section-id داشته باشد تا کلیک
        روی یک section در Preview بتواند تنظیماتِ همان section را باز کند."""
        resp = self.client.get(reverse("dashboard:storefront-builder-preview"))
        self.assertContains(resp, "data-section-id")
        self.assertContains(resp, "data-section-key")

    def test_preview_exposes_inline_canvas_toolbar(self):
        """Phase 8 P0-6 — ابزارِ شناورِ روی خودِ section در Canvas؛ فقط
        در Preview (نه صفحه‌ی عمومی)، دقیقاً کنارِ data-section-id."""
        resp = self.client.get(reverse("dashboard:storefront-builder-preview"))
        self.assertContains(resp, "sfb-rsec-toolbar")
        self.assertContains(resp, 'data-cmd="duplicate"')
        self.assertContains(resp, 'data-cmd="remove"')

    # Phase 4: هدر/فوتر همان دکوریتورهای مشترکِ ``@staff_required`` +
    # ``@permission_required(STOREFRONT_LAYOUT_MANAGE)`` را (که در بالا
    # برای editor/preview اثبات شده) استفاده می‌کنند — این دو تست فقط
    # همان مکانیزم را صراحتاً روی دو Endpoint این فاز هم اثبات می‌کنند.
    def test_header_editor_anonymous_denied(self):
        self.client.logout()
        resp = self.client.get(reverse("dashboard:storefront-builder-header"))
        self.assertEqual(resp.status_code, 302)

    def test_footer_editor_anonymous_denied(self):
        self.client.logout()
        resp = self.client.get(reverse("dashboard:storefront-builder-footer"))
        self.assertEqual(resp.status_code, 302)

    def test_header_editor_without_storefront_permission_denied(self):
        analyst = User.objects.create_user(username="sfb_hf_analyst", password="pass12345", is_staff=True)
        StoreMembership.objects.create(
            store=self.store, user=analyst, role=StoreMembership.Role.ANALYST,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )
        client = Client(HTTP_HOST=HOST)
        client.login(username="sfb_hf_analyst", password="pass12345")
        resp = client.get(reverse("dashboard:storefront-builder-header"))
        self.assertEqual(resp.status_code, 403)

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


class FullscreenEditorTests(StorefrontBuilderViewsTestCase):
    """مشکلِ ۴ (تصمیمِ مالک): دکمه‌ی «تمام‌صفحه» کنارِ کنترل‌های
    دسکتاپ/تبلت/موبایل — بدونِ Renderer/Tab/پنجره‌ی جدید؛ همان
    ``#sfbPreviewFrame``ی مشترکِ Preview/Storefront عمومی."""

    def test_fullscreen_button_present_next_to_device_controls(self):
        resp = self.client.get(reverse("dashboard:storefront-builder-editor"))
        self.assertEqual(resp.status_code, 200)
        html = resp.content.decode("utf-8")
        device_toggle_pos = html.index("sfb-device-toggle")
        fullscreen_btn_pos = html.index("sfb-fullscreen-btn")
        # دکمه‌ی تمام‌صفحه باید همان نزدیکیِ کنترل‌هایِ دستگاه باشد، نه
        # جایی کاملاً نامرتبط در صفحه.
        self.assertLess(fullscreen_btn_pos - device_toggle_pos, 2000)
        self.assertContains(resp, "تمام‌صفحه")

    def test_fullscreen_exit_toolbar_present_with_save_status(self):
        resp = self.client.get(reverse("dashboard:storefront-builder-editor"))
        self.assertContains(resp, "sfb-fullscreen-float")
        self.assertContains(resp, "خروج از تمام‌صفحه")
        self.assertContains(resp, "sfb-fullscreen-save-status")

    def test_escape_key_handler_wired_to_exit_fullscreen(self):
        resp = self.client.get(reverse("dashboard:storefront-builder-editor"))
        self.assertContains(resp, "@keydown.escape.window")
        self.assertContains(resp, "fullscreen = false")

    def test_fullscreen_reuses_the_same_shared_preview_iframe(self):
        """هیچ Renderer/iframe/URLِ جداگانه‌ای برایِ تمام‌صفحه ساخته
        نشود — همان ``sfbPreviewFrame``ی مشترکِ Preview/Storefront عمومی
        باید زیرِ حالتِ تمام‌صفحه هم استفاده شود."""
        resp = self.client.get(reverse("dashboard:storefront-builder-editor"))
        html = resp.content.decode("utf-8")
        self.assertEqual(html.count('id="sfbPreviewFrame"'), 1)
        self.assertContains(resp, reverse("dashboard:storefront-builder-preview"))

    def test_fullscreen_state_is_a_pure_css_toggle_not_a_new_route(self):
        """طبقِ الزامِ صریح: بازشدنِ Tab/پنجره‌ی جدید مجاز نیست — دکمه‌ی
        تمام‌صفحه فقط یک متغیرِ Alpineِ محلی را تغییر می‌دهد (``fullscreen``)،
        نه هیچ ناوبری/hx-get/window.open ای."""
        resp = self.client.get(reverse("dashboard:storefront-builder-editor"))
        html = resp.content.decode("utf-8")
        btn_start = html.index("sfb-fullscreen-btn")
        btn_tag = html[max(0, btn_start - 300):btn_start + 200]
        self.assertIn("fullscreen = true", btn_tag)
        self.assertNotIn("window.open", btn_tag)
        self.assertNotIn("target=\"_blank\"", btn_tag)


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
        StorefrontSection.objects.create(version=self.draft, section_key="announcement_bar", order=0)
        self.client.post(reverse("dashboard:storefront-builder-section-add"), {"section_key": "announcement_bar"})
        self.assertEqual(self.draft.sections.filter(section_key="announcement_bar").count(), 1)

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

    def test_duplicate_copies_responsive_settings_and_stays_independent(self):
        section = StorefrontSection.objects.create(
            version=self.draft, section_key="category_grid", order=0,
            settings={
                "responsive": {
                    "hide_on_desktop": False, "hide_on_tablet": False, "hide_on_mobile": True,
                    "desktop_columns": 3, "tablet_columns": 2, "mobile_columns": 1,
                },
            },
        )
        self.client.post(reverse("dashboard:storefront-builder-section-duplicate", args=[section.pk]))
        duplicate = self.draft.sections.filter(section_key="category_grid").exclude(pk=section.pk).get()
        self.assertEqual(duplicate.settings["responsive"], section.settings["responsive"])

        self.client.post(reverse("dashboard:storefront-builder-section-settings", args=[duplicate.pk]), {
            "show_on_desktop": "on", "show_on_tablet": "on", "show_on_mobile": "on",
            "desktop_columns": "6", "tablet_columns": "3", "mobile_columns": "2",
        })
        section.refresh_from_db()
        duplicate.refresh_from_db()
        self.assertTrue(section.settings["responsive"]["hide_on_mobile"])
        self.assertEqual(section.settings["responsive"]["desktop_columns"], 3)
        self.assertFalse(duplicate.settings["responsive"]["hide_on_mobile"])
        self.assertEqual(duplicate.settings["responsive"]["desktop_columns"], 6)

    def test_duplicate_non_duplicable_rejected(self):
        section = StorefrontSection.objects.create(version=self.draft, section_key="announcement_bar", order=0)
        self.client.post(reverse("dashboard:storefront-builder-section-duplicate", args=[section.pk]))
        self.assertEqual(self.draft.sections.filter(section_key="announcement_bar").count(), 1)

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


class LockSectionTests(StorefrontBuilderViewsTestCase):
    """Phase 1 (spec §37 — Lock): «It cannot be moved / It cannot be
    deleted»."""

    def setUp(self):
        super().setUp()
        self.draft = svc.get_or_create_draft(self.store)
        self.draft.sections.all().delete()

    def test_lock_toggle_flips_flag(self):
        section = StorefrontSection.objects.create(version=self.draft, section_key="rich_text", order=0)
        self.assertFalse(section.is_locked)
        self.client.post(reverse("dashboard:storefront-builder-section-lock", args=[section.pk]))
        section.refresh_from_db()
        self.assertTrue(section.is_locked)
        self.client.post(reverse("dashboard:storefront-builder-section-lock", args=[section.pk]))
        section.refresh_from_db()
        self.assertFalse(section.is_locked)

    def test_locked_section_cannot_be_removed(self):
        section = StorefrontSection.objects.create(
            version=self.draft, section_key="rich_text", order=0, is_locked=True,
        )
        self.client.post(reverse("dashboard:storefront-builder-section-remove", args=[section.pk]))
        self.assertTrue(StorefrontSection.objects.filter(pk=section.pk).exists())

    def test_unlocked_section_still_removable(self):
        section = StorefrontSection.objects.create(version=self.draft, section_key="rich_text", order=0)
        self.client.post(reverse("dashboard:storefront-builder-section-remove", args=[section.pk]))
        self.assertFalse(StorefrontSection.objects.filter(pk=section.pk).exists())

    def test_locked_section_cannot_be_moved(self):
        a = StorefrontSection.objects.create(
            version=self.draft, section_key="rich_text", order=0, is_locked=True,
        )
        b = StorefrontSection.objects.create(version=self.draft, section_key="image_text", order=1)
        self.client.post(reverse("dashboard:storefront-builder-section-move", args=[a.pk]), {"direction": "down"})
        a.refresh_from_db()
        b.refresh_from_db()
        self.assertEqual(a.order, 0)
        self.assertEqual(b.order, 1)

    def test_locked_section_still_duplicable(self):
        """قفل فقط جابه‌جایی/حذفِ *همان* section را منع می‌کند — تکرار یک
        نمونه‌ی منطقاً جدید می‌سازد (spec §37 صراحتاً فقط move/delete را
        نام می‌برد)."""
        section = StorefrontSection.objects.create(
            version=self.draft, section_key="rich_text", order=0, is_locked=True,
        )
        self.client.post(reverse("dashboard:storefront-builder-section-duplicate", args=[section.pk]))
        self.assertEqual(self.draft.sections.filter(section_key="rich_text").count(), 2)


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

    def test_settings_form_shows_only_responsive_block_for_type_without_own_fields(self):
        """از فازِ D به بعد، ``hero_banner`` (که هیچ فیلدِ اختصاصیِ خودش
        را ندارد) دیگر ۴۰۴ نمی‌دهد — چون همه‌ی انواع اکنون حداقل بلوکِ
        «تنظیماتِ نمایش در دستگاه‌ها» را دارند."""
        section = StorefrontSection.objects.create(version=self.draft, section_key="hero_banner", order=1)
        resp = self.client.get(reverse("dashboard:storefront-builder-section-settings", args=[section.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "تنظیمات نمایش در دستگاه‌ها")

    def test_image_text_rejects_dangerous_url(self):
        section = StorefrontSection.objects.create(version=self.draft, section_key="image_text", order=1)
        resp = self.client.post(reverse("dashboard:storefront-builder-section-settings", args=[section.pk]), {
            "image_url": "javascript:alert(1)", "body_html": "", "title": "",
        })
        self.assertEqual(resp.status_code, 200)  # stays on form with error
        section.refresh_from_db()
        self.assertEqual(section.settings.get("image_url", ""), "")


class CategoryGridBrandCarouselSettingsFormTests(StorefrontBuilderViewsTestCase):
    def setUp(self):
        super().setUp()
        self.draft = svc.get_or_create_draft(self.store)

    def test_category_grid_settings_form_get_shows_picker(self):
        from apps.catalog.models import Category

        Category.objects.create(store=self.store, name="دسته انتخابی", slug="cat-picker", is_active=True)
        section = StorefrontSection.objects.create(version=self.draft, section_key="category_grid", order=1)
        resp = self.client.get(reverse("dashboard:storefront-builder-section-settings", args=[section.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "دسته انتخابی")

    def test_category_grid_settings_form_saves_selection_and_order(self):
        from apps.catalog.models import Category

        cat_a = Category.objects.create(store=self.store, name="آ", slug="cg-a", is_active=True)
        cat_b = Category.objects.create(store=self.store, name="ب", slug="cg-b", is_active=True)
        section = StorefrontSection.objects.create(version=self.draft, section_key="category_grid", order=1)
        resp = self.client.post(reverse("dashboard:storefront-builder-section-settings", args=[section.pk]), {
            "title": "دسته‌های ویژه", "display_mode": "carousel",
            "category_ids": [str(cat_b.pk), str(cat_a.pk)],
        })
        self.assertEqual(resp.status_code, 302)
        section.refresh_from_db()
        self.assertEqual(section.settings["title"], "دسته‌های ویژه")
        self.assertEqual(section.settings["display_mode"], "carousel")
        self.assertEqual(section.settings["category_ids"], [cat_b.pk, cat_a.pk])

    def test_brand_carousel_settings_form_saves_selection(self):
        from apps.catalog.models import Brand

        brand = Brand.objects.create(store=self.store, name="برند تست", slug="bc-a", is_active=True)
        section = StorefrontSection.objects.create(version=self.draft, section_key="brand_carousel", order=1)
        resp = self.client.post(reverse("dashboard:storefront-builder-section-settings", args=[section.pk]), {
            "title": "", "display_mode": "grid", "brand_ids": [str(brand.pk)],
            "destination_type": "none",
        })
        self.assertEqual(resp.status_code, 302)
        section.refresh_from_db()
        self.assertEqual(section.settings["brand_ids"], [brand.pk])

    def test_brand_carousel_view_all_requires_no_specific_error_when_destination_none(self):
        """نمایشِ لینکِ «مشاهده همه» بدونِ مقصد اجازه دارد ذخیره شود — فقط
        در رندر هیچ لینکی نشان داده نمی‌شود (نه یک خطایِ اعتبارسنجیِ
        گیج‌کننده روی این چک‌باکس)."""
        section = StorefrontSection.objects.create(version=self.draft, section_key="brand_carousel", order=1)
        resp = self.client.post(reverse("dashboard:storefront-builder-section-settings", args=[section.pk]), {
            "title": "", "display_mode": "grid", "show_view_all": "on", "brand_ids": [],
            "destination_type": "none",
        })
        self.assertEqual(resp.status_code, 302)
        section.refresh_from_db()
        self.assertTrue(section.settings["show_view_all"])
        self.assertEqual(section.settings["destination"]["destination_type"], "none")


class ResponsiveSettingsFormTests(StorefrontBuilderViewsTestCase):
    def setUp(self):
        super().setUp()
        self.draft = svc.get_or_create_draft(self.store)

    def test_default_new_section_visible_everywhere(self):
        section = StorefrontSection.objects.create(version=self.draft, section_key="hero_banner", order=0)
        self.assertEqual(section.settings, {})
        resp = self.client.get(reverse("dashboard:storefront-builder-section-settings", args=[section.pk]))
        self.assertContains(resp, 'name="show_on_desktop" checked')
        self.assertContains(resp, 'name="show_on_tablet" checked')
        self.assertContains(resp, 'name="show_on_mobile" checked')

    def test_unchecking_mobile_hides_only_mobile(self):
        section = StorefrontSection.objects.create(version=self.draft, section_key="hero_banner", order=0)
        resp = self.client.post(reverse("dashboard:storefront-builder-section-settings", args=[section.pk]), {
            "show_on_desktop": "on", "show_on_tablet": "on",
        })
        self.assertEqual(resp.status_code, 302)
        section.refresh_from_db()
        self.assertEqual(section.settings["responsive"], {
            "hide_on_desktop": False, "hide_on_tablet": False, "hide_on_mobile": True,
        })

    def test_hide_all_three_combination(self):
        section = StorefrontSection.objects.create(version=self.draft, section_key="hero_banner", order=0)
        resp = self.client.post(reverse("dashboard:storefront-builder-section-settings", args=[section.pk]), {})
        self.assertEqual(resp.status_code, 302)
        section.refresh_from_db()
        self.assertEqual(section.settings["responsive"], {
            "hide_on_desktop": True, "hide_on_tablet": True, "hide_on_mobile": True,
        })

    def test_column_controls_absent_for_non_column_aware_type(self):
        section = StorefrontSection.objects.create(version=self.draft, section_key="hero_banner", order=0)
        resp = self.client.get(reverse("dashboard:storefront-builder-section-settings", args=[section.pk]))
        self.assertNotContains(resp, "تعداد ستون‌ها")

    def test_column_controls_present_for_visually_functional_type(self):
        """``product_section``/``multi_banner`` — تنها دو نوعی که الان
        چیدمانِ پارامتریِ واقعی دارند (Phase 3: ``multi_banner`` به
        ``COLUMN_VISUAL_SECTION_KEYS`` منتقل شد، نگاه کنید به
        ``STOREFRONT_BUILDER_V2_PHASE_3_AUDIT.md``) — باید کنترلِ «تعداد
        ستون‌ها» را در فرم ببینند."""
        for section_key in ("product_section", "multi_banner"):
            section = StorefrontSection.objects.create(version=self.draft, section_key=section_key, order=0)
            resp = self.client.get(reverse("dashboard:storefront-builder-section-settings", args=[section.pk]))
            self.assertContains(resp, "تعداد ستون‌ها", msg_prefix=f"section_key={section_key}")

    def test_column_controls_absent_for_column_aware_but_visually_static_types(self):
        """فیکسِ فازِ D — تستِ دستیِ کاربر روی Brand Carousel نشان داد
        تغییرِ تعدادِ ستون هیچ اثرِ بصری‌ای ندارد؛ این سه نوع همچنان
        در ``COLUMN_AWARE_SECTION_KEYS`` (قراردادِ ذخیره‌سازیِ عمومی)
        هستند اما دیگر نباید کنترلِ گمراه‌کننده را در UI نشان دهند.
        (``multi_banner`` از این فهرست در Phase 3 خارج شد — چیدمانِ
        گریدش دیگر واقعاً پارامتری است، نگاه کنید به تستِ بالا.)"""
        for section_key in ("category_grid", "promo_cards", "brand_carousel"):
            section = StorefrontSection.objects.create(version=self.draft, section_key=section_key, order=0)
            resp = self.client.get(reverse("dashboard:storefront-builder-section-settings", args=[section.pk]))
            self.assertNotContains(resp, "تعداد ستون‌ها", msg_prefix=f"section_key={section_key}")

    def test_visibility_controls_still_present_for_column_aware_but_visually_static_types(self):
        """نمایش/عدمِ‌نمایش per-device باید برایِ همه‌ی انواع (از جمله این
        چهار نوع) همچنان کار کند — فقط کنترلِ ستون حذف شده، نه ریسپانسیوِ
        نمایش."""
        for section_key in ("category_grid", "multi_banner", "promo_cards", "brand_carousel"):
            section = StorefrontSection.objects.create(version=self.draft, section_key=section_key, order=0)
            resp = self.client.get(reverse("dashboard:storefront-builder-section-settings", args=[section.pk]))
            self.assertContains(resp, "نمایش در:", msg_prefix=f"section_key={section_key}")
            self.assertContains(resp, "show_on_mobile", msg_prefix=f"section_key={section_key}")

    def test_motion_controls_present_for_motion_aware_type(self):
        section = StorefrontSection.objects.create(version=self.draft, section_key="hero_banner", order=0)
        resp = self.client.get(reverse("dashboard:storefront-builder-section-settings", args=[section.pk]))
        self.assertContains(resp, 'name="motion_style"')

    def test_motion_controls_absent_for_non_motion_aware_type(self):
        section = StorefrontSection.objects.create(version=self.draft, section_key="rich_text", order=0)
        resp = self.client.get(reverse("dashboard:storefront-builder-section-settings", args=[section.pk]))
        self.assertNotContains(resp, 'name="motion_style"')

    def test_motion_style_saved_for_motion_aware_type(self):
        section = StorefrontSection.objects.create(version=self.draft, section_key="hero_banner", order=0)
        resp = self.client.post(reverse("dashboard:storefront-builder-section-settings", args=[section.pk]), {
            "motion_style": "hover_lift",
        })
        self.assertEqual(resp.status_code, 302)
        section.refresh_from_db()
        self.assertEqual(section.settings["motion"], {"style": "hover_lift"})

    def test_motion_style_ignored_for_non_motion_aware_type(self):
        """پستِ ``motion_style`` برایِ نوعی که موتور از آن پشتیبانی نمی‌کند
        (مثلاً یک درخواستِ دستکاری‌شده) نباید چیزی در settings بنویسد —
        فقط ``MOTION_AWARE_SECTION_KEYS`` این کلید را از POST می‌خواند."""
        section = StorefrontSection.objects.create(version=self.draft, section_key="rich_text", order=0)
        resp = self.client.post(reverse("dashboard:storefront-builder-section-settings", args=[section.pk]), {
            "body_html": "متن", "motion_style": "fade",
        })
        self.assertEqual(resp.status_code, 302)
        section.refresh_from_db()
        self.assertNotIn("motion", section.settings)

    def test_column_values_still_saved_for_category_grid_despite_no_ui(self):
        """قراردادِ ذخیره‌سازی عمداً عمومی می‌ماند (بخشِ ۵ مشخصاتِ فیکس) —
        حتی بدونِ UI، اگر مقدار پست شود همچنان اعتبارسنجی/ذخیره می‌شود؛
        این تفاوتِ «UI کنترل نمی‌کند» با «سرور اصلاً پشتیبانی نمی‌کند» را
        روشن می‌کند."""
        section = StorefrontSection.objects.create(version=self.draft, section_key="category_grid", order=0)
        resp = self.client.post(reverse("dashboard:storefront-builder-section-settings", args=[section.pk]), {
            "show_on_desktop": "on", "show_on_tablet": "on", "show_on_mobile": "on",
            "desktop_columns": "3", "tablet_columns": "2", "mobile_columns": "1",
        })
        self.assertEqual(resp.status_code, 302)
        section.refresh_from_db()
        self.assertEqual(section.settings["responsive"]["desktop_columns"], 3)
        self.assertEqual(section.settings["responsive"]["tablet_columns"], 2)
        self.assertEqual(section.settings["responsive"]["mobile_columns"], 1)

    def test_category_grid_save_without_column_fields_uses_defaults(self):
        """چون UI دیگر این فیلدها را برایِ category_grid پست نمی‌کند،
        ذخیره‌ی معمولی (بدونِ desktop_columns/…) باید بدونِ خطا به
        پیش‌فرض‌ها برگردد — نه کرش کند."""
        section = StorefrontSection.objects.create(version=self.draft, section_key="category_grid", order=0)
        resp = self.client.post(reverse("dashboard:storefront-builder-section-settings", args=[section.pk]), {
            "show_on_desktop": "on", "show_on_tablet": "on", "show_on_mobile": "on",
        })
        self.assertEqual(resp.status_code, 302)
        section.refresh_from_db()
        self.assertEqual(section.settings["responsive"]["desktop_columns"], 4)
        self.assertEqual(section.settings["responsive"]["tablet_columns"], 3)
        self.assertEqual(section.settings["responsive"]["mobile_columns"], 2)

    def test_invalid_column_value_shows_error_and_does_not_save(self):
        section = StorefrontSection.objects.create(version=self.draft, section_key="category_grid", order=0)
        resp = self.client.post(reverse("dashboard:storefront-builder-section-settings", args=[section.pk]), {
            "show_on_desktop": "on", "show_on_tablet": "on", "show_on_mobile": "on",
            "desktop_columns": "99",
        })
        self.assertEqual(resp.status_code, 200)
        section.refresh_from_db()
        self.assertEqual(section.settings, {})

    def test_is_active_independent_of_responsive_visibility(self):
        section = StorefrontSection.objects.create(version=self.draft, section_key="hero_banner", order=0, is_active=True)
        self.client.post(reverse("dashboard:storefront-builder-section-settings", args=[section.pk]), {})
        section.refresh_from_db()
        self.assertTrue(section.settings["responsive"]["hide_on_mobile"])
        self.assertTrue(section.is_active)

    def test_collapsed_in_editor_independent_of_responsive_visibility(self):
        section = StorefrontSection.objects.create(
            version=self.draft, section_key="hero_banner", order=0, collapsed_in_editor=True,
        )
        self.client.post(reverse("dashboard:storefront-builder-section-settings", args=[section.pk]), {
            "show_on_desktop": "on", "show_on_tablet": "on", "show_on_mobile": "on",
        })
        section.refresh_from_db()
        self.assertFalse(section.settings["responsive"]["hide_on_mobile"])
        self.assertTrue(section.collapsed_in_editor)

    def test_cross_store_section_cannot_be_edited(self):
        other_store = Store.objects.create(
            name="فروشگاه دیگر ریسپانسیو", slug="resp-other-store", admin_subdomain="resp-other-store",
        )
        other_draft = svc.get_or_create_draft(other_store)
        other_section = StorefrontSection.objects.create(version=other_draft, section_key="hero_banner", order=0)
        resp = self.client.post(reverse("dashboard:storefront-builder-section-settings", args=[other_section.pk]), {})
        self.assertEqual(resp.status_code, 404)

    def test_published_section_cannot_be_mutated_through_draft_settings_endpoint(self):
        """فرمِ تنظیمات فقط section‌هایِ نسخه‌ی Draft را برمی‌گرداند
        (``_get_scoped_section`` روی ``version__status=DRAFT`` فیلتر
        می‌کند) — یک section از نسخه‌ی منتشرشده/بایگانی از این مسیر
        اصلاً یافت نمی‌شود (۴۰۴)، هرگز mutate نمی‌شود."""
        StorefrontSection.objects.create(version=self.draft, section_key="hero_banner", order=0)
        published = svc.publish(self.store)
        published_section = published.sections.get(section_key="hero_banner")
        resp = self.client.post(
            reverse("dashboard:storefront-builder-section-settings", args=[published_section.pk]), {},
        )
        self.assertEqual(resp.status_code, 404)


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

    def test_card_quick_add_reveal_persists(self):
        """P1 — گزینه‌ی نحوه‌ی نمایانِ دکمه‌ی افزودنِ سریع باید در
        ``settings.card.quick_add_reveal`` ذخیره شود."""
        resp = self.client.post(reverse("dashboard:storefront-builder-section-settings", args=[self.section.pk]), {
            "data_source": "newest", "item_limit": "8", "display_mode": "carousel",
            "card_quick_add_reveal": "hover_fade",
        })
        self.assertEqual(resp.status_code, 302)
        self.section.refresh_from_db()
        self.assertEqual(self.section.settings["card"]["quick_add_reveal"], "hover_fade")

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

    def test_header_editor_htmx_request_renders_embeddable_panel_not_full_page(self):
        """چکپوینتِ ۹: هدر باید بدونِ خروج از سازنده قابل‌ویرایش باشد —
        درخواستِ htmx باید فرگمنتِ داخلِ سازنده (بدونِ چیدمانِ کاملِ
        base_admin) برگرداند، نه صفحه‌ی مستقلِ قدیمی."""
        resp = self.client.get(reverse("dashboard:storefront-builder-header"), HTTP_HX_REQUEST="true")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "هدر فروشگاه")
        self.assertNotContains(resp, "بازگشت به ادیتور")

    def test_header_editor_non_htmx_request_still_renders_full_page(self):
        """درخواستِ مستقیمِ URL (بدونِ htmx) هم‌چنان صفحه‌ی کامل را
        برمی‌گرداند — سازگاریِ کامل با مسیرِ قدیمی."""
        resp = self.client.get(reverse("dashboard:storefront-builder-header"))
        self.assertContains(resp, "بازگشت به ادیتور")

    def test_footer_editor_htmx_request_renders_embeddable_panel_not_full_page(self):
        resp = self.client.get(reverse("dashboard:storefront-builder-footer"), HTTP_HX_REQUEST="true")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "فوتر فروشگاه")
        self.assertNotContains(resp, "بازگشت به ادیتور")

    def test_footer_editor_non_htmx_request_still_renders_full_page(self):
        resp = self.client.get(reverse("dashboard:storefront-builder-footer"))
        self.assertContains(resp, "بازگشت به ادیتور")

    def test_header_and_footer_reachable_from_appearance_hub_without_leaving_builder(self):
        resp = self.client.get(reverse("dashboard:storefront-builder-appearance"))
        self.assertContains(resp, reverse("dashboard:storefront-builder-header"))
        self.assertContains(resp, reverse("dashboard:storefront-builder-footer"))

    def test_header_editor_saves_responsive_settings(self):
        resp = self.client.post(reverse("dashboard:storefront-builder-header"), {
            "show_search": "on", "show_cart": "on",
            "show_search__hide_on_mobile": "on", "show_search__hide_on_tablet": "on",
        })
        self.assertEqual(resp.status_code, 302)
        draft = svc.get_or_create_draft(self.store)
        self.assertEqual(draft.header_config["responsive"]["show_search"], {"hide_on_tablet": True, "hide_on_mobile": True})
        # کامپوننتِ دیگر دست‌نخورده می‌ماند
        self.assertEqual(draft.header_config["responsive"]["show_account"], {"hide_on_tablet": False, "hide_on_mobile": False})

    def test_header_editor_form_shows_responsive_checkboxes(self):
        resp = self.client.get(reverse("dashboard:storefront-builder-header"))
        self.assertContains(resp, "show_search__hide_on_mobile")
        self.assertContains(resp, "show_search__hide_on_tablet")
        # سبدِ خرید عمداً کنترلِ «نمایش در دستگاه‌ها» ندارد
        self.assertNotContains(resp, "show_cart__hide_on_mobile")

    def test_footer_editor_saves_responsive_settings(self):
        resp = self.client.post(reverse("dashboard:storefront-builder-footer"), {
            "show_about": "on", "show_about__hide_on_mobile": "on",
        })
        self.assertEqual(resp.status_code, 302)
        draft = svc.get_or_create_draft(self.store)
        self.assertEqual(draft.footer_config["responsive"]["show_about"], {"hide_on_tablet": False, "hide_on_mobile": True})

    def test_footer_editor_form_shows_responsive_checkboxes(self):
        resp = self.client.get(reverse("dashboard:storefront-builder-footer"))
        self.assertContains(resp, "show_copyright__hide_on_mobile")

    def test_header_responsive_attribute_reaches_rendered_preview(self):
        draft = svc.get_or_create_draft(self.store)
        draft.header_config = svc.validate_header_config({
            "show_search": True, "show_cart": True,
            "responsive": {"show_search": {"hide_on_tablet": False, "hide_on_mobile": True}},
        })
        draft.save(update_fields=["header_config"])
        resp = self.client.get(reverse("dashboard:storefront-builder-preview"))
        self.assertContains(resp, "data-shell-hide-mobile")
        self.assertNotContains(resp, "data-shell-hide-tablet")

    def test_footer_responsive_attribute_reaches_rendered_preview(self):
        draft = svc.get_or_create_draft(self.store)
        draft.footer_config = svc.validate_footer_config({
            "show_copyright": True,
            "responsive": {"show_copyright": {"hide_on_tablet": True, "hide_on_mobile": False}},
        })
        draft.save(update_fields=["footer_config"])
        resp = self.client.get(reverse("dashboard:storefront-builder-preview"))
        self.assertContains(resp, "data-shell-hide-tablet")

    def test_header_responsive_absent_by_default_no_hide_attributes(self):
        """پیش‌فرض (بدونِ تنظیمِ صریح) یعنی نمایان در همه‌جا — هیچ
        data-shell-hide-* ای نباید رندر شود."""
        resp = self.client.get(reverse("dashboard:storefront-builder-preview"))
        self.assertNotContains(resp, "data-shell-hide-mobile")
        self.assertNotContains(resp, "data-shell-hide-tablet")


class RenderedPreviewIntegrationTests(StorefrontBuilderViewsTestCase):
    """رندرِ واقعیِ HTML از طریقِ preview endpoint — نه صرفاً بررسیِ دیکشنریِ
    context (که ``test_render_service.py`` انجام می‌دهد). این کلاس مشخصاً
    برایِ گرفتنِ باگ‌هایی نوشته شده که فقط در سطحِ template اتفاق می‌افتند —
    مثلاً یک context key که در سرویس درست ساخته می‌شود اما در
    ``{% include ... with %}`` ی ``responsive_section_wrapper.html`` فراموش
    شده باشد (این دقیقاً همان باگی بود که نبودِ این تست باعث شد فاش نشود)."""

    def setUp(self):
        super().setUp()
        from io import BytesIO

        from django.core.files.uploadedfile import SimpleUploadedFile
        from PIL import Image

        from apps.content.models import HeroSlide

        buf = BytesIO()
        Image.new("RGB", (800, 400), (10, 20, 30)).save(buf, "PNG")
        self.img = SimpleUploadedFile("t.png", buf.getvalue(), content_type="image/png")

        self.draft = svc.get_or_create_draft(self.store)
        self.draft.sections.filter(section_key="hero_banner").delete()
        self.hero_section = StorefrontSection.objects.create(
            version=self.draft, section_key="hero_banner", order=900,
            settings={"autoplay": False, "interval_ms": 4500, "show_arrows": True, "show_dots": True, "loop": True,
                      "responsive": {"hide_on_desktop": False, "hide_on_tablet": False, "hide_on_mobile": False}},
        )
        HeroSlide.objects.create(store=self.store, section=self.hero_section, title="اسلایدِ رندرشده", desktop_image=self.img, is_active=True)
        HeroSlide.objects.create(store=self.store, section=self.hero_section, title="اسلایدِ دوم", desktop_image=self.img, is_active=True)

    def test_hero_slider_settings_reach_the_rendered_html(self):
        """اگر ``slider_settings`` در ``{% include with %}`` فراموش شود،
        تمپلیت به مقدارِ پیش‌فرضِ ``{{ slider_settings.autoplay|yesno }}``
        (رشته‌ی خالی) برمی‌گردد که به ``false`` تفسیر می‌شود — این تست فقط
        وقتی رد می‌شود که واقعاً به مقدارِ *صحیحِ* ذخیره‌شده (این‌جا False)
        برسد، نه به یک پیش‌فرضِ تصادفاً هم‌ارز."""
        resp = self.client.get(reverse("dashboard:storefront-builder-preview"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "اسلایدِ رندرشده")
        self.assertContains(resp, "autoplay: false")

    def test_image_text_destination_link_reaches_rendered_html(self):
        section = StorefrontSection.objects.create(
            version=self.draft, section_key="image_text", order=901,
            settings={
                "title": "عنوانِ تست", "body_html": "", "image_url": "https://example.com/x.png", "image_position": "right",
                "destination": {"destination_type": "external", "destination_id": None,
                                 "destination_external_url": "https://example.com/landing", "open_in_new_tab": False},
                "responsive": {"hide_on_desktop": False, "hide_on_tablet": False, "hide_on_mobile": False},
            },
        )
        resp = self.client.get(reverse("dashboard:storefront-builder-preview"))
        self.assertContains(resp, "https://example.com/landing")

    def test_image_text_search_destination_reaches_rendered_html(self):
        """Phase 3 — مقصدِ جدیدِ ``search`` (بدون‌پارامتر، مثلِ external
        اما بدونِ URL دستی) باید تا HTMLِ رندرشده برسد."""
        section = StorefrontSection.objects.create(
            version=self.draft, section_key="image_text", order=902,
            settings={
                "title": "لینک به جستجو", "body_html": "", "image_url": "https://example.com/y.png", "image_position": "right",
                "destination": {"destination_type": "search", "destination_id": None,
                                 "destination_external_url": "", "open_in_new_tab": False},
                "responsive": {"hide_on_desktop": False, "hide_on_tablet": False, "hide_on_mobile": False},
            },
        )
        resp = self.client.get(reverse("dashboard:storefront-builder-preview"))
        self.assertContains(resp, reverse("catalog:product-list"))

    def test_motion_style_reaches_rendered_data_attribute(self):
        section = StorefrontSection.objects.create(
            version=self.draft, section_key="category_grid", order=903,
            settings={
                "title": "", "display_mode": "grid", "category_ids": [],
                "motion": {"style": "fade"},
                "responsive": {"hide_on_desktop": False, "hide_on_tablet": False, "hide_on_mobile": False},
            },
        )
        resp = self.client.get(reverse("dashboard:storefront-builder-preview"))
        self.assertContains(resp, 'data-motion="fade"')

    def test_missing_motion_key_defaults_to_none_in_rendered_html(self):
        section = StorefrontSection.objects.create(
            version=self.draft, section_key="rich_text", order=904,
            settings={"body_html": "پیشین"},
        )
        resp = self.client.get(reverse("dashboard:storefront-builder-preview"))
        self.assertContains(resp, 'data-motion="none"')

    def test_two_duplicated_category_grids_render_different_categories(self):
        """چکپوینتِ ۱۱ — رگرسیونِ همان کلاسِ باگ: اگر ``category_grid_settings``
        در ``{% include with %}`` فراموش شود، هر دو نمونه به رفتارِ auto
        (یکسان) برمی‌گردند، نه انتخابِ per-instance."""
        from apps.catalog.models import Category

        cat_a = Category.objects.create(store=self.store, name="دستهٔ رندرشدهٔ آ", slug="cat-render-a", is_active=True)
        cat_b = Category.objects.create(store=self.store, name="دستهٔ رندرشدهٔ ب", slug="cat-render-b", is_active=True)
        self.draft.sections.filter(section_key="category_grid").delete()
        StorefrontSection.objects.create(
            version=self.draft, section_key="category_grid", order=901,
            settings={"title": "", "display_mode": "grid", "category_ids": [cat_a.pk],
                      "responsive": {"hide_on_desktop": False, "hide_on_tablet": False, "hide_on_mobile": False}},
        )
        StorefrontSection.objects.create(
            version=self.draft, section_key="category_grid", order=902,
            settings={"title": "", "display_mode": "grid", "category_ids": [cat_b.pk],
                      "responsive": {"hide_on_desktop": False, "hide_on_tablet": False, "hide_on_mobile": False}},
        )
        resp = self.client.get(reverse("dashboard:storefront-builder-preview"))
        self.assertContains(resp, "دستهٔ رندرشدهٔ آ")
        self.assertContains(resp, "دستهٔ رندرشدهٔ ب")

    def test_two_duplicated_brand_carousels_render_different_brands_and_titles(self):
        from apps.catalog.models import Brand

        brand_a = Brand.objects.create(store=self.store, name="برندِ رندرشدهٔ آ", slug="brand-render-a", is_active=True)
        brand_b = Brand.objects.create(store=self.store, name="برندِ رندرشدهٔ ب", slug="brand-render-b", is_active=True)
        self.draft.sections.filter(section_key="brand_carousel").delete()
        StorefrontSection.objects.create(
            version=self.draft, section_key="brand_carousel", order=901,
            settings={"title": "برندهای بخش اول", "display_mode": "grid", "show_view_all": False, "brand_ids": [brand_a.pk],
                      "responsive": {"hide_on_desktop": False, "hide_on_tablet": False, "hide_on_mobile": False}},
        )
        StorefrontSection.objects.create(
            version=self.draft, section_key="brand_carousel", order=902,
            settings={"title": "برندهای بخش دوم", "display_mode": "grid", "show_view_all": False, "brand_ids": [brand_b.pk],
                      "responsive": {"hide_on_desktop": False, "hide_on_tablet": False, "hide_on_mobile": False}},
        )
        resp = self.client.get(reverse("dashboard:storefront-builder-preview"))
        self.assertContains(resp, "برندِ رندرشدهٔ آ")
        self.assertContains(resp, "برندِ رندرشدهٔ ب")
        self.assertContains(resp, "برندهای بخش اول")
        self.assertContains(resp, "برندهای بخش دوم")


class NewSectionTypesRenderedPreviewTests(StorefrontBuilderViewsTestCase):
    """چکپوینتِ ۱۲ — همان کلاسِ رگرسیونِ ``RenderedPreviewIntegrationTests``:
    برایِ هر نوعِ section جدید، حداقل یک context key که فقط در سرویس
    ساخته می‌شود باید واقعاً تا HTML رندرشده برسد (نه فقط دیکشنریِ context
    که ``test_render_service.py`` چک می‌کند)."""

    def setUp(self):
        super().setUp()
        self.draft = svc.get_or_create_draft(self.store)

    def test_collection_tiles_reach_rendered_html(self):
        from apps.catalog.models import MerchantCollection

        collection = MerchantCollection.objects.create(
            store=self.store, name="کالکشنِ رندرشده", slug="np-collection", is_active=True,
        )
        StorefrontSection.objects.create(
            version=self.draft, section_key="collection_tiles", order=901,
            settings={"title": "", "collection_ids": [collection.pk],
                      "responsive": {"hide_on_desktop": False, "hide_on_tablet": False, "hide_on_mobile": False}},
        )
        resp = self.client.get(reverse("dashboard:storefront-builder-preview"))
        self.assertContains(resp, "کالکشنِ رندرشده")
        self.assertContains(resp, "0 کالا")

    def test_quick_links_reach_rendered_html(self):
        from apps.catalog.models import Category
        from apps.content.models import DestinationType, Menu, MenuItem

        category = Category.objects.create(store=self.store, name="دستهٔ دسترسیِ سریع", slug="np-ql-cat", is_active=True)
        menu = Menu.objects.create(store=self.store, title="منوی تست", location=Menu.Location.HEADER, is_active=True)
        MenuItem.objects.create(
            menu=menu, title="لینکِ رندرشده", display_order=0, is_active=True,
            destination_type=DestinationType.CATEGORY, destination_category=category,
        )
        StorefrontSection.objects.create(
            version=self.draft, section_key="quick_links", order=901,
            settings={"title": "", "menu_id": menu.pk,
                      "responsive": {"hide_on_desktop": False, "hide_on_tablet": False, "hide_on_mobile": False}},
        )
        resp = self.client.get(reverse("dashboard:storefront-builder-preview"))
        self.assertContains(resp, "لینکِ رندرشده")

    def test_faq_items_reach_rendered_html(self):
        StorefrontSection.objects.create(
            version=self.draft, section_key="faq", order=901,
            settings={"title": "سوالات متداول", "items": [{"question": "سوالِ رندرشده؟", "answer": "پاسخِ رندرشده"}],
                      "responsive": {"hide_on_desktop": False, "hide_on_tablet": False, "hide_on_mobile": False}},
        )
        resp = self.client.get(reverse("dashboard:storefront-builder-preview"))
        self.assertContains(resp, "سوالِ رندرشده؟")
        self.assertContains(resp, "پاسخِ رندرشده")

    def test_testimonials_reach_rendered_html(self):
        StorefrontSection.objects.create(
            version=self.draft, section_key="testimonials", order=901,
            settings={"title": "نظرات مشتریان", "items": [{"name": "مشتریِ رندرشده", "quote": "نظرِ رندرشده", "role": ""}],
                      "responsive": {"hide_on_desktop": False, "hide_on_tablet": False, "hide_on_mobile": False}},
        )
        resp = self.client.get(reverse("dashboard:storefront-builder-preview"))
        self.assertContains(resp, "مشتریِ رندرشده")
        self.assertContains(resp, "نظرِ رندرشده")

    def test_video_section_reaches_rendered_html(self):
        StorefrontSection.objects.create(
            version=self.draft, section_key="video_section", order=901,
            settings={"title": "", "video_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ", "caption": "زیرنویسِ رندرشده",
                      "responsive": {"hide_on_desktop": False, "hide_on_tablet": False, "hide_on_mobile": False}},
        )
        resp = self.client.get(reverse("dashboard:storefront-builder-preview"))
        self.assertContains(resp, "youtube.com/embed/dQw4w9WgXcQ")
        self.assertContains(resp, "زیرنویسِ رندرشده")

    def test_newsletter_reaches_rendered_html(self):
        """Phase 3 — عنوان/زیرعنوان/متنِ دکمه باید تا HTML برسند، و خودِ
        فرم باید به endpointِ عمومیِ ثبتِ ایمیل اشاره کند (نه یک مسیرِ
        داشبورد)."""
        StorefrontSection.objects.create(
            version=self.draft, section_key="newsletter", order=901,
            settings={"title": "عنوانِ خبرنامه", "subtitle": "زیرعنوانِ خبرنامه", "button_label": "عضوِ من کن",
                      "responsive": {"hide_on_desktop": False, "hide_on_tablet": False, "hide_on_mobile": False}},
        )
        resp = self.client.get(reverse("dashboard:storefront-builder-preview"))
        self.assertContains(resp, "عنوانِ خبرنامه")
        self.assertContains(resp, "زیرعنوانِ خبرنامه")
        self.assertContains(resp, "عضوِ من کن")
        self.assertContains(resp, reverse("content:newsletter-subscribe"))


class NewSectionTypesSettingsFormTests(StorefrontBuilderViewsTestCase):
    def setUp(self):
        super().setUp()
        self.draft = svc.get_or_create_draft(self.store)

    def test_faq_settings_form_saves_items_in_order(self):
        section = StorefrontSection.objects.create(version=self.draft, section_key="faq", order=1)
        resp = self.client.post(reverse("dashboard:storefront-builder-section-settings", args=[section.pk]), {
            "title": "سوالات متداول",
            "question": ["سوال یک", "سوال دو"],
            "answer": ["پاسخ یک", "پاسخ دو"],
        })
        self.assertEqual(resp.status_code, 302)
        section.refresh_from_db()
        self.assertEqual(section.settings["items"], [
            {"question": "سوال یک", "answer": "پاسخ یک"},
            {"question": "سوال دو", "answer": "پاسخ دو"},
        ])

    def test_testimonials_settings_form_saves_items(self):
        section = StorefrontSection.objects.create(version=self.draft, section_key="testimonials", order=1)
        resp = self.client.post(reverse("dashboard:storefront-builder-section-settings", args=[section.pk]), {
            "title": "نظرات مشتریان",
            "t_name": ["سارا"], "t_quote": ["عالی بود"], "t_role": ["تهران"],
        })
        self.assertEqual(resp.status_code, 302)
        section.refresh_from_db()
        self.assertEqual(section.settings["items"], [{"name": "سارا", "quote": "عالی بود", "role": "تهران"}])

    def test_video_section_settings_form_rejects_unrecognized_url(self):
        section = StorefrontSection.objects.create(version=self.draft, section_key="video_section", order=1)
        resp = self.client.post(reverse("dashboard:storefront-builder-section-settings", args=[section.pk]), {
            "title": "", "video_url": "https://example.com/not-a-video", "caption": "",
        })
        self.assertEqual(resp.status_code, 200)
        section.refresh_from_db()
        self.assertEqual(section.settings, {})

    def test_video_section_settings_form_saves_valid_url(self):
        section = StorefrontSection.objects.create(version=self.draft, section_key="video_section", order=1)
        resp = self.client.post(reverse("dashboard:storefront-builder-section-settings", args=[section.pk]), {
            "title": "", "video_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ", "caption": "",
        })
        self.assertEqual(resp.status_code, 302)
        section.refresh_from_db()
        self.assertEqual(section.settings["video_url"], "https://www.youtube.com/watch?v=dQw4w9WgXcQ")

    def test_collection_tiles_settings_form_get_shows_picker(self):
        from apps.catalog.models import MerchantCollection

        MerchantCollection.objects.create(store=self.store, name="کالکشنِ انتخابی", slug="np-form-coll", is_active=True)
        section = StorefrontSection.objects.create(version=self.draft, section_key="collection_tiles", order=1)
        resp = self.client.get(reverse("dashboard:storefront-builder-section-settings", args=[section.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "کالکشنِ انتخابی")

    def test_quick_links_settings_form_get_shows_menu_picker(self):
        from apps.content.models import Menu

        Menu.objects.create(store=self.store, title="منویِ انتخابی", location=Menu.Location.FOOTER_1, is_active=True)
        section = StorefrontSection.objects.create(version=self.draft, section_key="quick_links", order=1)
        resp = self.client.get(reverse("dashboard:storefront-builder-section-settings", args=[section.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "منویِ انتخابی")

    def test_newsletter_settings_form_saves_fields(self):
        section = StorefrontSection.objects.create(version=self.draft, section_key="newsletter", order=1)
        resp = self.client.post(reverse("dashboard:storefront-builder-section-settings", args=[section.pk]), {
            "title": "عنوان جدید", "subtitle": "زیرعنوان جدید", "button_label": "بزن بریم",
        })
        self.assertEqual(resp.status_code, 302)
        section.refresh_from_db()
        self.assertEqual(section.settings["title"], "عنوان جدید")
        self.assertEqual(section.settings["subtitle"], "زیرعنوان جدید")
        self.assertEqual(section.settings["button_label"], "بزن بریم")

    def test_newsletter_only_one_instance_allowed(self):
        StorefrontSection.objects.create(version=self.draft, section_key="newsletter", order=1)
        self.client.post(reverse("dashboard:storefront-builder-section-add"), {"section_key": "newsletter"})
        self.assertEqual(self.draft.sections.filter(section_key="newsletter").count(), 1)


class PageSwitchingTests(StorefrontBuilderViewsTestCase):
    """Phase 2 (سازنده‌ی تک‌صفحه‌ای): ادیتور اکنون رویِ هر شش نوعِ صفحه
    کار می‌کند — ``?page=<page_type>`` صریحاً در URL، پیش‌فرضِ غایب/
    نامعتبر همیشه ``home`` (سازگاری کامل با رفتارِ پیش از این چکپوینت)."""

    def setUp(self):
        super().setUp()
        self.draft = svc.get_or_create_draft(self.store)
        self.draft.sections.all().delete()
        self.listing_page = self.draft.get_page(StorefrontPage.PageType.LISTING)
        self.home_page = self.draft.home_page()

    def test_editor_defaults_to_home_page(self):
        resp = self.client.get(reverse("dashboard:storefront-builder-editor"))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context["page_type"], "home")
        self.assertEqual(resp.context["page"].pk, self.home_page.pk)

    def test_editor_shows_page_switcher_for_all_six_pages(self):
        resp = self.client.get(reverse("dashboard:storefront-builder-editor"))
        for _value, label in StorefrontPage.PageType.choices:
            self.assertContains(resp, label)
        self.assertContains(resp, "sfb-page-switcher")

    def test_editor_switches_to_requested_page(self):
        resp = self.client.get(reverse("dashboard:storefront-builder-editor"), {"page": "listing"})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context["page_type"], "listing")
        self.assertEqual(resp.context["page"].pk, self.listing_page.pk)

    def test_editor_invalid_page_falls_back_to_home(self):
        resp = self.client.get(reverse("dashboard:storefront-builder-editor"), {"page": "not-a-real-page"})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context["page_type"], "home")

    def test_add_section_targets_requested_page(self):
        self.client.post(reverse("dashboard:storefront-builder-section-add"), {"section_key": "rich_text", "page": "listing"})
        self.assertTrue(self.listing_page.sections.filter(section_key="rich_text").exists())
        self.assertFalse(self.home_page.sections.filter(section_key="rich_text").exists())

    def test_add_section_without_page_param_defaults_to_home(self):
        self.client.post(reverse("dashboard:storefront-builder-section-add"), {"section_key": "rich_text"})
        self.assertTrue(self.home_page.sections.filter(section_key="rich_text").exists())
        self.assertFalse(self.listing_page.sections.filter(section_key="rich_text").exists())

    def test_reorder_scoped_to_page_does_not_affect_other_pages(self):
        home_a = StorefrontSection.objects.create(page=self.home_page, section_key="rich_text", order=0)
        listing_a = StorefrontSection.objects.create(page=self.listing_page, section_key="rich_text", order=0)
        listing_b = StorefrontSection.objects.create(page=self.listing_page, section_key="image_text", order=1)

        resp = self.client.post(reverse("dashboard:storefront-builder-section-reorder"), {
            "section_ids": [str(listing_b.pk), str(listing_a.pk)], "page": "listing",
        })
        self.assertEqual(resp.status_code, 200)
        listing_a.refresh_from_db()
        listing_b.refresh_from_db()
        home_a.refresh_from_db()
        self.assertEqual(listing_b.order, 0)
        self.assertEqual(listing_a.order, 1)
        self.assertEqual(home_a.order, 0)

    def test_reorder_cannot_reach_a_different_pages_section(self):
        """یک section از صفحه‌ی اصلی نباید با ``page=listing`` جابه‌جا شود —
        ``valid_ids`` باید به صفحه‌یِ درخواست‌شده محدود بماند."""
        home_a = StorefrontSection.objects.create(page=self.home_page, section_key="rich_text", order=0)
        listing_a = StorefrontSection.objects.create(page=self.listing_page, section_key="rich_text", order=5)

        self.client.post(reverse("dashboard:storefront-builder-section-reorder"), {
            "section_ids": [str(home_a.pk)], "page": "listing",
        })
        home_a.refresh_from_db()
        listing_a.refresh_from_db()
        self.assertEqual(home_a.order, 0)
        self.assertEqual(listing_a.order, 5)

    def test_move_toggle_duplicate_operate_on_sections_own_page(self):
        home_marker = StorefrontSection.objects.create(page=self.home_page, section_key="rich_text", order=0, settings={"body_html": "HOME-MARKER"})
        listing_marker = StorefrontSection.objects.create(page=self.listing_page, section_key="rich_text", order=0, settings={"body_html": "LISTING-MARKER"})

        resp = self.client.post(reverse("dashboard:storefront-builder-section-toggle", args=[listing_marker.pk]))
        self.assertEqual(resp.status_code, 200)
        listing_marker.refresh_from_db()
        home_marker.refresh_from_db()
        self.assertFalse(listing_marker.is_active)
        self.assertTrue(home_marker.is_active)

    def test_duplicate_stays_on_originating_page(self):
        listing_section = StorefrontSection.objects.create(page=self.listing_page, section_key="rich_text", order=0)
        self.client.post(reverse("dashboard:storefront-builder-section-duplicate", args=[listing_section.pk]))
        self.assertEqual(self.listing_page.sections.filter(section_key="rich_text").count(), 2)
        self.assertEqual(self.home_page.sections.filter(section_key="rich_text").count(), 0)

    def test_preview_shows_requested_pages_sections(self):
        StorefrontSection.objects.create(page=self.home_page, section_key="rich_text", order=0, settings={"body_html": "HOME-PREVIEW-MARKER"})
        StorefrontSection.objects.create(page=self.listing_page, section_key="rich_text", order=0, settings={"body_html": "LISTING-PREVIEW-MARKER"})

        home_resp = self.client.get(reverse("dashboard:storefront-builder-preview"))
        self.assertContains(home_resp, "HOME-PREVIEW-MARKER")
        self.assertNotContains(home_resp, "LISTING-PREVIEW-MARKER")

        listing_resp = self.client.get(reverse("dashboard:storefront-builder-preview"), {"page": "listing"})
        self.assertContains(listing_resp, "LISTING-PREVIEW-MARKER")
        self.assertNotContains(listing_resp, "HOME-PREVIEW-MARKER")

    def test_non_home_page_with_no_sections_shows_empty_state(self):
        resp = self.client.get(reverse("dashboard:storefront-builder-preview"), {"page": "cart"})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "هنوز هیچ بخش فعالی")


class CsrfEnforcementTests(StorefrontBuilderViewsTestCase):
    """چکپوینتِ ممیزیِ Phase 2: هیچ تستِ موجودی صراحتاً اجرایِ CSRF را
    برایِ این اپ اثبات نمی‌کرد (خودِ محافظت از قبل از طریقِ میدل‌ورِ
    سراسریِ جنگو برقرار است — هیچ ``csrf_exempt``ی در این اپ وجود ندارد
    — این کلاس صرفاً همان محافظتِ موجود را اثبات می‌کند، مکانیزمِ جدیدی
    اضافه نمی‌کند)."""

    def setUp(self):
        super().setUp()
        self.draft = svc.get_or_create_draft(self.store)
        self.draft.sections.all().delete()
        self.csrf_client = Client(HTTP_HOST=HOST, enforce_csrf_checks=True)
        self.csrf_client.login(username="sfb_owner", password="pass12345")

    def test_section_add_without_csrf_token_rejected(self):
        resp = self.csrf_client.post(reverse("dashboard:storefront-builder-section-add"), {"section_key": "rich_text"})
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(self.draft.sections.count(), 0)

    def test_section_reorder_without_csrf_token_rejected(self):
        section = StorefrontSection.objects.create(version=self.draft, section_key="rich_text", order=0)
        resp = self.csrf_client.post(reverse("dashboard:storefront-builder-section-reorder"), {"section_ids": [str(section.pk)]})
        self.assertEqual(resp.status_code, 403)

    def test_section_remove_without_csrf_token_rejected(self):
        section = StorefrontSection.objects.create(version=self.draft, section_key="rich_text", order=0)
        resp = self.csrf_client.post(reverse("dashboard:storefront-builder-section-remove", args=[section.pk]))
        self.assertEqual(resp.status_code, 403)
        self.assertTrue(StorefrontSection.objects.filter(pk=section.pk).exists())

    def test_publish_without_csrf_token_rejected(self):
        resp = self.csrf_client.post(reverse("dashboard:storefront-builder-publish"))
        self.assertEqual(resp.status_code, 403)

    # Phase 4: هدر/فوتر هم مثلِ بقیه‌ی Endpointهای POST این اپ زیرِ
    # میدل‌ورِ سراسریِ CSRF جنگو هستند — هیچ csrf_exempt ای اضافه نشده.
    def test_header_editor_without_csrf_token_rejected(self):
        draft = svc.get_or_create_draft(self.store)
        original_config = dict(draft.header_config or {})
        resp = self.csrf_client.post(reverse("dashboard:storefront-builder-header"), {"show_search": "on", "show_cart": "on"})
        self.assertEqual(resp.status_code, 403)
        draft.refresh_from_db()
        self.assertEqual(draft.header_config, original_config)

    def test_footer_editor_without_csrf_token_rejected(self):
        draft = svc.get_or_create_draft(self.store)
        original_config = dict(draft.footer_config or {})
        resp = self.csrf_client.post(reverse("dashboard:storefront-builder-footer"), {"show_copyright": "on"})
        self.assertEqual(resp.status_code, 403)
        draft.refresh_from_db()
        self.assertEqual(draft.footer_config, original_config)


class ProductDetailContextAwareSectionsPreviewTests(StorefrontBuilderViewsTestCase):
    """Phase 5: چهار نوعِ context-aware صفحه محصول واقعاً تا HTML رندرشده‌ی
    Preview می‌رسند (نه فقط dict، که test_render_service.py چک می‌کند) —
    Preview یک محصولِ نماینده (جدیدترین) را به‌جایِ «محصولِ جاری» انتخاب
    می‌کند، چون هیچ URLای برایِ یک محصولِ خاص در Preview وجود ندارد."""

    def setUp(self):
        super().setUp()
        from decimal import Decimal

        from apps.catalog.models import Category, Product, Vendor

        self.draft = svc.get_or_create_draft(self.store)
        self.pd_page = self.draft.get_page("product_detail")
        vendor = Vendor.objects.create(store=self.store, name="فروشنده پیش‌نمایش", slug="preview-vendor")
        category = Category.objects.create(store=self.store, name="دسته پیش‌نمایش", slug="preview-cat", is_active=True)
        self.product = Product.objects.create(
            store=self.store, vendor=vendor, category=category, name="کالای پیش‌نمایشِ رندرشده",
            slug="preview-render-product", sku="PREVIEW-RENDER-1", price=Decimal("75000"), stock=4,
            status=Product.Status.ACTIVE, description="توضیحاتِ کاملِ کالای پیش‌نمایش",
        )

    def _preview(self):
        return self.client.get(reverse("dashboard:storefront-builder-preview"), {"page": "product_detail"})

    def test_product_main_reaches_rendered_html(self):
        StorefrontSection.objects.create(page=self.pd_page, section_key="product_main", order=0)
        resp = self._preview()
        self.assertContains(resp, "کالای پیش‌نمایشِ رندرشده")
        self.assertContains(resp, "افزودن به سبد خرید")

    def test_product_description_reaches_rendered_html(self):
        StorefrontSection.objects.create(page=self.pd_page, section_key="product_description", order=0)
        resp = self._preview()
        self.assertContains(resp, "توضیحاتِ کاملِ کالای پیش‌نمایش")
        self.assertContains(resp, "مشخصات فنی")

    def test_related_products_reaches_rendered_html_when_related_exist(self):
        from datetime import timedelta
        from decimal import Decimal

        from django.utils import timezone

        from apps.catalog.models import Product

        related = Product.objects.create(
            store=self.store, vendor=self.product.vendor, category=self.product.category,
            name="کالای مرتبطِ پیش‌نمایش", slug="preview-related-product", sku="PREVIEW-RELATED-1",
            price=Decimal("20000"), stock=2, status=Product.Status.ACTIVE,
        )
        # Preview انتخابِ «محصولِ جاری» را از رویِ جدیدترینِ محصولِ فروشگاه
        # انجام می‌دهد (``_preview_page_context``) — این تست باید مطمئن
        # باشد ``self.product`` (نه ``related``) همان «جاری» است، تا
        # ``related`` واقعاً در گریدِ محصولاتِ مرتبط ظاهر شود.
        Product.objects.filter(pk=related.pk).update(created_at=timezone.now() - timedelta(days=1))
        StorefrontSection.objects.create(page=self.pd_page, section_key="related_products", order=0)
        resp = self._preview()
        self.assertContains(resp, "کالای مرتبطِ پیش‌نمایش")

    def test_product_video_section_renders_nothing_without_videos(self):
        """محصولِ نماینده هیچ ویدیویی ندارد — section باید بی‌خطا و بدونِ
        هیچ نشانه‌ای از گرید ویدیو رندر شود (fail-safe، نه crash)."""
        StorefrontSection.objects.create(page=self.pd_page, section_key="product_video", order=0)
        resp = self._preview()
        self.assertEqual(resp.status_code, 200)
        self.assertNotContains(resp, "pdp-video-grid")

    def test_context_aware_sections_absent_on_other_page_tabs(self):
        """این چهار section فقط با ``?page=product_detail`` دیده می‌شوند —
        اگر همان section (با دستکاریِ مستقیم) رویِ صفحه‌ی دیگری بنشیند،
        Preview آن صفحه هرگز آن را رندر نمی‌کند (چون اصلاً section آن
        صفحه نیست)."""
        StorefrontSection.objects.create(page=self.pd_page, section_key="product_main", order=0)
        resp = self.client.get(reverse("dashboard:storefront-builder-preview"), {"page": "cart"})
        self.assertNotContains(resp, "کالای پیش‌نمایشِ رندرشده")


class ProductListingContextAwareSectionPreviewTests(StorefrontBuilderViewsTestCase):
    """Phase 5: ``product_listing`` تا HTML رندرشده‌ی Preview می‌رسد —
    روی هر دو تبِ listing و search."""

    def setUp(self):
        super().setUp()
        from decimal import Decimal

        from apps.catalog.models import Category, Product, Vendor

        self.draft = svc.get_or_create_draft(self.store)
        vendor = Vendor.objects.create(store=self.store, name="فروشنده لیست", slug="listing-vendor")
        category = Category.objects.create(store=self.store, name="دسته لیست", slug="listing-cat", is_active=True)
        Product.objects.create(
            store=self.store, vendor=vendor, category=category, name="کالای لیستِ رندرشده",
            slug="listing-render-product", sku="LISTING-RENDER-1", price=Decimal("30000"), stock=5,
            status=Product.Status.ACTIVE,
        )

    def test_product_listing_reaches_rendered_html_on_listing_tab(self):
        page = self.draft.get_page("listing")
        StorefrontSection.objects.create(page=page, section_key="product_listing", order=0)
        resp = self.client.get(reverse("dashboard:storefront-builder-preview"), {"page": "listing"})
        self.assertContains(resp, "کالای لیستِ رندرشده")
        self.assertContains(resp, "اعمال فیلتر")

    def test_product_listing_reaches_rendered_html_on_search_tab(self):
        page = self.draft.get_page("search")
        StorefrontSection.objects.create(page=page, section_key="product_listing", order=0)
        resp = self.client.get(reverse("dashboard:storefront-builder-preview"), {"page": "search"})
        self.assertContains(resp, "کالای لیستِ رندرشده")

    def test_product_listing_not_addable_to_cart(self):
        cart_page = self.draft.get_page("cart")
        resp = self.client.post(reverse("dashboard:storefront-builder-section-add"), {
            "section_key": "product_listing", "page": "cart",
        })
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(cart_page.sections.filter(section_key="product_listing").count(), 0)


class CollectionContextAwareSectionsPreviewTests(StorefrontBuilderViewsTestCase):
    """Phase 5: ``collection_header``/``collection_products`` تا HTML
    رندرشده‌ی Preview می‌رسند — Preview جدیدترین کالکشنِ فروشگاه را
    به‌عنوانِ «کالکشنِ جاری» نماینده انتخاب می‌کند."""

    def setUp(self):
        super().setUp()
        from apps.catalog.services import collection_service

        self.draft = svc.get_or_create_draft(self.store)
        self.collection_page = self.draft.get_page("collection")
        self.collection = collection_service.create_collection(
            self.store, name="کالکشنِ پیش‌نمایشِ رندرشده", description="توضیحِ کالکشنِ پیش‌نمایش",
        )

    def _preview(self):
        return self.client.get(reverse("dashboard:storefront-builder-preview"), {"page": "collection"})

    def test_collection_header_reaches_rendered_html(self):
        StorefrontSection.objects.create(page=self.collection_page, section_key="collection_header", order=0)
        resp = self._preview()
        self.assertContains(resp, "کالکشنِ پیش‌نمایشِ رندرشده")
        self.assertContains(resp, "توضیحِ کالکشنِ پیش‌نمایش")

    def test_collection_products_reaches_rendered_html_and_shows_empty_state(self):
        StorefrontSection.objects.create(page=self.collection_page, section_key="collection_products", order=0)
        resp = self._preview()
        self.assertContains(resp, "فعلاً کالایی در این کالکشن برای نمایش وجود ندارد")

    def test_collection_sections_not_addable_to_product_detail(self):
        pd_page = self.draft.get_page("product_detail")
        resp = self.client.post(reverse("dashboard:storefront-builder-section-add"), {
            "section_key": "collection_header", "page": "product_detail",
        })
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(pd_page.sections.filter(section_key="collection_header").count(), 0)


class CartContextAwareSectionsPreviewTests(StorefrontBuilderViewsTestCase):
    """Phase 5: ``cart_items``/``cart_summary`` تا HTML رندرشده‌ی Preview
    می‌رسند — Preview هرگز سبدِ واقعیِ کاربر را نشان نمی‌دهد (نگاه کنید به
    Phase 4)، پس همیشه حالتِ خالی نشان داده می‌شود."""

    def setUp(self):
        super().setUp()
        self.draft = svc.get_or_create_draft(self.store)
        self.cart_page = self.draft.get_page("cart")

    def _preview(self):
        return self.client.get(reverse("dashboard:storefront-builder-preview"), {"page": "cart"})

    def test_cart_items_shows_empty_state_in_preview(self):
        StorefrontSection.objects.create(page=self.cart_page, section_key="cart_items", order=0)
        resp = self._preview()
        self.assertContains(resp, "سبد خرید شما خالی است")

    def test_cart_summary_renders_nothing_in_preview_empty_state(self):
        # data-section-label (فقط برای Preview، همیشه حاضر تا مرچنت بتواند
        # جایگاهِ خالی را هم انتخاب کند) خودش شاملِ عبارتِ «خلاصه سفارش»ست —
        # این تست باید محتوایِ واقعیِ کارت را چک کند، نه برچسبِ section.
        StorefrontSection.objects.create(page=self.cart_page, section_key="cart_summary", order=0)
        resp = self._preview()
        self.assertNotContains(resp, "جمع قابل پرداخت")
        self.assertNotContains(resp, "ادامه و تسویه‌حساب")

    def test_cart_sections_not_addable_to_home(self):
        home_page = self.draft.get_page("home")
        resp = self.client.post(reverse("dashboard:storefront-builder-section-add"), {
            "section_key": "cart_items", "page": "home",
        })
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(home_page.sections.filter(section_key="cart_items").count(), 0)
