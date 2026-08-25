"""Real Ready Template Gallery screenshots — «Rasti Mode Demo — COMPLETE
REAL CATALOG + MEDIA + CONTENT + ALL 8 READY TEMPLATE REAL PREVIEWS»
mission (Steps 20-30).

This file tests the NEW real-screenshot resolution layer added to
``template_preview_service.py`` (``resolve_real_screenshot``,
``preview_content_hash``) and its Gallery-view integration — it does NOT
modify or duplicate ``test_acceptance_batch3.py``, whose 15 tests (the
pure-SVG schematic contract and the full no-mutation contract) must keep
passing byte-for-byte unchanged; see that file's own docstring.

The actual capture tool
(``apps.storefront_builder.management.commands.capture_ready_template_previews``)
is a dev/build-time-only script that requires a real running server and a
real browser — it is exercised manually (see the execution ledger for the
real capture run's evidence), not by this automated suite. What IS tested
here automatically:
  - the resolver's pure-filesystem contract (fresh vs. stale vs. missing)
  - that a normal Gallery request never imports/touches Playwright
  - that the currently-committed real screenshots (if present) satisfy
    the mission's structural requirements (one per official Template,
    correctly keyed, sourced from the Rasti Mode Demo capture workflow)
"""

import json
from pathlib import Path
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.storefront_builder import layout_preset_registry as lpr
from apps.storefront_builder.services import template_preview_service as tps
from apps.stores.models import Store, StoreDomain, StoreMembership

User = get_user_model()

ADMIN_HOST = "sfb-real-previews.rastisi.localhost"
READY_TEMPLATE_KEYS = (
    "dense_marketplace", "premium_leather", "warm_boutique", "fashion_promo_catalog",
    "playful_lifestyle", "utility_catalog", "editorial_jewelry", "dark_digital",
)


def _akhlaghi():
    return Store.objects.get(slug="akhlaghi")


class RealScreenshotResolverTests(TestCase):
    """Pure filesystem-contract tests — no HTTP, no browser."""

    def test_exact_official_template_count_is_8(self):
        self.assertEqual({p.key for p in lpr.list_ready_templates()}, set(READY_TEMPLATE_KEYS))

    def test_missing_screenshot_falls_back_to_none(self):
        preset = lpr.get_layout_preset("dense_marketplace")
        with mock.patch.object(Path, "is_file", return_value=False):
            self.assertIsNone(tps.resolve_real_screenshot(preset))

    def test_stale_content_hash_is_rejected_not_silently_served(self):
        """Mission Step 24: 'do NOT silently show an old version
        screenshot' — a mismatched stored hash must safely refuse the
        file, never serve it as if it were current."""
        preset = lpr.get_layout_preset("dense_marketplace")
        real_relpath = tps.screenshot_relpath(preset.key)
        real_image_path = tps.APP_STATIC_DIR / real_relpath

        with mock.patch.object(Path, "is_file", return_value=True), \
             mock.patch("apps.storefront_builder.services.template_preview_service.json.loads",
                        return_value={"content_hash": "definitely-not-the-real-hash"}), \
             mock.patch.object(Path, "read_text", return_value="{}"):
            result = tps.resolve_real_screenshot(preset)
        self.assertIsNone(result)

    def test_matching_content_hash_resolves_the_expected_relpath(self):
        preset = lpr.get_layout_preset("dense_marketplace")
        expected_relpath = tps.screenshot_relpath(preset.key)
        real_hash = tps.preview_content_hash(preset)

        with mock.patch.object(Path, "is_file", return_value=True), \
             mock.patch.object(Path, "read_text", return_value=json.dumps({"content_hash": real_hash})):
            result = tps.resolve_real_screenshot(preset)
        self.assertEqual(result, expected_relpath)

    def test_content_hash_changes_when_a_screenshot_visible_field_changes(self):
        preset = lpr.get_layout_preset("dense_marketplace")
        original_hash = tps.preview_content_hash(preset)

        import copy
        mutated = copy.deepcopy(preset)
        mutated.appearance["density"] = "definitely-a-different-value"
        self.assertNotEqual(tps.preview_content_hash(mutated), original_hash)

    def test_content_hash_is_stable_across_repeated_calls(self):
        preset = lpr.get_layout_preset("warm_boutique")
        self.assertEqual(tps.preview_content_hash(preset), tps.preview_content_hash(preset))

    def test_screenshot_relpath_shape_matches_the_mission_spec(self):
        self.assertEqual(tps.screenshot_relpath("dense_marketplace", 1), "ready_template_previews/dense_marketplace/v1.webp")

    def test_resolve_real_screenshot_never_imports_playwright(self):
        """Structural proof of the no-browser-launch contract (Step 23) —
        the module may *mention* Playwright in prose (it documents the
        offline capture tool that produces the files it reads), but must
        contain no actual import statement for it, so a normal Gallery
        request cannot possibly trigger a browser launch."""
        import apps.storefront_builder.services.template_preview_service as module

        source = Path(module.__file__).read_text()
        for line in source.splitlines():
            stripped = line.strip()
            self.assertFalse(stripped.startswith("import playwright"), line)
            self.assertFalse(stripped.startswith("from playwright"), line)
            self.assertFalse(stripped.startswith("import selenium"), line)
            self.assertFalse(stripped.startswith("from selenium"), line)


