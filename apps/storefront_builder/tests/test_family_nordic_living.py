"""خانواده‌ی سوم — Nordic Living (مرجع IkalaJam)."""

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


class NordicLivingRegistryTests(TestCase):
    def test_registered_with_matching_default_preset(self):
        family = family_registry.get_family("nordic_living")
        self.assertIsNotNone(family)
        preset = preset_registry.get_preset(family.default_preset_slug)
        self.assertIsNotNone(preset)
        self.assertEqual(preset.family_slug, "nordic_living")


class ProductSecondaryImageTests(TestCase):
    """``Product.secondary_image`` — پیش‌نیازِ داده‌ایِ Crossfadeِ کارتِ این خانواده (Q-13)."""

    def setUp(self):
        from apps.catalog.models import Category, Product, ProductImage, Vendor

        self.store = _akhlaghi()
        category = Category.objects.create(store=self.store, name="دکور آزمایشی", slug="nl-test-cat")
        vendor = Vendor.objects.create(store=self.store, name="فروشنده آزمایشی", slug="nl-test-vendor")
        self.single_image_product = Product.objects.create(
            store=self.store, vendor=vendor, category=category, name="محصول تک‌تصویری",
            slug="nl-single-image", sku="NL-1", price=Decimal("10000"),
        )
        ProductImage.objects.create(product=self.single_image_product, image="products/gallery/a.jpg", is_cover=True)

        self.two_image_product = Product.objects.create(
            store=self.store, vendor=vendor, category=category, name="محصول دوتصویری",
            slug="nl-two-images", sku="NL-2", price=Decimal("10000"),
        )
        ProductImage.objects.create(product=self.two_image_product, image="products/gallery/b1.jpg", is_cover=True, order=0)
        self.second = ProductImage.objects.create(product=self.two_image_product, image="products/gallery/b2.jpg", is_cover=False, order=1)

    def test_single_image_product_has_no_secondary_image(self):
        self.assertIsNone(self.single_image_product.secondary_image)

    def test_two_image_product_secondary_image_is_the_non_cover_one(self):
        self.assertEqual(self.two_image_product.secondary_image.pk, self.second.pk)


@override_settings(ALLOWED_HOSTS=["sfb-nl-public.example.com", "testserver"])
class NordicLivingPublicRenderingTests(TestCase):
    def setUp(self):
        cache.clear()
        self.store = _akhlaghi()
        StoreDomain.objects.create(
            store=self.store, hostname="sfb-nl-public.example.com", is_primary=True,
            verification_status=StoreDomain.VerificationStatus.VERIFIED, verified_at=timezone.now(),
        )

    def test_family_selected_renders_family_header_and_card(self):
        draft = svc.get_or_create_draft(self.store)
        draft.appearance_config = svc.validate_appearance_config({
            "family_slug": "nordic_living", "preset_slug": "nordic_living_default",
        })
        draft.save(update_fields=["appearance_config"])
        svc.publish(self.store)
        resp = self.client.get(reverse("catalog:home"), HTTP_HOST="sfb-nl-public.example.com")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "nl-header")
        self.assertContains(resp, 'data-sfb-family="nordic_living"')

    def test_product_detail_renders_family_composition(self):
        from apps.catalog.models import Category, Product, Vendor

        draft = svc.get_or_create_draft(self.store)
        draft.appearance_config = svc.validate_appearance_config({
            "family_slug": "nordic_living", "preset_slug": "nordic_living_default",
        })
        draft.save(update_fields=["appearance_config"])
        svc.publish(self.store)
        category = Category.objects.create(store=self.store, name="دکور", slug="nl-cat-2")
        vendor = Vendor.objects.create(store=self.store, name="فروشنده", slug="nl-vendor-2")
        product = Product.objects.create(
            store=self.store, vendor=vendor, category=category, name="کوسن نمونه",
            slug="nl-test-product-2", sku="NL-TEST-2", price=Decimal("150000"),
        )
        resp = self.client.get(reverse("catalog:product-detail", args=[product.slug]), HTTP_HOST="sfb-nl-public.example.com")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "nl-pdp")
