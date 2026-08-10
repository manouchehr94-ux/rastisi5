"""خانواده‌ی پنجم و آخر — Vibrant Catalog (مرجع Beraito)."""

from decimal import Decimal

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.storefront_builder import family_registry, preset_registry
from apps.storefront_builder.services import layout_service as svc
from apps.stores.models import Store, StoreDomain


def _akhlaghi():
    return Store.objects.get(slug="akhlaghi")


class VibrantCatalogRegistryTests(TestCase):
    def test_registered_with_matching_default_preset(self):
        family = family_registry.get_family("vibrant_catalog")
        self.assertIsNotNone(family)
        preset = preset_registry.get_preset(family.default_preset_slug)
        self.assertIsNotNone(preset)
        self.assertEqual(preset.family_slug, "vibrant_catalog")

    def test_all_five_families_registered(self):
        """رگرسیونِ پنج Familyِ اصلی — این تست فقط باید ثابت کند این پنج
        اسلاگِ اصلی هنوز در Registry حضور دارند (subset)، نه این‌که Registry
        دقیقاً همین پنج مورد را دارد و هیچ‌چیزِ دیگری اضافه نشده. با افزودنِ
        شش Familyِ جدید (atlas_catalog، ava_fashion، toranj_gifting،
        sarv_stock، sepidar_handmade، zarrin_jewelry) به Registry، مجموعِ
        کلی حالا ۱۱ عضو دارد — این افزایش، تصمیمِ محصولیِ عمدی است، نه یک
        رگرسیون. ادعایِ «دقیقاً ۱۱ Family» جای دیگری (در
        ``test_eleven_families.py::ElevenFamilyRegistryTests.test_exactly_11_families``)
        صاحبِ خودش را دارد؛ این تست فقط باید مطمئن شود پنج Familyِ اصلی هنوز
        حذف/تغییرنام/ادغام نشده‌اند."""
        slugs = {f.slug for f in family_registry.list_families()}
        original_five = {
            "modern_fashion", "artisan_editorial", "nordic_living",
            "heritage_premium", "vibrant_catalog",
        }
        self.assertTrue(
            original_five.issubset(slugs),
            f"یکی یا چند مورد از پنج Familyِ اصلی از Registry حذف شده‌اند: {original_five - slugs}",
        )


@override_settings(ALLOWED_HOSTS=["sfb-vc-public.example.com", "testserver"])
class VibrantCatalogPublicRenderingTests(TestCase):
    def setUp(self):
        cache.clear()
        self.store = _akhlaghi()
        StoreDomain.objects.create(
            store=self.store, hostname="sfb-vc-public.example.com", is_primary=True,
            verification_status=StoreDomain.VerificationStatus.VERIFIED, verified_at=timezone.now(),
        )

    def test_family_selected_renders_family_header_and_card(self):
        draft = svc.get_or_create_draft(self.store)
        draft.appearance_config = svc.validate_appearance_config({
            "family_slug": "vibrant_catalog", "preset_slug": "vibrant_catalog_default",
        })
        draft.save(update_fields=["appearance_config"])
        svc.publish(self.store)
        resp = self.client.get(reverse("catalog:home"), HTTP_HOST="sfb-vc-public.example.com")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "vc-header")
        self.assertContains(resp, 'data-sfb-family="vibrant_catalog"')

    def test_product_detail_renders_family_composition(self):
        from apps.catalog.models import Category, Product, Vendor

        draft = svc.get_or_create_draft(self.store)
        draft.appearance_config = svc.validate_appearance_config({
            "family_slug": "vibrant_catalog", "preset_slug": "vibrant_catalog_default",
        })
        draft.save(update_fields=["appearance_config"])
        svc.publish(self.store)
        category = Category.objects.create(store=self.store, name="لوازم تحریر", slug="vc-cat")
        vendor = Vendor.objects.create(store=self.store, name="فروشنده", slug="vc-vendor")
        product = Product.objects.create(
            store=self.store, vendor=vendor, category=category, name="ست نوشت‌افزار نمونه",
            slug="vc-test-product", sku="VC-TEST-1", price=Decimal("120000"),
        )
        resp = self.client.get(reverse("catalog:product-detail", args=[product.slug]), HTTP_HOST="sfb-vc-public.example.com")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "vc-pdp")

    def test_hero_with_no_slides_renders_nothing_without_error(self):
        """اگر مرچنت هنوز هیچ Hero Slide ای نساخته، Promo Dashboard باید
        بی‌صدا خالی بماند — نه خطا، نه تایلِ ساختگی."""
        draft = svc.get_or_create_draft(self.store)
        draft.appearance_config = svc.validate_appearance_config({
            "family_slug": "vibrant_catalog", "preset_slug": "vibrant_catalog_default",
        })
        draft.save(update_fields=["appearance_config"])
        svc.publish(self.store)
        resp = self.client.get(reverse("catalog:home"), HTTP_HOST="sfb-vc-public.example.com")
        self.assertEqual(resp.status_code, 200)
        self.assertNotContains(resp, "vc-deal-main")
