from __future__ import annotations

import hashlib
import json
from pathlib import Path

from django.conf import settings
from django.core.files import File
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.catalog.models import Brand, Category
from apps.content.models import DestinationType, HeroSlide, PromotionalBanner, StoryRailItem
from apps.core.models import ShopSettings
from apps.stores.models import Store


STORE_SLUG = "rasti-mode-demo"
CURATED_DIR = Path(__file__).resolve().parents[2] / "demo_assets" / "rasti_mode_demo" / "curated"
MANIFEST_PATH = CURATED_DIR / "manifest.json"
MAX_MEDIA_BYTES = 5 * 1024 * 1024


def _sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sha256_field(field_file) -> str | None:
    if not field_file or not getattr(field_file, "name", ""):
        return None
    digest = hashlib.sha256()
    try:
        # Hash through an independent storage handle. Opening/closing the model's
        # FieldFile here leaves its internal file object closed, which makes the
        # subsequent ImageField validators fail on an idempotent second run.
        with field_file.storage.open(field_file.name, "rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
    except (FileNotFoundError, OSError, ValueError):
        return None


def _set_file_if_changed(instance, field_name: str, source_path: Path, filename: str) -> bool:
    field_file = getattr(instance, field_name)
    source_digest = _sha256_path(source_path)
    if _sha256_field(field_file) == source_digest:
        return False
    with source_path.open("rb") as handle:
        field_file.save(filename, File(handle), save=False)
    return True


def _clear_destination(instance) -> None:
    instance.destination_category = None
    instance.destination_product = None
    instance.destination_brand = None
    instance.destination_collection = None
    instance.destination_external_url = ""
    instance.open_in_new_tab = False


class Command(BaseCommand):
    help = (
        "Refresh only the non-product visual media of the isolated rasti-mode-demo store "
        "from committed curated RastiSi demo assets. ProductImage rows are never modified."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--check-only",
            action="store_true",
            help="Validate the curated asset pack and demo structure without changing database/media state.",
        )

    def _load_manifest(self) -> dict:
        if not MANIFEST_PATH.is_file():
            raise CommandError(f"Curated manifest is missing: {MANIFEST_PATH}")
        data = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        if data.get("schema_version") != 1:
            raise CommandError("Unsupported curated demo visual manifest schema_version")
        if data.get("store", {}).get("slug") != STORE_SLUG:
            raise CommandError("Curated manifest targets an unexpected Store slug")
        return data

    def _validate_assets(self, manifest: dict) -> None:
        rel_paths = {manifest["branding"]["logo"], manifest["branding"]["favicon"]}
        for hero in manifest["heroes"]:
            rel_paths.update((hero["desktop"], hero["mobile"]))
        for banner in manifest["banners"]:
            rel_paths.update((banner["desktop"], banner["mobile"]))
        rel_paths.update(manifest["categories"].values())
        rel_paths.update(manifest["brands"].values())

        from PIL import Image

        curated_root = CURATED_DIR.resolve()
        for rel_path in sorted(rel_paths):
            try:
                path = (CURATED_DIR / rel_path).resolve()
            except (OSError, TypeError, ValueError) as exc:
                raise CommandError(f"Invalid curated asset path: {rel_path}") from exc
            if not path.is_relative_to(curated_root):
                raise CommandError(f"Curated asset path is outside the curated directory: {rel_path}")
            if not path.is_file():
                raise CommandError(f"Curated asset is missing: {rel_path}")
            if path.stat().st_size > MAX_MEDIA_BYTES:
                raise CommandError(f"Curated asset exceeds 5 MiB: {rel_path}")
            try:
                with Image.open(path) as image:
                    image.verify()
            except Exception as exc:
                raise CommandError(f"Curated asset is not a valid image: {rel_path}") from exc

    def _require_structure(self, store: Store, manifest: dict) -> None:
        category_names = set(manifest["categories"])
        actual_categories = set(
            Category.objects.filter(store=store, name__in=category_names).values_list("name", flat=True)
        )
        if actual_categories != category_names:
            missing = sorted(category_names - actual_categories)
            raise CommandError(f"Demo categories are incomplete; run seed_ready_template_fashion_demo first. Missing: {missing}")

        brand_names = set(manifest["brands"])
        actual_brands = set(Brand.objects.filter(store=store, name__in=brand_names).values_list("name", flat=True))
        if actual_brands != brand_names:
            missing = sorted(brand_names - actual_brands)
            raise CommandError(f"Demo brands are incomplete; run seed_ready_template_fashion_demo first. Missing: {missing}")

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError("This demo-only visual refresh is disabled when DEBUG=False")

        manifest = self._load_manifest()
        self._validate_assets(manifest)

        store = Store.objects.filter(slug=STORE_SLUG).first()
        if store is None:
            raise CommandError("rasti-mode-demo does not exist; run seed_ready_template_fashion_demo first")
        self._require_structure(store, manifest)

        if options["check_only"]:
            self.stdout.write(self.style.SUCCESS("Curated visual pack: valid; demo structure: ready; no writes performed."))
            return

        counts = {"branding": 0, "heroes": 0, "banners": 0, "categories": 0, "brands": 0, "stories": 0}

        with transaction.atomic():
            # Store identity is intentionally demo-only; hostnames/slugs remain stable.
            display_name = manifest["store"]["display_name"]
            if store.name != display_name:
                store.name = display_name
                store.save(update_fields=["name", "updated_at"])

            shop = ShopSettings.provision_for(store)
            shop_changed = False
            for field_name, value in (
                ("name", display_name),
                ("tagline", manifest["store"]["tagline"]),
                ("description", manifest["store"]["description"]),
            ):
                if getattr(shop, field_name) != value:
                    setattr(shop, field_name, value)
                    shop_changed = True
            if _set_file_if_changed(shop, "logo", CURATED_DIR / manifest["branding"]["logo"], "rasti-mode-demo-logo.png"):
                shop_changed = True
            if _set_file_if_changed(shop, "favicon", CURATED_DIR / manifest["branding"]["favicon"], "rasti-mode-demo-favicon.png"):
                shop_changed = True
            if shop_changed:
                shop.save()
                counts["branding"] = 1

            for hero_data in manifest["heroes"]:
                order = hero_data["order"]
                hero = (
                    HeroSlide.objects.filter(store=store, section__isnull=True, display_order=order)
                    .order_by("id")
                    .first()
                )
                if hero is None:
                    hero = HeroSlide(store=store, section=None, display_order=order)
                hero.title = hero_data["title"]
                hero.subtitle = hero_data["subtitle"]
                hero.button_label = hero_data["button_label"]
                hero.show_button = True
                hero.is_active = True
                hero.display_order = order
                _clear_destination(hero)
                hero.destination_type = DestinationType.SEARCH
                _set_file_if_changed(hero, "desktop_image", CURATED_DIR / hero_data["desktop"], f"rasti-curated-hero-{order + 1}.webp")
                _set_file_if_changed(hero, "mobile_image", CURATED_DIR / hero_data["mobile"], f"rasti-curated-hero-{order + 1}-mobile.webp")
                hero.full_clean()
                hero.save()
                counts["heroes"] += 1

            for banner_data in manifest["banners"]:
                order = banner_data["order"]
                banner = (
                    PromotionalBanner.objects.filter(store=store, section__isnull=True, display_order=order)
                    .order_by("id")
                    .first()
                )
                if banner is None:
                    banner = PromotionalBanner(store=store, section=None, display_order=order)
                banner.title = banner_data["title"]
                banner.description = ""
                banner.button_label = ""
                banner.show_button = False
                banner.is_active = True
                banner.display_order = order
                _clear_destination(banner)
                banner.destination_type = DestinationType.SEARCH
                _set_file_if_changed(banner, "desktop_image", CURATED_DIR / banner_data["desktop"], f"rasti-curated-banner-{order + 1}.webp")
                _set_file_if_changed(banner, "mobile_image", CURATED_DIR / banner_data["mobile"], f"rasti-curated-banner-{order + 1}-mobile.webp")
                banner.full_clean()
                banner.save()
                counts["banners"] += 1

            category_by_name = {c.name: c for c in Category.objects.filter(store=store, name__in=manifest["categories"].keys())}
            for name, rel_path in manifest["categories"].items():
                category = category_by_name[name]
                if _set_file_if_changed(category, "image", CURATED_DIR / rel_path, f"rasti-{category.slug}.webp"):
                    category.save(update_fields=["image", "updated_at"])
                counts["categories"] += 1

            for name, rel_path in manifest["brands"].items():
                brand = Brand.objects.get(store=store, name=name)
                if _set_file_if_changed(brand, "logo", CURATED_DIR / rel_path, f"rasti-{brand.slug}.webp"):
                    brand.save(update_fields=["logo", "updated_at"])
                counts["brands"] += 1

            # Reuse category photography for the 10 category story-rail items.
            for order, (category_name, rel_path) in enumerate(manifest["categories"].items()):
                category = category_by_name[category_name]
                story = (
                    StoryRailItem.objects.filter(store=store, section__isnull=True, display_order=order)
                    .order_by("id")
                    .first()
                )
                if story is None:
                    story = StoryRailItem(store=store, section=None, display_order=order)
                story.title = category_name[:60]
                story.is_active = True
                story.display_order = order
                _clear_destination(story)
                story.destination_type = DestinationType.CATEGORY
                story.destination_category = category
                _set_file_if_changed(story, "image", CURATED_DIR / rel_path, f"rasti-curated-story-{order + 1}.webp")
                story.full_clean()
                story.save()
                counts["stories"] += 1

        self.stdout.write(self.style.SUCCESS(
            "Rasti Mode Demo curated visuals applied: "
            f"branding={counts['branding']}, heroes={counts['heroes']}, banners={counts['banners']}, "
            f"categories={counts['categories']}, brands={counts['brands']}, stories={counts['stories']}; "
            "product images: untouched."
        ))
