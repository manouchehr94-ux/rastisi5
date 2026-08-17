from pathlib import Path

from django.urls import reverse

from apps.storefront_builder import section_registry
from apps.storefront_builder.models import StorefrontPage, StorefrontSection
from apps.storefront_builder.services import container_service, layout_service

from .test_views import StorefrontBuilderViewsTestCase


class Phase33BuilderUXCompletionTests(StorefrontBuilderViewsTestCase):
    def setUp(self):
        super().setUp()
        self.draft = layout_service.get_or_create_draft(self.store, user=self.staff)
        self.page = self.draft.get_page(StorefrontPage.PageType.HOME)

    def test_parent_builder_owns_cross_iframe_library_drop_surface(self):
        response = self.client.get(reverse("dashboard:storefront-builder-editor") + "?page=home")
        html = response.content.decode("utf-8")
        self.assertIn("sfb-library-cell-drop-layer", html)
        self.assertIn("libraryCellDropZones", html)
        self.assertIn("refreshLibraryCellDropZones", html)
        self.assertIn("updateLibraryCellDropOverlay", html)
        self.assertIn("dropLibraryToCellOverlay", html)
        self.assertIn("addContentBlockToCell(sectionKey, cellId, containerId)", html)

    def test_rich_text_uses_simplified_merchant_editor_and_hides_transport_html(self):
        section = StorefrontSection.objects.create(
            page=self.page,
            section_key="rich_text",
            order=0,
            settings={"body_html": "<p>سلام</p>"},
        )
        response = self.client.get(
            reverse("dashboard:storefront-builder-section-settings", args=[section.pk])
        )
        html = response.content.decode("utf-8")
        self.assertIn('x-data="storefrontRichTextEditor()"', html)
        self.assertIn("sfb-rich-text-source", html)
        self.assertIn("کد HTML نمایش داده نمی‌شود", html)
        self.assertIn("تنظیمات بیشتر", html)

    def test_rich_text_registry_name_is_plain_merchant_language(self):
        definition = section_registry.get_definition("rich_text")
        self.assertEqual(definition.label_fa, "متن")
        self.assertIn("پاراگراف", definition.description_fa)
        self.assertIn("HTML", definition.description_fa)

    def test_container_settings_explain_natural_cell_frames(self):
        container = container_service.create_empty_container(self.page, "half")
        response = self.client.get(
            reverse("dashboard:storefront-builder-container-settings", args=[container.pk])
        )
        self.assertContains(response, "هر خانه فقط به اندازه محتوای خودش قاب می‌گیرد")
        self.assertContains(response, "محتوای کوتاه دیگر تا ارتفاع بلندترین خانه کشیده نمی‌شود")

    def test_phase33_css_contract_keeps_selection_drop_overlay_and_phase34_natural_height(self):
        css = (
            Path(__file__).resolve().parents[1]
            / "static"
            / "css"
            / "storefront_builder.css"
        ).read_text(encoding="utf-8")
        phase = css[css.index("Phase 3.3 — coherent row frames"):]
        self.assertIn("Phase 3.4 — natural cell frames", phase)
        self.assertIn("align-self: start !important", phase)
        self.assertIn("height: max-content !important", phase)
        self.assertIn(".sfb-library-cell-drop-layer", phase)
        self.assertIn(".sfb-library-cell-drop-zone.active", phase)
        self.assertIn(".sfb-rich-text-source", phase)
        self.assertIn(".sfb-rsec-selected", phase)

    def test_base_admin_storefront_editor_toolbar_is_intentionally_small(self):
        base = (
            Path(__file__).resolve().parents[2]
            / "dashboard"
            / "templates"
            / "dashboard"
            / "base_admin.html"
        ).read_text(encoding="utf-8")
        start = base.index("function storefrontRichTextEditor()")
        end = base.index("\n</script>", start)
        function = base[start:end]
        for key in ('"heading"', '"bold"', '"italic"', '"bulletedList"', '"numberedList"', '"link"'):
            self.assertIn(key, function)
        self.assertNotIn('"uploadImage"', function)
        self.assertNotIn('"mediaEmbed"', function)
        self.assertNotIn('"insertTable"', function)
