import hashlib
import shutil
import tempfile
from io import StringIO
from pathlib import Path
from unittest import mock

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings
from PIL import Image

from apps.catalog.models import Brand, Category, ProductImage
from apps.content.models import HeroSlide, PromotionalBanner, StoryRailItem
from apps.core.models import ShopSettings
from apps.stores.management.commands import refresh_rasti_mode_demo_visuals as refresh_command
from apps.stores.management.commands.refresh_rasti_mode_demo_visuals import Command
from apps.stores.models import Store


STORE_SLUG = "rasti-mode-demo"


def _field_digest(field_file):
    field_file.open("rb")
    try:
        return hashlib.sha256(field_file.read()).hexdigest()
    finally:
        field_file.close()


@override_settings(DEBUG=True)
class RefreshRastiModeDemoVisualsCommandTests(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._media_root = tempfile.mkdtemp()
        cls._media_override = override_settings(MEDIA_ROOT=cls._media_root)
        cls._media_override.enable()

    @classmethod
    def tearDownClass(cls):
        cls._media_override.disable()
        shutil.rmtree(cls._media_root, ignore_errors=True)
        super().tearDownClass()

    def setUp(self):
        call_command("seed_ready_template_fashion_demo", stdout=StringIO())
        self.store = Store.objects.get(slug=STORE_SLUG)

    def _refresh(self):
        out = StringIO()
        try:
            call_command("refresh_rasti_mode_demo_visuals", stdout=out)
        except CommandError as exc:
            self.fail(f"refresh_rasti_mode_demo_visuals must execute successfully: {exc}")
        return out.getvalue()

    def test_refresh_applies_curated_branding_and_all_non_product_media(self):
        product_before = list(
            ProductImage.objects.filter(product__store=self.store)
            .order_by("pk")
            .values_list("pk", "image")
        )

        output = self._refresh()

        self.store.refresh_from_db()
        shop = ShopSettings.objects.get(store=self.store)
        self.assertEqual(self.store.name, "فروشگاه پوشاک تستی راستی سی")
        self.assertEqual(shop.name, "فروشگاه پوشاک تستی راستی سی")
        self.assertTrue(shop.logo)
        self.assertTrue(shop.favicon)

        heroes = HeroSlide.objects.filter(store=self.store, section__isnull=True).order_by("display_order", "id")
        self.assertGreaterEqual(heroes.count(), 4)
        for hero in heroes[:4]:
            self.assertTrue(hero.desktop_image)
            self.assertTrue(hero.mobile_image)

        banners = PromotionalBanner.objects.filter(store=self.store, section__isnull=True).order_by("display_order", "id")
        self.assertGreaterEqual(banners.count(), 6)
        for banner in banners[:6]:
            self.assertTrue(banner.desktop_image)
            self.assertTrue(banner.mobile_image)

        self.assertEqual(Category.objects.filter(store=self.store, image="").count(), 0)
        self.assertEqual(Brand.objects.filter(store=self.store, logo="").count(), 0)
        self.assertEqual(StoryRailItem.objects.filter(store=self.store, section__isnull=True, image="").count(), 0)

        product_after = list(
            ProductImage.objects.filter(product__store=self.store)
            .order_by("pk")
            .values_list("pk", "image")
        )
        self.assertEqual(product_after, product_before)
        self.assertIn("product images: untouched", output)

    def test_second_run_is_content_idempotent(self):
        self._refresh()
        shop = ShopSettings.objects.get(store=self.store)
        hero = HeroSlide.objects.filter(store=self.store, section__isnull=True).order_by("display_order", "id").first()
        category = Category.objects.filter(store=self.store).order_by("order", "id").first()
        brand = Brand.objects.filter(store=self.store).order_by("sort_order", "id").first()
        first = {
            "logo": _field_digest(shop.logo),
            "hero": _field_digest(hero.desktop_image),
            "category": _field_digest(category.image),
            "brand": _field_digest(brand.logo),
            "hero_count": HeroSlide.objects.filter(store=self.store, section__isnull=True).count(),
            "banner_count": PromotionalBanner.objects.filter(store=self.store, section__isnull=True).count(),
            "story_count": StoryRailItem.objects.filter(store=self.store, section__isnull=True).count(),
        }

        self._refresh()
        shop.refresh_from_db(); hero.refresh_from_db(); category.refresh_from_db(); brand.refresh_from_db()
        second = {
            "logo": _field_digest(shop.logo),
            "hero": _field_digest(hero.desktop_image),
            "category": _field_digest(category.image),
            "brand": _field_digest(brand.logo),
            "hero_count": HeroSlide.objects.filter(store=self.store, section__isnull=True).count(),
            "banner_count": PromotionalBanner.objects.filter(store=self.store, section__isnull=True).count(),
            "story_count": StoryRailItem.objects.filter(store=self.store, section__isnull=True).count(),
        }
        self.assertEqual(second, first)

    def test_other_store_is_never_modified(self):
        other = Store.objects.create(name="Other", slug="other-demo-safe", admin_subdomain="other-demo-safe")
        other_shop = ShopSettings.provision_for(other)
        other_shop.name = "Other Shop"
        other_shop.save(update_fields=["name", "updated_at"])

        self._refresh()

        other.refresh_from_db(); other_shop.refresh_from_db()
        self.assertEqual(other.name, "Other")
        self.assertEqual(other_shop.name, "Other Shop")

    def test_manifest_asset_paths_cannot_escape_the_curated_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            curated_dir = Path(directory) / "curated"
            curated_dir.mkdir()
            inside_image = curated_dir / "inside.png"
            outside_image = curated_dir.parent / "outside.png"
            Image.new("RGB", (1, 1)).save(inside_image)
            Image.new("RGB", (1, 1)).save(outside_image)
            manifest = {
                "branding": {"logo": "inside.png", "favicon": "inside.png"},
                "heroes": [],
                "banners": [],
                "categories": {},
                "brands": {},
            }

            with mock.patch.object(refresh_command, "CURATED_DIR", curated_dir):
                Command()._validate_assets(manifest)
                for escaped_path in ("../outside.png", str(outside_image.resolve())):
                    with self.subTest(escaped_path=escaped_path):
                        manifest["branding"]["logo"] = escaped_path
                        with self.assertRaisesRegex(CommandError, "outside the curated directory"):
                            Command()._validate_assets(manifest)
