import json
from pathlib import Path
import unittest

from PIL import Image


BASE = Path(__file__).resolve().parents[1] / "demo_assets" / "rasti_mode_demo" / "curated"
MANIFEST = BASE / "manifest.json"


class CuratedVisualAssetContractTests(unittest.TestCase):
    def _manifest(self):
        self.assertTrue(MANIFEST.is_file(), "curated visual manifest is missing")
        return json.loads(MANIFEST.read_text(encoding="utf-8"))

    def test_manifest_has_exact_demo_identity_and_counts(self):
        data = self._manifest()
        self.assertEqual(data["schema_version"], 1)
        self.assertEqual(data["store"]["slug"], "rasti-mode-demo")
        self.assertEqual(data["store"]["display_name"], "فروشگاه پوشاک تستی راستی سی")
        self.assertEqual(len(data["heroes"]), 4)
        self.assertEqual(len(data["banners"]), 6)
        self.assertEqual(len(data["categories"]), 10)
        self.assertEqual(len(data["brands"]), 6)

    def test_all_manifest_assets_exist_are_small_and_decodable(self):
        data = self._manifest()
        rel_paths = {
            data["branding"]["logo"],
            data["branding"]["favicon"],
        }
        for hero in data["heroes"]:
            rel_paths.update((hero["desktop"], hero["mobile"]))
        for banner in data["banners"]:
            rel_paths.update((banner["desktop"], banner["mobile"]))
        rel_paths.update(data["categories"].values())
        rel_paths.update(data["brands"].values())

        for rel_path in sorted(rel_paths):
            path = BASE / rel_path
            self.assertTrue(path.is_file(), rel_path)
            self.assertLess(path.stat().st_size, 5 * 1024 * 1024, rel_path)
            with Image.open(path) as img:
                img.verify()

    def test_hero_and_banner_dimensions_are_template_friendly(self):
        data = self._manifest()
        for hero in data["heroes"]:
            with Image.open(BASE / hero["desktop"]) as img:
                self.assertEqual(img.size, (1600, 700))
            with Image.open(BASE / hero["mobile"]) as img:
                self.assertEqual(img.size, (900, 1200))
        for banner in data["banners"]:
            with Image.open(BASE / banner["desktop"]) as img:
                self.assertEqual(img.size, (1200, 500))
            with Image.open(BASE / banner["mobile"]) as img:
                self.assertEqual(img.size, (900, 900))

    def test_category_and_brand_assets_are_consistent(self):
        data = self._manifest()
        for rel_path in data["categories"].values():
            with Image.open(BASE / rel_path) as img:
                self.assertEqual(img.size, (900, 900))
        for rel_path in data["brands"].values():
            with Image.open(BASE / rel_path) as img:
                self.assertEqual(img.size, (720, 360))


if __name__ == "__main__":
    unittest.main()
