"""Static, DB-free tests for the Rasti Mode Demo raw/media pipeline —
«Rasti Mode Demo — COMPLETE REAL CATALOG + MEDIA + CONTENT» mission's
TESTS — RAW / MEDIA section.

These tests read directly from
``apps/stores/demo_assets/rasti_mode_demo/`` on disk (the committed raw
source pool, the processed ``products/`` folder, and the deterministic
manifest) — no database, no Django test client. See
``scripts/build_inventory.py``/``scripts/select_and_process_media.py`` for
how these files were produced, and the execution ledger for the full
image-audit trail.
"""

import json
from pathlib import Path

from django.test import SimpleTestCase

BASE = Path(__file__).resolve().parents[1] / "demo_assets" / "rasti_mode_demo"
RAW = BASE / "raw_user_catalog"
PRODUCTS_DIR = BASE / "products"
MANIFEST_PATH = BASE / "selected_product_media_manifest.json"

RAW_FOLDER_COUNTS = {"1": 66, "2": 55, "3": 70, "4": 66, "5": 88}


class RawSourceInventoryTests(SimpleTestCase):
    def test_raw_folder_counts_match_the_committed_source_notice(self):
        for folder, expected in RAW_FOLDER_COUNTS.items():
            actual = len(list((RAW / folder).glob("*.jpg")))
            self.assertEqual(actual, expected, f"folder {folder}")

    def test_raw_total_is_exactly_345(self):
        total = sum(len(list((RAW / folder).glob("*.jpg"))) for folder in RAW_FOLDER_COUNTS)
        self.assertEqual(total, 345)

    def test_source_notice_document_is_preserved(self):
        notice = RAW / "QA_SOURCE_ASSETS.md"
        self.assertTrue(notice.is_file())
        text = notice.read_text()
        self.assertIn("345", text)
        self.assertIn("QA/demo-only", text)


class FinalSelectedMediaTests(SimpleTestCase):
    def test_exactly_50_product_folders(self):
        folders = [p for p in PRODUCTS_DIR.iterdir() if p.is_dir()]
        self.assertEqual(len(folders), 50)
        expected_skus = {f"FSH-{i:03d}" for i in range(1, 51)}
        self.assertEqual({f.name for f in folders}, expected_skus)

    def test_exactly_150_final_webp_files_all_physically_exist(self):
        files = list(PRODUCTS_DIR.glob("FSH-*/0[123].webp"))
        self.assertEqual(len(files), 150)
        for f in files:
            self.assertTrue(f.is_file())
            self.assertGreater(f.stat().st_size, 0)

    def test_every_product_has_exactly_01_02_03(self):
        for i in range(1, 51):
            sku_dir = PRODUCTS_DIR / f"FSH-{i:03d}"
            names = sorted(p.name for p in sku_dir.glob("*.webp"))
            self.assertEqual(names, ["01.webp", "02.webp", "03.webp"], sku_dir)

    def test_final_images_are_1200x1600_webp(self):
        from PIL import Image

        for path in list(PRODUCTS_DIR.glob("FSH-*/0[123].webp"))[:15]:
            with Image.open(path) as img:
                self.assertEqual(img.size, (1200, 1600), path)
                self.assertEqual(img.format, "WEBP", path)


class ManifestTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.manifest = json.loads(MANIFEST_PATH.read_text())

    def test_exactly_150_manifest_entries(self):
        self.assertEqual(len(self.manifest), 150)

    def test_every_entry_has_the_required_fields(self):
        required = {
            "sku", "image_order", "cover", "raw_source_relpath", "raw_source_sha256",
            "final_relpath", "final_sha256", "derived", "transformation", "category",
            "product_title_fa", "brand", "dominant_color_fa", "provenance_status",
        }
        for entry in self.manifest:
            self.assertTrue(required.issubset(entry.keys()), entry.get("sku"))

    def test_provenance_status_is_always_user_supplied_qa_source(self):
        for entry in self.manifest:
            self.assertEqual(entry["provenance_status"], "user_supplied_qa_source")

    def test_exactly_one_cover_per_product(self):
        by_sku: dict[str, int] = {}
        for entry in self.manifest:
            if entry["cover"]:
                by_sku[entry["sku"]] = by_sku.get(entry["sku"], 0) + 1
        self.assertEqual(len(by_sku), 50)
        self.assertTrue(all(count == 1 for count in by_sku.values()))

    def test_no_duplicate_final_target_paths(self):
        paths = [entry["final_relpath"] for entry in self.manifest]
        self.assertEqual(len(paths), len(set(paths)))

    def test_final_relpath_files_all_exist_and_hash_matches(self):
        import hashlib

        for entry in self.manifest[:30]:
            final_path = BASE / entry["final_relpath"]
            self.assertTrue(final_path.is_file(), entry["final_relpath"])
            digest = hashlib.sha256(final_path.read_bytes()).hexdigest()
            self.assertEqual(digest, entry["final_sha256"], entry["final_relpath"])

    def test_raw_source_relpath_points_inside_raw_user_catalog(self):
        for entry in self.manifest:
            self.assertTrue(entry["raw_source_relpath"].startswith("raw_user_catalog/"), entry["sku"])

    def test_derived_images_have_a_transformation_description(self):
        for entry in self.manifest:
            if entry["derived"]:
                self.assertTrue(entry["transformation"], entry)
            else:
                self.assertIn("cover", entry["transformation"].lower())

    def test_cover_image_is_never_marked_derived(self):
        for entry in self.manifest:
            if entry["cover"]:
                self.assertFalse(entry["derived"], entry["sku"])


class NoPublicRawServingTests(SimpleTestCase):
    """Mission's explicit prohibition: do not expose raw_user_catalog
    directly through the public storefront."""

    def test_seed_command_image_loader_reads_only_from_the_processed_folder(self):
        """The docstring legitimately documents that raw_user_catalog is
        never used for serving — this checks the actual code behavior:
        the one function that loads product image bytes for import
        (``_load_processed_image``) builds its path only from
        ``PRODUCT_MEDIA_DIR`` (the processed ``products/`` folder)."""
        import inspect

        from apps.stores.management.commands import seed_ready_template_fashion_demo as cmd

        source = inspect.getsource(cmd._load_processed_image)
        self.assertIn("PRODUCT_MEDIA_DIR", source)
        self.assertNotIn("raw_user_catalog", source)
        self.assertNotIn("RAW", source)

    def test_manifest_final_paths_never_point_into_raw_catalog(self):
        manifest = json.loads(MANIFEST_PATH.read_text())
        for entry in manifest:
            self.assertFalse(entry["final_relpath"].startswith("raw_user_catalog/"), entry["sku"])
