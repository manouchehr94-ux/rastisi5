from io import BytesIO

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from PIL import Image

from apps.content.models import MediaAsset
from apps.storefront_builder import layout_preset_registry
from apps.storefront_builder.models import StorefrontLayoutVersion, StorefrontPage, StorefrontSection
from apps.storefront_builder.services import container_service, layout_service

from .test_views import StorefrontBuilderViewsTestCase


def _img(name="bg.png"):
    buf = BytesIO()
    Image.new("RGB", (10, 10), (120, 80, 40)).save(buf, "PNG")
    return SimpleUploadedFile(name, buf.getvalue(), content_type="image/png")


class Phase35ReferencePresetContractTests(TestCase):
    def test_reference_preset_keeps_the_approved_dense_homepage_sequence(self):
        preset = layout_preset_registry.get_layout_preset("v5_golden_homepage")
        self.assertEqual(
            [entry.section_key for entry in preset.pages["home"]],
            [
                "product_section", "hero_banner",
                "category_grid",
                "trust_features",
                "multi_banner",
                "product_section",
                "amazing_offers",
                "product_section",
                "multi_banner", "multi_banner",
                "product_section",
                "multi_banner", "multi_banner",
                "product_section", "product_section",
                "product_section",
                "product_section", "product_section",
                "multi_banner",
                "product_section",
                "multi_banner",
                "product_section",
            ],
        )

    def test_reference_preset_is_merchant_facing_and_keeps_colored_rails(self):
        preset = layout_preset_registry.get_layout_preset("v5_golden_homepage")
        self.assertEqual(preset.label_fa, "فروشگاه رنگی و کاتالوگی — مرجع")
        rails = [
            e for e in preset.pages["home"]
            if e.section_key == "product_section"
            and (e.settings or {}).get("background", {}).get("mode") == "palette_pattern"
        ]
        self.assertEqual(len(rails), 5)
        self.assertEqual(
            {e.settings["background"]["palette_role"] for e in rails},
            {"tone-1", "tone-2", "tone-3", "tone-4", "tone-5"},
        )
        self.assertEqual(preset.default_palette_slug, "catalog-colorful")


