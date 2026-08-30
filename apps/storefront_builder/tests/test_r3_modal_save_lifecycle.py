"""Phase 1 repair — R3 modal shared save lifecycle.

ROOT CAUSE (proven live in a real browser, see the Phase 1 report): the R3
full-screen editor reuses the same settings-form partials as the legacy R2
sidebar inspector, but the JS orchestration layer that turns a form submit
into a background AJAX save (``queueInspectorAutosave`` /
``autosaveInspectorForm``) was wired only to ``#sfbInspectorBody`` — the R2
panel, permanently ``display:none`` inside ``.sfb-r3-shell``. ``#sfbR3ModalBody``
never received the equivalent wiring, so:

  * the inner "ذخیره تنظیمات" submit button fell through to a *native*
    browser form submission (confirmed via Playwright: two
    ``framenavigated`` events, R3 modal closed afterwards) instead of
    keeping the modal open;
  * the footer "انجام شد" button was a plain ``@click="closeR3Modal();
    reloadPreview()"`` with no persistence call at all — clicking it
    discarded any unsaved change in the active form.

Both buttons are therefore fixed at their shared root: one
``saveActiveR3Settings({closeOnSuccess})`` operation, invoked by a single
submit listener delegated on ``document.body`` (filtered to
``#sfbR3ModalBody`` forms — see the docstring on the test below for why it
is not attached to ``#sfbR3ModalBody`` directly) and by the footer Done
button, built on the same ``postFormAjax`` helper R2's autosave now also
uses — not a second, independent persistence path.
"""

from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase


