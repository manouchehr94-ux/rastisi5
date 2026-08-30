from pathlib import Path
from django.conf import settings
from django.test import SimpleTestCase


class R32BrowserFixContractTests(SimpleTestCase):
    def setUp(self):
        self.root = Path(settings.BASE_DIR)

    def read(self, rel):
        return (self.root / rel).read_text(encoding='utf-8')

    def test_modal_target_is_permanent_and_teleported(self):
        modal = self.read('apps/storefront_builder/templates/dashboard/storefront_builder/partials/r3_edit_modal.html')
        self.assertIn('x-teleport="body"', modal)
        self.assertIn('x-show="r3ModalOpen"', modal)
        self.assertNotIn('x-if="r3ModalOpen"', modal)
        self.assertIn('id="sfbR3ModalBody"', modal)

    def test_back_button_is_always_available(self):
        modal = self.read('apps/storefront_builder/templates/dashboard/storefront_builder/partials/r3_edit_modal.html')
        self.assertIn("class=\"sfb-r3-modal__back\" @click=\"r3ModalKind === 'deep' ? backR3Deep() : closeR3Modal()\"", modal)
        self.assertNotIn("class=\"sfb-r3-modal__back\" x-show=", modal)

    def test_modal_is_seventy_percent_on_desktop(self):
        css = self.read('apps/storefront_builder/static/css/storefront_builder_r3.css')
        self.assertIn('width:min(70vw,1100px);max-width:1100px;min-width:0;', css)

    def test_edit_mode_intercepts_storefront_actions_before_customer_handlers(self):
        preview = self.read('apps/storefront_builder/templates/storefront_builder/preview.html')
        self.assertIn("document.addEventListener('click', interceptBuilderEditClick, true)", preview)
        self.assertIn('evt.stopImmediatePropagation()', preview)
        self.assertIn("type: 'sfb:openHeaderSettings'", preview)
        self.assertIn("type: 'sfb:openFooterSettings'", preview)
        self.assertIn("type: 'sfb:openSectionSettings'", preview)