class Phase35EditableBackgroundTests(StorefrontBuilderViewsTestCase):
    def setUp(self):
        super().setUp()
        self.draft = layout_service.get_or_create_draft(self.store, user=self.staff)
        self.page = self.draft.get_page(StorefrontPage.PageType.HOME)
        self.page.containers.all().delete()
        self.page.sections.all().delete()
        self.draft.edit_history_entries.all().delete()

    def _product_section(self):
        definition_settings = {
            "data_source": "newest",
            "source_id": None,
            "product_ids": [],
            "item_limit": 6,
            "display_mode": "carousel",
            "show_view_all": True,
            "title": "محصولات رنگی",
            "subtitle": "",
            "carousel_autoplay": False,
            "carousel_interval_ms": 3500,
            "carousel_show_arrows": True,
            "header_position": "above",
            "background": {
                "mode": "pattern",
                "color": "#F53247",
                "pattern_slug": "commerce-doodle",
                "media_asset_id": None,
            },
            "spacing": {
                "vertical_spacing": "small",
                "advanced": {
                    "padding_top": None,
                    "padding_bottom": None,
                    "margin_top": None,
                    "margin_bottom": None,
                },
            },
        }
        section = StorefrontSection.objects.create(
            page=self.page,
            section_key="product_section",
            order=0,
            settings=definition_settings,
        )
        container = container_service.create_empty_container(self.page, "single")
        container_service.place_section(container.cells.get(), section)
        return section, container

    def test_section_settings_expose_merchant_background_editor(self):
        section, _ = self._product_section()
        response = self.client.get(
            reverse("dashboard:storefront-builder-section-settings", args=[section.pk])
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "پس‌زمینه بخش")
        self.assertContains(response, "رنگ از پالت کل سایت")
        self.assertContains(response, "پالت + الگوی ظریف")
        self.assertContains(response, "رنگ دلخواه ثابت")
        self.assertContains(response, "رنگ دلخواه + الگو")
        self.assertContains(response, "تصویر از رسانه‌های فروشگاه")
        self.assertContains(response, "#F53247")

    def test_product_background_and_reference_spacing_survive_legacy_post(self):
        section, _ = self._product_section()
        response = self.client.post(
            reverse("dashboard:storefront-builder-section-settings", args=[section.pk]),
            {
                "data_source": "newest",
                "item_limit": "6",
                "display_mode": "carousel",
                "show_view_all": "on",
                "title": "عنوان جدید",
                "subtitle": "",
                "carousel_interval_ms": "3500",
                "carousel_show_arrows": "on",
                "header_position": "above",
                "show_on_desktop": "on",
                "show_on_tablet": "on",
                "show_on_mobile": "on",
            },
        )
        self.assertEqual(response.status_code, 302)
        section.refresh_from_db()
        self.assertEqual(section.settings["background"]["mode"], "pattern")
        self.assertEqual(section.settings["background"]["color"], "#F53247")
        self.assertEqual(section.settings["spacing"]["vertical_spacing"], "small")

    def test_merchant_can_change_product_rail_to_custom_solid_background(self):
        section, _ = self._product_section()
        response = self.client.post(
            reverse("dashboard:storefront-builder-section-settings", args=[section.pk]),
            {
                "data_source": "newest",
                "item_limit": "6",
                "display_mode": "carousel",
                "show_view_all": "on",
                "title": "عنوان جدید",
                "subtitle": "",
                "carousel_interval_ms": "3500",
                "carousel_show_arrows": "on",
                "header_position": "above",
                "show_on_desktop": "on",
                "show_on_tablet": "on",
                "show_on_mobile": "on",
                "background_mode": "color",
                "background_color": "#123456",
            },
        )
        self.assertEqual(response.status_code, 302)
        section.refresh_from_db()
        self.assertEqual(section.settings["background"]["mode"], "color")
        self.assertEqual(section.settings["background"]["color"], "#123456")

    def test_background_image_picker_is_store_scoped(self):
        section, _ = self._product_section()
        own = MediaAsset.objects.create(store=self.store, image=_img("own.png"))
        other_store = type(self.store).objects.create(
            name="فروشگاه دیگر",
            slug="phase35-other",
            admin_subdomain="phase35-other",
        )
        foreign = MediaAsset.objects.create(store=other_store, image=_img("foreign.png"))

        response = self.client.get(
            reverse("dashboard:storefront-builder-section-settings", args=[section.pk])
        )
        html = response.content.decode("utf-8")
        self.assertIn(f"رسانه #{own.pk}", html)
        self.assertNotIn(f"رسانه #{foreign.pk}", html)


    def test_tampered_foreign_background_asset_is_rejected_without_mutation(self):
        section, _ = self._product_section()
        original = dict(section.settings["background"])
        other_store = type(self.store).objects.create(
            name="فروشگاه بیگانه",
            slug="phase35-foreign-post",
            admin_subdomain="phase35-foreign-post",
        )
        foreign = MediaAsset.objects.create(store=other_store, image=_img("foreign-post.png"))

        response = self.client.post(
            reverse("dashboard:storefront-builder-section-settings", args=[section.pk]),
            {
                "data_source": "newest",
                "item_limit": "6",
                "display_mode": "carousel",
                "show_view_all": "on",
                "title": "محصولات رنگی",
                "subtitle": "",
                "carousel_interval_ms": "3500",
                "carousel_show_arrows": "on",
                "header_position": "above",
                "show_on_desktop": "on",
                "show_on_tablet": "on",
                "show_on_mobile": "on",
                "background_mode": "image",
                "background_media_asset_id": str(foreign.pk),
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "متعلق به این فروشگاه نیست")
        section.refresh_from_db()
        self.assertEqual(section.settings["background"], original)

    def test_container_background_is_independent_from_content_background(self):
        section, container = self._product_section()
        response = self.client.post(
            reverse("dashboard:storefront-builder-container-settings", args=[container.pk]),
            {
                "gap": "14",
                "mobile_mode": "stack",
                "vertical_align": "start",
                "container_background_mode": "pattern",
                "container_background_color": "#352196",
                "container_background_pattern": "commerce-doodle",
            },
        )
        self.assertEqual(response.status_code, 200)
        container.refresh_from_db()
        cleaned = container_service.effective_container_settings(container.settings)
        self.assertEqual(cleaned["background_mode"], "pattern")
        self.assertEqual(cleaned["background_color"], "#352196")
        section.refresh_from_db()
        self.assertEqual(section.settings["background"]["color"], "#F53247")

        preview = self.client.get(
            reverse("dashboard:storefront-builder-preview") + "?page=home"
        )
        html = preview.content.decode("utf-8")
        self.assertIn('data-container-bg="pattern"', html)
        self.assertIn('data-container-pattern="commerce-doodle"', html)
        self.assertIn("background-color:#352196", html)


class Phase35ReferencePresetUndoSafetyTests(StorefrontBuilderViewsTestCase):
    def setUp(self):
        super().setUp()
        self.draft = layout_service.get_or_create_draft(self.store, user=self.staff)
        self.page = self.draft.get_page(StorefrontPage.PageType.HOME)
        self.page.containers.all().delete()
        self.page.sections.all().delete()
        self.draft.edit_history_entries.all().delete()

    def test_reference_preset_apply_is_one_undo_step_and_restores_previous_draft(self):
        """Acceptance Batch 2 (post-U11) correction: applying a Ready
        Template over a Draft with real existing content (``original``
        below) now preserves that content as a recoverable version-history
        checkpoint (Issue 1) instead of a local Undo/Redo entry — the same
        Draft-identity-boundary rule ``publish()`` already applies to
        Undo/Redo (see ``test_u1a_preset_edit_history_characterization.py``
        for the full rationale). The previous Draft state is still fully
        recoverable, just via History → Restore instead of Undo."""
        original = StorefrontSection.objects.create(
            page=self.page,
            section_key="rich_text",
            order=0,
            settings={"body_html": "<p>قبل از مرجع</p>"},
        )
        original_stable_id = original.stable_id
        container = container_service.create_empty_container(self.page, "single")
        container_service.place_section(container.cells.get(), original)

        response = self.client.post(
            reverse("dashboard:storefront-builder-apply-preset"),
            {
                "preset_key": "v5_golden_homepage",
                "confirm_preset_apply": "1",
            },
        )
        self.assertEqual(response.status_code, 302)

        layout = layout_service.get_or_create_layout(self.store)
        new_draft = layout.draft_version
        self.assertNotEqual(new_draft.pk, self.draft.pk)
        self.assertEqual(new_draft.appearance_config.get("layout_preset_key"), "v5_golden_homepage")
        self.assertGreater(new_draft.get_page(StorefrontPage.PageType.HOME).sections.count(), 1)

        # No Undo entry against either row — the checkpoint is the recovery
        # mechanism for this action.
        self.assertEqual(new_draft.edit_history_entries.count(), 0)
        self.draft.refresh_from_db()
        self.assertEqual(self.draft.status, StorefrontLayoutVersion.Status.ARCHIVED)
        self.assertEqual(self.draft.edit_history_entries.count(), 0)

        checkpoint = layout.versions.filter(status=StorefrontLayoutVersion.Status.ARCHIVED).latest("version_number")
        self.assertEqual(checkpoint.pk, self.draft.pk)
        restored = layout_service.restore_version(self.store, checkpoint.pk, user=self.staff)
        restored_section = restored.get_page(StorefrontPage.PageType.HOME).sections.get(stable_id=original_stable_id)
        self.assertEqual(restored_section.settings["body_html"], "<p>قبل از مرجع</p>")

        self.draft.refresh_from_db()
        restored_page = self.draft.get_page(StorefrontPage.PageType.HOME)
        restored = list(restored_page.sections.order_by("order", "id"))
        self.assertEqual(len(restored), 1)
        self.assertEqual(restored[0].section_key, "rich_text")
        self.assertEqual(restored[0].stable_id, original_stable_id)
        restored_container = restored_page.containers.get()
        restored_cell = restored_container.cells.get()
        self.assertEqual(restored_cell.section.stable_id, original_stable_id)