class R3ModalSharedSaveLifecycleTests(SimpleTestCase):
    """The regression for the shared root cause (Task 1-3 of the plan)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.root = Path(settings.BASE_DIR)

    def read(self, rel):
        return (self.root / rel).read_text(encoding="utf-8")

    def setUp(self):
        self.editor = self.read(
            "apps/storefront_builder/templates/dashboard/storefront_builder/editor.html"
        )
        self.modal = self.read(
            "apps/storefront_builder/templates/dashboard/storefront_builder/partials/r3_edit_modal.html"
        )

    def test_r3_modal_body_gets_a_submit_listener_like_the_r2_inspector_does(self):
        """This is the actual regression for the shared lifecycle bug: R2's
        ``#sfbInspectorBody`` has always had its own submit/input listeners;
        prior to the fix, ``#sfbR3ModalBody`` had none at all, so a submit
        inside the R3 modal fell through to the browser's native, full-page
        form submission — destroying the modal instead of keeping it open.

        The listener is delegated on ``document.body`` rather than looked up
        by ``document.getElementById('sfbR3ModalBody')`` directly: that
        element lives inside ``r3_edit_modal.html``'s
        ``<template x-teleport="body">``, which Alpine only clones into
        ``<body>`` once its initial walker actually reaches that directive —
        strictly *after* the root's own ``x-init="init()"`` (which runs
        first, before any descendant is visited) has already executed. A
        direct ``getElementById('sfbR3ModalBody')`` call inside ``init()``
        would therefore find nothing and silently wire up no listener at
        all (confirmed live: a first version of this fix looked up the
        element directly and Playwright still observed the old native-submit
        navigation). ``document.body`` already exists at that point, so
        delegating on it — the same way the file already does for
        ``sfbSectionAdded``/``sfbContainerAdded``/etc. a few lines below —
        sidesteps the ordering hazard entirely."""
        self.assertIn("document.getElementById('sfbInspectorBody')", self.editor)
        body_setup = self.editor.split(
            "document.body.addEventListener('submit', (evt) => {\n"
            "        if (!evt.target.matches('#sfbR3ModalBody form[data-sfb-autosave=\"true\"]')) return;",
            1,
        )
        self.assertEqual(
            len(body_setup), 2,
            "editor.html must delegate a submit listener for #sfbR3ModalBody "
            "forms on document.body (not a direct #sfbR3ModalBody lookup, "
            "which does not exist yet when init() runs — see docstring).",
        )
        wiring = body_setup[1][:200]
        self.assertIn("evt.preventDefault()", wiring)
        self.assertIn("this.saveActiveR3Settings({ closeOnSuccess: false })", wiring)

    def test_listener_is_registered_once_in_init_not_once_per_swap(self):
        """The plan requires "correctly initialized interactive controls
        after every modal load/reload, with no duplicate initialization/
        listeners" — the fix must attach the listener exactly once, in
        init(), not inside any per-swap path (openR3Section/openR3Panel only
        ever call htmx.ajax, never touch addEventListener)."""
        self.assertEqual(
            self.editor.count("if (!evt.target.matches('#sfbR3ModalBody form[data-sfb-autosave=\"true\"]')) return;"),
            1,
        )


class R3ModalSaveContractTests(SimpleTestCase):
    """Task 4 — three regressions for the unified save contract."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.root = Path(settings.BASE_DIR)

    def read(self, rel):
        return (self.root / rel).read_text(encoding="utf-8")

    def setUp(self):
        self.editor = self.read(
            "apps/storefront_builder/templates/dashboard/storefront_builder/editor.html"
        )
        self.modal = self.read(
            "apps/storefront_builder/templates/dashboard/storefront_builder/partials/r3_edit_modal.html"
        )

    def _save_fn_body(self):
        start = self.editor.index("async saveActiveR3Settings(")
        end = self.editor.index("\n    reloadPreview()", start)
        return self.editor[start:end]

    def test_inner_save_persists_and_keeps_modal_open(self):
        """«ذخیره تنظیمات»: save و modal باز بماند."""
        self.assertIn(
            "this.saveActiveR3Settings({ closeOnSuccess: false })", self.editor,
            "the inner submit must call the shared save with closeOnSuccess=false",
        )
        body = self._save_fn_body()
        # closeR3Modal() must only ever be reached inside an
        # `if (closeOnSuccess)` guard — never unconditionally.
        for line in body.splitlines():
            if "closeR3Modal()" in line:
                self.assertIn("closeOnSuccess", line, f"unconditional modal close found: {line!r}")

    def test_done_persists_waits_for_success_then_closes_and_refreshes(self):
        """«انجام شد»: همان فرم را save کند، صبر کند تا موفقیت، سپس ببندد و
        preview را refresh کند."""
        self.assertIn(
            '@click="saveActiveR3Settings({ closeOnSuccess: true })"', self.modal,
            "Done must delegate to the same shared save operation, not an "
            "independent close-without-saving path",
        )
        self.assertNotIn('@click="closeR3Modal(); reloadPreview()"', self.modal)
        body = self._save_fn_body()
        # closeOnSuccess must gate the close, and the close must be inside
        # the success branch (after a successful postFormAjax), not before.
        ok_branch = body.index("if (ok) {")
        close_call = body.index("if (closeOnSuccess) this.closeR3Modal();")
        self.assertGreater(close_call, ok_branch, "Done must only close after a successful save")

    def test_error_response_keeps_modal_open_and_shows_error(self):
        """روی validation/server error، modal بسته نشود و خطا نمایش داده شود."""
        body = self._save_fn_body()
        self.assertIn("this.r3Error = ", body)
        # Neither failure branch (validation nor network) may call closeR3Modal().
        failure_section = body[body.index("const html = await response.text();"):]
        self.assertNotIn("closeR3Modal()", failure_section)
        self.assertIn('x-show="r3Error"', self.modal)

    def test_double_submit_is_guarded(self):
        self.assertIn("if (this.r3SaveBusy) return false;", self.editor)
        self.assertIn("this.r3SaveBusy = true;", self.editor)
        self.assertIn("this.r3SaveBusy = false;", self.editor)
        self.assertIn(':disabled="r3SaveBusy"', self.modal)

    def test_no_second_independent_persistence_implementation(self):
        """Both the R2 sidebar autosave and the R3 modal save must funnel
        through the same low-level POST helper — not two copies of the
        fetch/FormData/redirect-detection logic."""
        self.assertEqual(self.editor.count("async function postFormAjax(form)"), 1)
        self.assertIn("await postFormAjax(form)", self._save_fn_body())
        autosave_start = self.editor.index("async autosaveInspectorForm(form)")
        autosave_body = self.editor[autosave_start:autosave_start + 800]
        self.assertIn("await postFormAjax(form)", autosave_body)
        # The old duplicated inline fetch call must be gone from autosave.
        self.assertNotIn("new FormData(form)", autosave_body)
