from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

from apps.storefront_builder import section_registry
from apps.storefront_builder.models import StorefrontPage


class StorefrontBuilderQAHarnessContractTests(SimpleTestCase):
    def test_every_registry_definition_is_either_hidden_or_in_a_page_library(self):
        library_keys = set()
        for page_type, _label in StorefrontPage.PageType.choices:
            for _category, definitions in section_registry.list_library_groups(page_type=page_type):
                library_keys.update(definition.key for definition in definitions)

        definitions = section_registry.list_definitions()
        self.assertGreaterEqual(len(definitions), 34)
        missing = [
            definition.key
            for definition in definitions
            if not definition.hidden_from_library and definition.key not in library_keys
        ]
        self.assertEqual(missing, [])

    def test_browser_runner_covers_actions_layout_errors_and_destructive_controls(self):
        runner = Path(settings.BASE_DIR) / "tools" / "storefront_builder_qa" / "run.mjs"
        package = runner.with_name("package.json")
        self.assertTrue(runner.exists())
        self.assertTrue(package.exists())
        source = runner.read_text(encoding="utf-8")
        for marker in (
            "registry:all-definitions-covered",
            "duplicate-capability",
            "hide-and-undo",
            "lock-unlock-and-command-disable",
            "move-up-and-undo",
            "remove-and-undo",
            "settings-save-noop",
            "internal-links-stay-in-builder",
            "library:drag-drop-onto-canvas",
            "quarter_left",
            "quarter_right",
            "keyboard:undo-redo-shortcuts",
            "browser:console-errors",
            "browser:request-failures",
            "topbar:publish-button-real-submit",
            "library:discard-draft-real-submit",
        ):
            self.assertIn(marker, source)
