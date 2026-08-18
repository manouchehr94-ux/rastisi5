from pathlib import Path

from django.test import SimpleTestCase


class Phase276SectionCommandSingleFlightTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.editor = (
            Path(__file__).resolve().parents[1]
            / "templates"
            / "dashboard"
            / "storefront_builder"
            / "editor.html"
        ).read_text(encoding="utf-8")

    def test_section_commands_are_single_flight_per_section(self):
        self.assertIn("sectionCommandBusy: {}", self.editor)
        self.assertIn("const commandKey = String(sectionId);", self.editor)
        self.assertIn("if (this.sectionCommandBusy[commandKey]) return;", self.editor)
        self.assertIn("this.sectionCommandBusy[commandKey] = command;", self.editor)

    def test_busy_guard_survives_until_preview_reload(self):
        self.assertIn(
            "iframe.addEventListener('load', releaseAfterPreviewReload, { once: true });",
            self.editor,
        )
        self.assertIn("window.setTimeout(releaseWithoutReload, 8000)", self.editor)
        self.assertIn("iframe.removeEventListener('load', releaseAfterPreviewReload);", self.editor)
        self.assertIn("delete this.sectionCommandBusy[commandKey];", self.editor)

        ajax_pos = self.editor.index("const request = htmx.ajax('POST', url, options);")
        listener_pos = self.editor.index(
            "iframe.addEventListener('load', releaseAfterPreviewReload, { once: true });"
        )
        self.assertLess(listener_pos, ajax_pos)

    def test_success_path_does_not_release_guard_before_reload(self):
        start = self.editor.index("sectionCommand(sectionId, command)")
        # Slice only the section command. Container commands intentionally use
        # their own promise-finally guard and must not contaminate this check.
        end = self.editor.index("containerCommand(containerId, command)", start)
        method = self.editor[start:end]
        self.assertNotIn(".finally(() =>", method)
        self.assertIn("Promise.resolve(request).then(() =>", method)
        self.assertIn("releaseAfterPreviewReload", method)
