"""خانواده‌ی دوم — Artisan Editorial (مرجع Deeyar). همان الگویِ
test_family_registry.py، فقط برایِ این خانواده."""

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.storefront_builder import family_registry, preset_registry
from apps.storefront_builder.services import layout_service as svc
from apps.stores.models import Store, StoreDomain


def _akhlaghi():
    return Store.objects.get(slug="akhlaghi")


class ArtisanEditorialRegistryTests(TestCase):
    def test_registered_with_matching_default_preset(self):
        family = family_registry.get_family("artisan_editorial")
        self.assertIsNotNone(family)
        preset = preset_registry.get_preset(family.default_preset_slug)
        self.assertIsNotNone(preset)
        self.assertEqual(preset.family_slug, "artisan_editorial")

    def test_default_preset_palette_is_real(self):
        from apps.storefront_builder import appearance_registry

        preset = preset_registry.get_preset("artisan_editorial_default")
        self.assertIsNotNone(appearance_registry.get_palette(preset.default_palette_slug))

    def test_validate_accepts_family_and_its_own_preset(self):
        cleaned = svc.validate_appearance_config({
            "family_slug": "artisan_editorial", "preset_slug": "artisan_editorial_default",
        })
        self.assertEqual(cleaned["family_slug"], "artisan_editorial")

    def test_modern_fashion_preset_rejected_for_this_family(self):
        with self.assertRaises(svc.AppearanceConfigValidationError):
            svc.validate_appearance_config({
                "family_slug": "artisan_editorial", "preset_slug": "modern_fashion_default",
            })


@override_settings(ALLOWED_HOSTS=["sfb-ae-public.example.com", "testserver"])
class ArtisanEditorialPublicRenderingTests(TestCase):
    def setUp(self):
        cache.clear()
        self.store = _akhlaghi()
        StoreDomain.objects.create(
            store=self.store, hostname="sfb-ae-public.example.com", is_primary=True,
            verification_status=StoreDomain.VerificationStatus.VERIFIED, verified_at=timezone.now(),
        )

    def test_family_selected_renders_family_header_and_card(self):
        draft = svc.get_or_create_draft(self.store)
        draft.appearance_config = svc.validate_appearance_config({
            "family_slug": "artisan_editorial", "preset_slug": "artisan_editorial_default",
        })
        draft.save(update_fields=["appearance_config"])
        svc.publish(self.store)
        resp = self.client.get(reverse("catalog:home"), HTTP_HOST="sfb-ae-public.example.com")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "ae-header")
        self.assertContains(resp, 'data-sfb-family="artisan_editorial"')

    def test_product_detail_renders_family_composition(self):
        from decimal import Decimal

        from apps.catalog.models import Category, Product, Vendor

        draft = svc.get_or_create_draft(self.store)
        draft.appearance_config = svc.validate_appearance_config({
            "family_slug": "artisan_editorial", "preset_slug": "artisan_editorial_default",
        })
        draft.save(update_fields=["appearance_config"])
        svc.publish(self.store)

        category = Category.objects.create(store=self.store, name="صنایع‌دستی", slug="ae-test-cat", icon="🏺")
        vendor = Vendor.objects.create(store=self.store, name="کارگاه", slug="ae-test-vendor")
        product = Product.objects.create(
            store=self.store, vendor=vendor, category=category, name="ظرف سفالی نمونه",
            slug="ae-test-product", sku="AE-TEST-1", price=Decimal("150000"),
        )
        resp = self.client.get(
            reverse("catalog:product-detail", args=[product.slug]), HTTP_HOST="sfb-ae-public.example.com",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "ae-pdp")
