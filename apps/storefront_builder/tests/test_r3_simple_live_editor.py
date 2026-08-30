from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase


class R3SimpleLiveEditorContractTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.root = Path(settings.BASE_DIR)

    def read(self, rel):
        return (self.root / rel).read_text(encoding="utf-8")

    def test_storefront_is_the_primary_surface(self):
        editor = self.read("apps/storefront_builder/templates/dashboard/storefront_builder/editor.html")
        css = self.read("apps/storefront_builder/static/css/storefront_builder_r3.css")
        self.assertIn("sfb-r3-shell", editor)
        self.assertIn("storefront_builder_r3.css", editor)
        self.assertIn(".sfb-r3-shell .sfb-v3-sidebar-right", css)
        self.assertIn("display:none !important", css)
        self.assertIn('[data-device="desktop"] #sfbPreviewFrame', css)
        self.assertIn("width:100% !important", css)

    def test_toolbar_uses_plain_merchant_actions(self):
        toolbar = self.read("apps/storefront_builder/templates/dashboard/storefront_builder/partials/r3_toolbar.html")
        for label in ("صفحه:", "افزودن", "ترتیب صفحه", "قالب‌ها", "رنگ‌ها", "ویرایش", "پیش‌نمایش", "انتشار"):
            self.assertIn(label, toolbar)
        self.assertIn("page_types", toolbar)
        self.assertIn("storefront-builder-templates", toolbar)
        self.assertIn("storefront-builder-publish", toolbar)

    def test_popup_is_large_overlay_and_reuses_existing_editors(self):
        editor = self.read("apps/storefront_builder/templates/dashboard/storefront_builder/editor.html")
        css = self.read("apps/storefront_builder/static/css/storefront_builder_r3.css")
        modal = self.read("apps/storefront_builder/templates/dashboard/storefront_builder/partials/r3_edit_modal.html")
        self.assertIn("width:min(70vw,1100px)", css)
        self.assertIn("position:fixed", css)
        self.assertIn("sfbR3ModalBody", modal)
        self.assertIn("openR3Section", editor)
        self.assertIn("openR3Panel", editor)
        self.assertIn("openR3Deep", editor)
        self.assertIn("htmx.ajax('GET', url, { target: '#sfbR3ModalBody'", editor)

    def test_add_popup_uses_registry_and_existing_cell_add_path(self):
        editor = self.read("apps/storefront_builder/templates/dashboard/storefront_builder/editor.html")
        add = self.read("apps/storefront_builder/templates/dashboard/storefront_builder/partials/r3_add_modal.html")
        self.assertIn("section_library_groups", add)
        self.assertIn("جستجوی بخش", add)
        self.assertIn("r3AddSection('{{ definition.key }}')", add)
        self.assertIn("this.$root.dataset.cellAddSectionUrl", editor)
        for forbidden in ("row_span", "12-column", "cell_id", "container_id"):
            self.assertNotIn(forbidden, add)

    def test_structure_popup_is_plain_language(self):
        editor = self.read("apps/storefront_builder/templates/dashboard/storefront_builder/editor.html")
        structure = self.read("apps/storefront_builder/templates/dashboard/storefront_builder/partials/r3_structure_modal.html")
        state = self.read("apps/storefront_builder/templates/dashboard/storefront_builder/partials/container_state.html")
        for label in ("بالا", "پایین", "ویرایش", "مخفی", "نمایش", "تکثیر", "حذف"):
            self.assertIn(label, structure)
        self.assertIn("this.openR3Modal('structure', 'ترتیب صفحه'", editor)
        self.assertIn("r3StructureGroups()", structure)
        self.assertIn("r3MoveGroup", structure)
        self.assertIn("data-section-active", state)
        self.assertIn("data-section-locked", state)
        for forbidden in ("row_span", "12 ستون"):
            self.assertNotIn(forbidden, structure)
        self.assertIn("containerCommand(containerId, direction)", editor)

    def test_preview_clicks_open_modal_not_permanent_inspector(self):
        editor = self.read("apps/storefront_builder/templates/dashboard/storefront_builder/editor.html")
        self.assertIn("this.openR3Section(evt.data.sectionId, evt.data)", editor)
        self.assertIn("this.openR3Panel('{% url 'dashboard:storefront-builder-header' %}', 'ویرایش هدر'", editor)
        self.assertIn("this.openR3Panel('{% url 'dashboard:storefront-builder-footer' %}', 'ویرایش فوتر'", editor)
        self.assertIn("this.openR3Deep(url, title, this.r3ModalTitle || 'ویرایش')", editor)

    def test_r2_engine_contracts_remain_present(self):
        editor = self.read("apps/storefront_builder/templates/dashboard/storefront_builder/editor.html")
        for contract in (
            "storefront-builder-preview",
            "storefront-builder-publish",
            "storefront-builder-undo",
            "storefront-builder-redo",
            "storefront-builder-section-settings",
            "storefront-builder-cell-add-section",
            "storefront-builder-container-add",
            "storefront-builder-appearance",
            "queueInspectorAutosave",
            "sfb:openEntityEditor",
        ):
            self.assertIn(contract, editor)
