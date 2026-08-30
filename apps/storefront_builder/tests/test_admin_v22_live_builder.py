from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase


class AdminV22LiveBuilderContractTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.root = Path(settings.BASE_DIR)

    def _read(self, relpath: str) -> str:
        return (self.root / relpath).read_text(encoding="utf-8")

    def test_builder_uses_dedicated_full_window_workspace_without_legacy_fullscreen_collision(self):
        editor = self._read("apps/storefront_builder/templates/dashboard/storefront_builder/editor.html")
        css = self._read("apps/storefront_builder/static/css/storefront_builder_v22.css")
        self.assertIn("sfb-v22-workspace", editor)
        self.assertIn("fullscreen: false", editor)
        self.assertNotIn("fullscreen: true", editor)
        self.assertIn("builderMode: 'edit'", editor)
        self.assertIn(".sfb-v22-workspace .sfb-v3-main", css)
        self.assertIn("position:absolute !important", css)

    def test_builder_has_plain_language_primary_actions(self):
        editor = self._read("apps/storefront_builder/templates/dashboard/storefront_builder/editor.html")
        for label in ("ساختار صفحه", "افزودن بخش", "ظاهر فروشگاه", "پیش‌نمایش", "ویرایش"):
            self.assertIn(label, editor)
        self.assertIn("openAppearancePanel()", editor)
        self.assertIn("sfb-v22-drawer-backdrop", editor)

    def test_builder_drawers_overlay_instead_of_taking_canvas_columns(self):
        css = self._read("apps/storefront_builder/static/css/storefront_builder_v22.css")
        self.assertIn(".sfb-v22-workspace .sfb-v3-sidebar-right", css)
        self.assertIn(".sfb-v22-workspace .sfb-v3-inspector", css)
        self.assertIn("position:absolute !important", css)
        self.assertIn(".sfb-v22-drawer-backdrop", css)
        self.assertIn("width:370px", css)
        self.assertIn("width:430px", css)

    def test_edit_preview_uses_one_obvious_edit_action_and_exact_entity_labels(self):
        css = self._read("apps/storefront_builder/static/css/storefront_builder_preview_v22.css")
        self.assertIn("button:not([data-open-settings])", css)
        self.assertIn("[data-open-settings]::after", css)
        self.assertIn('content:"ویرایش"', css)
        self.assertIn("[data-admin-edit-kind]::after", css)
        self.assertIn('content:"✎ ویرایش"', css)
        self.assertIn("ویرایش هدر", css)
        self.assertIn("ویرایش فوتر", css)

    def test_existing_builder_engine_contracts_are_preserved(self):
        editor = self._read("apps/storefront_builder/templates/dashboard/storefront_builder/editor.html")
        for contract in (
            "storefront-builder-preview",
            "storefront-builder-publish",
            "storefront-builder-undo",
            "storefront-builder-redo",
            "sfb:selectSection",
            "queueInspectorAutosave",
        ):
            self.assertIn(contract, editor)

    def test_section_placement_state_exposes_section_key(self):
        state = self._read("apps/storefront_builder/templates/dashboard/storefront_builder/partials/container_state.html")
        self.assertIn('data-section-key="{{ block.section_key }}"', state)

    def test_deep_workspace_uses_real_existing_admin_editors(self):
        editor = self._read("apps/storefront_builder/templates/dashboard/storefront_builder/editor.html")
        settings_form = self._read("apps/storefront_builder/templates/dashboard/storefront_builder/partials/section_settings_form.html")
        self.assertIn("deepWorkspaceOpen", editor)
        self.assertIn("openDeepWorkspace(url, title)", editor)
        self.assertIn("closeDeepWorkspace()", editor)
        self.assertIn("sfb-v22-deep-workspace", editor)
        for url_name in (
            "dashboard:product-list",
            "dashboard:category-list",
            "dashboard:brand-list",
            "dashboard:collection-list",
            "dashboard:storefront-builder-section-media-list",
        ):
            self.assertIn(url_name, settings_form)
        self.assertIn('hero-slides', settings_form)
        self.assertIn('banners', settings_form)

    def test_product_section_keeps_inline_manual_product_picker(self):
        settings_form = self._read("apps/storefront_builder/templates/dashboard/storefront_builder/partials/section_settings_form.html")
        self.assertIn("productSectionForm", settings_form)
        self.assertIn("storefront-builder-section-product-search", settings_form)
        self.assertIn("کالاهای دستی (انتخاب تکی)", settings_form)

    def test_header_and_footer_real_editors_stay_inside_builder_workspace(self):
        header = self._read("apps/storefront_builder/templates/dashboard/storefront_builder/partials/header_panel.html")
        footer = self._read("apps/storefront_builder/templates/dashboard/storefront_builder/partials/footer_panel.html")
        self.assertIn("openDeepWorkspace", header)
        self.assertIn('data-sfb-focus="logo"', header)
        self.assertIn("dashboard:settings-shop-info", header)
        self.assertIn("openDeepWorkspace", footer)
        self.assertIn("dashboard:footer-settings", footer)
        self.assertIn("dashboard:footer-trust-badge-list", footer)

    def test_product_cards_can_jump_to_the_exact_real_product_editor(self):
        card = self._read("apps/catalog/templates/catalog/partials/product_card.html")
        preview = self._read("apps/storefront_builder/templates/storefront_builder/preview.html")
        editor = self._read("apps/storefront_builder/templates/dashboard/storefront_builder/editor.html")
        self.assertIn("data-admin-product-id", card)
        self.assertIn("is_builder_preview", card)
        self.assertIn("is_builder_preview=True", preview)
        self.assertIn('data-admin-edit-kind="product"', card)
        self.assertIn("sfb:openEntityEditor", preview)
        self.assertIn("dashboard:product-edit", editor)
        self.assertIn("dashboard:category-edit", editor)
        self.assertIn("dashboard:brand-edit", editor)
        self.assertIn("dashboard:collection-edit", editor)
        self.assertIn("dashboard:storefront-builder-section-media-edit", editor)

    def test_visible_storefront_items_expose_exact_edit_metadata_in_builder_preview(self):
        contracts = {
            "apps/storefront_builder/templates/storefront_builder/partials/hero_slider_body.html": ('data-admin-edit-kind="media"', 'data-admin-media-kind="hero-slides"'),
            "apps/storefront_builder/templates/storefront_builder/sections/single_banner.html": ('data-admin-edit-kind="media"', 'data-admin-media-kind="banners"'),
            "apps/storefront_builder/templates/storefront_builder/sections/multi_banner.html": ('data-admin-edit-kind="media"', 'data-admin-media-kind="banners"'),
            "apps/storefront_builder/templates/storefront_builder/sections/category_grid.html": ('data-admin-edit-kind="category"', 'data-admin-edit-id'),
            "apps/storefront_builder/templates/storefront_builder/sections/brand_carousel.html": ('data-admin-edit-kind="brand"', 'data-admin-edit-id'),
            "apps/storefront_builder/templates/storefront_builder/sections/collection_tiles.html": ('data-admin-edit-kind="collection"', 'data-admin-edit-id'),
        }
        for relpath, needles in contracts.items():
            source = self._read(relpath)
            for needle in needles:
                self.assertIn(needle, source, relpath)

    def test_preview_understands_clean_preview_and_edit_modes(self):
        preview = self._read("apps/storefront_builder/templates/storefront_builder/preview.html")
        self.assertIn("sfb:setMode", preview)
        self.assertIn("builderMode", preview)
        self.assertIn("sfb:openFooterSettings", preview)
        self.assertIn("css/storefront_builder_preview_v22.css", preview)

    def test_v22_builder_css_is_loaded(self):
        editor = self._read("apps/storefront_builder/templates/dashboard/storefront_builder/editor.html")
        self.assertIn("css/storefront_builder_v22.css", editor)