class CommittedScreenshotIntegrityTests(TestCase):
    """If real screenshots have been captured and committed (the normal
    healthy state after running the capture command), verify they satisfy
    the mission's structural requirements. Skips gracefully if none are
    present yet (e.g. a fresh checkout before the first capture run)."""

    def _committed_keys(self):
        base = tps.APP_STATIC_DIR / "ready_template_previews"
        if not base.is_dir():
            return []
        return [p.name for p in base.iterdir() if p.is_dir()]

    def test_every_committed_screenshot_belongs_to_an_official_template(self):
        for key in self._committed_keys():
            self.assertIn(key, READY_TEMPLATE_KEYS, key)

    def test_every_committed_screenshot_has_a_meta_sidecar_from_rasti_mode_demo(self):
        keys = self._committed_keys()
        if not keys:
            self.skipTest("no real screenshots committed yet")
        for key in keys:
            meta_path = tps.APP_STATIC_DIR / tps.meta_relpath(key)
            self.assertTrue(meta_path.is_file(), key)
            meta = json.loads(meta_path.read_text())
            self.assertEqual(meta["template_key"], key)
            self.assertEqual(meta["capture_source"], "rasti-mode-demo")
            self.assertEqual(meta["viewport"], {"width": 1440, "height": 1100})

    def test_every_official_template_resolves_its_committed_screenshot_as_fresh(self):
        keys = self._committed_keys()
        if len(keys) < len(READY_TEMPLATE_KEYS):
            self.skipTest("not all 8 real screenshots are committed yet")
        for key in READY_TEMPLATE_KEYS:
            preset = lpr.get_layout_preset(key)
            self.assertIsNotNone(tps.resolve_real_screenshot(preset), key)


@override_settings(ALLOWED_HOSTS=[ADMIN_HOST, "testserver"])
class GalleryRealScreenshotIntegrationTests(TestCase):
    """HTTP-level integration — extends Batch 3's no-mutation contract to
    cover the new screenshot branch without touching that file."""

    def setUp(self):
        self.store = _akhlaghi()
        self.store.admin_subdomain = ADMIN_HOST.split(".")[0]
        self.store.save(update_fields=["admin_subdomain"])
        self.staff = User.objects.create_user(username="real_preview_owner", password="pass12345", is_staff=True)
        StoreMembership.objects.create(
            store=self.store, user=self.staff, role=StoreMembership.Role.OWNER,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )
        self.client = Client(HTTP_HOST=ADMIN_HOST)
        self.client.login(username="real_preview_owner", password="pass12345")
        self.url = reverse("dashboard:storefront-builder-templates")

    def test_gallery_page_never_imports_or_calls_playwright(self):
        """The whole request path (view + both preview-resolution
        branches) must be structurally incapable of launching a browser."""
        with mock.patch.dict("sys.modules", {"playwright": None, "playwright.sync_api": None}):
            response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)

    def test_every_card_renders_either_a_real_screenshot_or_the_svg_fallback(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        for card in response.context["template_cards"]:
            self.assertIn(card["thumbnail_kind"], ("screenshot", "svg"))
            if card["thumbnail_kind"] == "screenshot":
                self.assertTrue(card["thumbnail_url"])
                self.assertIn("ready_template_previews", card["thumbnail_url"])
            else:
                self.assertTrue(card["thumbnail_svg"].startswith("<svg"))

    def test_gallery_get_still_creates_no_version_history_with_real_screenshots_present(self):
        """Re-proves Batch 3's Test G under the new code path."""
        from apps.storefront_builder.services import layout_service as svc

        svc.get_or_create_draft(self.store)
        layout = svc.get_or_create_layout(self.store)
        versions_before = layout.versions.count()

        for _ in range(3):
            self.client.get(self.url)

        layout.refresh_from_db()
        self.assertEqual(layout.versions.count(), versions_before)

    def test_gallery_get_never_calls_apply_preset_with_screenshots_present(self):
        from apps.storefront_builder.services import layout_service as svc
        from apps.storefront_builder.services import preset_service

        svc.get_or_create_draft(self.store)
        with mock.patch.object(preset_service, "apply_preset") as mocked_apply, \
             mock.patch.object(preset_service, "apply_preset_with_checkpoint") as mocked_checkpoint:
            response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        mocked_apply.assert_not_called()
        mocked_checkpoint.assert_not_called()

    def test_screenshot_image_can_be_opened_larger_via_a_plain_non_mutating_link(self):
        """Mission Step 30: 'preview may open larger non-mutating view' —
        implemented as a plain <a href> to the static image itself (no
        view logic, so structurally non-mutating)."""
        response = self.client.get(self.url)
        content = response.content.decode()
        for card in response.context["template_cards"]:
            if card["thumbnail_kind"] == "screenshot":
                self.assertIn(f'href="{card["thumbnail_url"]}"', content)


class CaptureCommandSafetyTests(TestCase):
    """The capture tool itself is dev/build-only and cannot be exercised
    end-to-end here (needs a real server + real browser), but its safety
    contract (fixed store slug, no CLI redirection) is structurally
    verifiable from its source, exactly like the seed command's own
    reset-safety tests."""

    def test_capture_command_hardcodes_the_demo_store_slug(self):
        import apps.storefront_builder.management.commands.capture_ready_template_previews as cmd

        self.assertEqual(cmd.STORE_SLUG, "rasti-mode-demo")

    def test_capture_command_exposes_no_store_targeting_argument(self):
        from apps.storefront_builder.management.commands.capture_ready_template_previews import Command

        parser = Command().create_parser("manage.py", "capture_ready_template_previews")
        dest_names = {action.dest for action in parser._actions}
        self.assertNotIn("store", dest_names)
        self.assertNotIn("store_slug", dest_names)
        self.assertNotIn("slug", dest_names)

    def test_capture_command_errors_clearly_when_demo_store_missing(self):
        from io import StringIO

        from django.core.management import CommandError, call_command

        Store.objects.filter(slug="rasti-mode-demo").delete()
        with self.assertRaises(CommandError):
            call_command("capture_ready_template_previews", stdout=StringIO())
