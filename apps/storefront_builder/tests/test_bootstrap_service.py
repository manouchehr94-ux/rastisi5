from decimal import Decimal
from io import BytesIO

from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from PIL import Image

from apps.catalog.models import Category, Product, Vendor
from apps.content.models import HeroSlide, PromotionalBanner
from apps.storefront_builder.models import StorefrontLayoutVersion
from apps.storefront_builder.services import bootstrap_service, layout_service as svc
from apps.stores.models import Store


def _akhlaghi():
    return Store.objects.get(slug="akhlaghi")


def _img(name="test.png"):
    buf = BytesIO()
    Image.new("RGB", (800, 400), (100, 50, 200)).save(buf, "PNG")
    return SimpleUploadedFile(name, buf.getvalue(), content_type="image/png")


class BootstrapSectionsTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_minimal_store_gets_baseline_sections(self):
        sections = bootstrap_service.build_bootstrap_sections(_akhlaghi())
        keys = [s["section_key"] for s in sections]
        self.assertIn("category_grid", keys)
        self.assertIn("newest_products", keys)
        self.assertIn("best_sellers", keys)
        self.assertIn("trust_features", keys)
        self.assertNotIn("hero_banner", keys)
        self.assertNotIn("discounted_products", keys)

    def test_active_hero_slide_included(self):
        store = _akhlaghi()
        HeroSlide.objects.create(store=store, title="T", desktop_image=_img(), is_active=True)
        sections = bootstrap_service.build_bootstrap_sections(store)
        self.assertIn("hero_banner", [s["section_key"] for s in sections])

    def test_inactive_hero_slide_excluded(self):
        store = _akhlaghi()
        HeroSlide.objects.create(store=store, title="T", desktop_image=_img(), is_active=False)
        sections = bootstrap_service.build_bootstrap_sections(store)
        self.assertNotIn("hero_banner", [s["section_key"] for s in sections])

    def test_active_promo_banner_included_as_multi_banner(self):
        store = _akhlaghi()
        PromotionalBanner.objects.create(store=store, title="B", desktop_image=_img(), is_active=True)
        sections = bootstrap_service.build_bootstrap_sections(store)
        self.assertIn("multi_banner", [s["section_key"] for s in sections])

    def test_discounted_products_included_only_when_present(self):
        store = _akhlaghi()
        vendor = Vendor.objects.create(store=store, name="V", slug="v-boot")
        cat = Category.objects.create(store=store, name="C", slug="c-boot")
        Product.objects.create(
            store=store, vendor=vendor, category=cat, name="P", slug="p-boot",
            sku="SKU-BOOT", price=Decimal("1000"), stock=1, discount_percent=10,
        )
        sections = bootstrap_service.build_bootstrap_sections(store)
        self.assertIn("discounted_products", [s["section_key"] for s in sections])

    def test_sections_ordered_sequentially(self):
        store = _akhlaghi()
        HeroSlide.objects.create(store=store, title="T", desktop_image=_img(), is_active=True)
        sections = bootstrap_service.build_bootstrap_sections(store)
        orders = [s["order"] for s in sections]
        self.assertEqual(orders, list(range(len(orders))))


class BootstrapIntegrationWithDraftTests(TestCase):
    """اطمینان از این‌که اولین Draft هر فروشگاه هرگز خالی نیست."""

    def setUp(self):
        cache.clear()

    def test_first_draft_is_bootstrapped_not_empty(self):
        store = _akhlaghi()
        draft = svc.get_or_create_draft(store)
        self.assertEqual(draft.source, StorefrontLayoutVersion.Source.LEGACY_BOOTSTRAP)
        self.assertGreater(draft.sections.count(), 0)

    def test_second_draft_after_publish_is_manual_source_not_rebootstrapped(self):
        store = _akhlaghi()
        svc.get_or_create_draft(store)
        svc.publish(store)
        second_draft = svc.get_or_create_draft(store)
        self.assertEqual(second_draft.source, StorefrontLayoutVersion.Source.MANUAL)

    def test_flag_stays_false_until_explicit_publish(self):
        store = _akhlaghi()
        svc.get_or_create_draft(store)
        layout = svc.get_or_create_layout(store)
        self.assertFalse(layout.uses_visual_storefront_layout)
