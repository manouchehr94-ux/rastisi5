"""خانواده‌ی چهارم — Heritage Premium (مرجع Cactus Leather). این خانواده
تنها موردی است که دو حالتِ Renderer کارت دارد (تصمیمِ مالک Q-09) —
تست‌های ``card_mode`` مخصوصِ همین فایل‌اند."""

from decimal import Decimal

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.storefront_builder import family_registry, preset_registry, section_registry
from apps.storefront_builder.services import layout_service as svc
from apps.stores.models import Store, StoreDomain


def _akhlaghi():
    return Store.objects.get(slug="akhlaghi")


class HeritagePremiumRegistryTests(TestCase):
    def test_registered_with_two_card_variants(self):
        family = family_registry.get_family("heritage_premium")
        self.assertIsNotNone(family)
        self.assertEqual(family.product_card_variant, "catalog/partials/product_cards/premium_portrait.html")
        self.assertEqual(family.product_card_campaign_variant, "catalog/partials/product_cards/premium_campaign.html")

    def test_default_preset_registered(self):
        family = family_registry.get_family("heritage_premium")
        preset = preset_registry.get_preset(family.default_preset_slug)
        self.assertIsNotNone(preset)
        self.assertEqual(preset.family_slug, "heritage_premium")

    def test_other_families_have_no_campaign_variant(self):
        for slug in ("modern_fashion", "artisan_editorial", "nordic_living"):
            family = family_registry.get_family(slug)
            self.assertIsNone(family.product_card_campaign_variant, f"{slug} should not have a campaign card mode")


class ProductSectionCardModeTests(TestCase):
    def test_default_card_mode_when_absent(self):
        cleaned = section_registry._validate_product_section_settings({"data_source": "newest"})
        self.assertEqual(cleaned["card_mode"], "default")

    def test_invalid_card_mode_falls_back_to_default(self):
        cleaned = section_registry._validate_product_section_settings({"data_source": "newest", "card_mode": "not-a-real-mode"})
        self.assertEqual(cleaned["card_mode"], "default")

    def test_campaign_card_mode_accepted(self):
        cleaned = section_registry._validate_product_section_settings({"data_source": "newest", "card_mode": "campaign"})
        self.assertEqual(cleaned["card_mode"], "campaign")


@override_settings(ALLOWED_HOSTS=["sfb-hp-public.example.com", "testserver"])
class HeritagePremiumPublicRenderingTests(TestCase):
    def setUp(self):
        cache.clear()
        self.store = _akhlaghi()
        StoreDomain.objects.create(
            store=self.store, hostname="sfb-hp-public.example.com", is_primary=True,
            verification_status=StoreDomain.VerificationStatus.VERIFIED, verified_at=timezone.now(),
        )

    def _publish_with_family(self):
        draft = svc.get_or_create_draft(self.store)
        draft.appearance_config = svc.validate_appearance_config({
            "family_slug": "heritage_premium", "preset_slug": "heritage_premium_default",
        })
        draft.save(update_fields=["appearance_config"])
        svc.publish(self.store)
        return draft

    def test_family_selected_renders_family_header(self):
        self._publish_with_family()
        resp = self.client.get(reverse("catalog:home"), HTTP_HOST="sfb-hp-public.example.com")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "hp-header")
        self.assertContains(resp, 'data-sfb-family="heritage_premium"')

    def test_product_detail_renders_family_composition(self):
        from apps.catalog.models import Category, Product, Vendor

        self._publish_with_family()
        category = Category.objects.create(store=self.store, name="چرم", slug="hp-cat")
        vendor = Vendor.objects.create(store=self.store, name="کارگاه چرم", slug="hp-vendor")
        product = Product.objects.create(
            store=self.store, vendor=vendor, category=category, name="کیف چرمی نمونه",
            slug="hp-test-product", sku="HP-TEST-1", price=Decimal("1500000"),
        )
        resp = self.client.get(reverse("catalog:product-detail", args=[product.slug]), HTTP_HOST="sfb-hp-public.example.com")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "hp-pdp")

    def test_product_card_uses_portrait_mode_by_default(self):
        from apps.catalog.models import Category, Product, Vendor

        self._publish_with_family()
        category = Category.objects.create(store=self.store, name="کفش", slug="hp-cat-2")
        vendor = Vendor.objects.create(store=self.store, name="کارگاه", slug="hp-vendor-2")
        Product.objects.create(
            store=self.store, vendor=vendor, category=category, name="کفش رسمی نمونه",
            slug="hp-shoe-1", sku="HP-SHOE-1", price=Decimal("2000000"), discount_percent=20,
        )
        resp = self.client.get(reverse("catalog:home"), HTTP_HOST="sfb-hp-public.example.com")
        self.assertContains(resp, "hp-card")
        self.assertNotContains(resp, "hp-campaign-overlay")

    def test_product_card_campaign_mode_when_section_requests_it(self):
        from apps.catalog.models import Category, Product, Vendor
        from apps.storefront_builder.models import StorefrontSection

        draft = self._publish_with_family()
        category = Category.objects.create(store=self.store, name="اکسسوری", slug="hp-cat-3")
        vendor = Vendor.objects.create(store=self.store, name="کارگاه", slug="hp-vendor-3")
        Product.objects.create(
            store=self.store, vendor=vendor, category=category, name="اکسسوری چرمی نمونه",
            slug="hp-acc-1", sku="HP-ACC-1", price=Decimal("500000"), discount_percent=15,
        )
        draft = svc.get_or_create_draft(self.store)
        StorefrontSection.objects.create(
            version=draft, section_key="product_section", order=99,
            settings={"data_source": "newest", "item_limit": 8, "display_mode": "grid", "card_mode": "campaign"},
        )
        svc.publish(self.store)
        resp = self.client.get(reverse("catalog:home"), HTTP_HOST="sfb-hp-public.example.com")
        self.assertContains(resp, "hp-campaign-overlay")
