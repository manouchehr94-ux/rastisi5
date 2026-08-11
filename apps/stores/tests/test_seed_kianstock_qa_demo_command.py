"""Runtime tests for the local KianStock-shaped QA dataset.

The command intentionally re-creates public catalogue structure/facts with synthetic
local media; it never downloads third-party product/hero/testimonial images.
"""

import shutil
import tempfile
from io import StringIO

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.management import CommandError, call_command
from django.test import TestCase, override_settings

from apps.catalog.models import Brand, Category, MerchantCollection, MerchantCollectionItem, Product, ProductImage, ProductVariant
from apps.content.models import ContentPage, FooterSettings, HeroSlide, Menu, MenuItem, PromotionalBanner, SocialLink, StoryRailItem
from apps.core.models import ShopSettings
from apps.storefront_builder.models import StorefrontLayout
from apps.stores.models import Store, StoreDomain, StoreMembership

User = get_user_model()
STORE_SLUG = "kianstock-qa"


@override_settings(DEBUG=True)
class SeedKianstockQADemoTests(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._media_root = tempfile.mkdtemp(prefix="kianstock-qa-test-")
        cls._media_override = override_settings(MEDIA_ROOT=cls._media_root)
        cls._media_override.enable()

    @classmethod
    def tearDownClass(cls):
        cls._media_override.disable()
        shutil.rmtree(cls._media_root, ignore_errors=True)
        super().tearDownClass()

    def setUp(self):
        cache.clear()
        self.owner = User.objects.create_user(username="kianstock-qa-owner", password="pass12345")

    def _run(self, *extra):
        call_command(
            "seed_kianstock_qa_demo", "--owner-username", self.owner.username,
            *extra, stdout=StringIO(),
        )

    def _store(self):
        return Store.objects.get(slug=STORE_SLUG)

    def test_safety_gates(self):
        with override_settings(DEBUG=False):
            with self.assertRaises(CommandError):
                self._run()
        self.assertFalse(Store.objects.filter(slug=STORE_SLUG).exists())
        with self.assertRaises(CommandError):
            call_command("seed_kianstock_qa_demo", "--owner-username", "missing-owner", stdout=StringIO())
        self.assertFalse(User.objects.filter(username="missing-owner").exists())

    def test_store_identity_domain_membership_and_contacts(self):
        self._run()
        store = self._store()
        self.assertEqual(store.name, "کیان استوک")
        self.assertEqual(store.status, Store.Status.ACTIVE)
        domain = StoreDomain.objects.get(store=store, is_primary=True)
        self.assertEqual(domain.verification_status, StoreDomain.VerificationStatus.VERIFIED)
        self.assertTrue(domain.hostname.endswith(".rastisi.localhost"))
        membership = StoreMembership.objects.get(store=store, user=self.owner)
        self.assertEqual(membership.role, StoreMembership.Role.OWNER)
        self.assertEqual(membership.status, StoreMembership.MembershipStatus.ACTIVE)
        self.assertEqual(ShopSettings.objects.get(store=store).contact_phone, "09361428775")
        footer = FooterSettings.objects.get(store=store)
        self.assertEqual(footer.phone, "09361428775")
        self.assertEqual(footer.secondary_phone, "09147992815")

    def test_dense_taxonomy_brands_and_exact_product_count(self):
        self._run()
        store = self._store()
        self.assertEqual(Category.objects.filter(store=store, parent__isnull=True).count(), 10)
        self.assertEqual(Category.objects.filter(store=store).count(), 71)
        self.assertEqual(Brand.objects.filter(store=store).count(), 30)
        self.assertEqual(Product.objects.filter(store=store).count(), 100)
        self.assertEqual(Product.objects.filter(store=store).values("name").distinct().count(), 100)
        self.assertTrue(Product.objects.filter(store=store, name="شلوار چینو کرم استخوانی", price=2450000).exists())
        sale = Product.objects.get(store=store, name="سارافون گل گلی بچگانه")
        self.assertEqual(int(sale.price), 750000)
        self.assertGreater(sale.discount_percent, 0)

    def test_ten_homepage_collections_each_have_ten_products(self):
        self._run()
        store = self._store()
        collections = MerchantCollection.objects.filter(store=store)
        self.assertEqual(collections.count(), 10)
        for collection in collections:
            self.assertEqual(MerchantCollectionItem.objects.filter(collection=collection).count(), 10, collection.slug)
            for item in MerchantCollectionItem.objects.filter(collection=collection).select_related("product"):
                self.assertEqual(item.product.store_id, store.pk)

    def test_variants_and_synthetic_images_are_rich_enough_for_visual_qa(self):
        self._run()
        store = self._store()
        self.assertGreater(ProductVariant.objects.filter(product__store=store).count(), 250)
        self.assertEqual(ProductImage.objects.filter(product__store=store).count(), 200)
        self.assertGreaterEqual(ProductImage.objects.filter(product__store=store, variant__isnull=False).count(), 20)
        for image in ProductImage.objects.filter(product__store=store, variant__isnull=False).select_related("variant", "product"):
            self.assertEqual(image.variant.product_id, image.product_id)
        for image in ProductImage.objects.filter(product__store=store):
            self.assertFalse(str(image.image.name).startswith(("http://", "https://")))

    def test_homepage_content_social_and_pages_are_populated(self):
        self._run()
        store = self._store()
        self.assertEqual(HeroSlide.objects.filter(store=store).count(), 3)
        self.assertEqual(PromotionalBanner.objects.filter(store=store).count(), 4)
        self.assertEqual(StoryRailItem.objects.filter(store=store).count(), 4)
        self.assertEqual(SocialLink.objects.filter(store=store).count(), 4)
        pages = ContentPage.objects.filter(store=store, status=ContentPage.Status.PUBLISHED, show_in_footer=True)
        self.assertEqual(pages.count(), 6)
        self.assertTrue(pages.filter(slug="customer-club").exists())
        self.assertTrue(pages.filter(slug="returns").exists())

    def test_navigation_has_store_menu_dropdowns_and_no_dead_seeded_menu_items(self):
        self._run()
        store = self._store()
        header = Menu.objects.get(store=store, location=Menu.Location.HEADER)
        top = MenuItem.objects.filter(menu=header, parent__isnull=True)
        self.assertEqual(top.count(), 12)  # newest + sale + ten primary categories
        self.assertTrue(MenuItem.objects.filter(menu=header, parent__isnull=False).exists())
        for item in MenuItem.objects.filter(menu__store=store):
            self.assertNotEqual(item.destination_type, "none", item.title)

    def test_builder_publishes_sarv_with_ten_real_collection_sections(self):
        self._run()
        store = self._store()
        layout = StorefrontLayout.objects.get(store=store)
        self.assertIsNone(layout.draft_version_id)
        self.assertIsNotNone(layout.published_version_id)
        config = layout.published_version.effective_appearance_config()
        self.assertEqual(config["family_slug"], "sarv_stock")
        sections = list(layout.published_version.sections.order_by("order"))
        product_sections = [s for s in sections if s.section_key == "product_section"]
        self.assertEqual(len(product_sections), 10)
        titles = {s.settings.get("title") for s in product_sections}
        self.assertIn("تخفیفات شگفت انگیز", titles)
        self.assertIn("جدید ترین محصولات", titles)
        self.assertIn("عینک آفتابی اورجینال", titles)
        self.assertIn("اکسسوری", titles)

    def test_idempotent_and_reset_never_delete_unrelated_store(self):
        unrelated = Store.objects.create(name="فروشگاه مستقل", slug="unrelated-kian-qa", admin_subdomain="unrelated-kian-qa")
        self._run()
        first_store_id = self._store().pk
        self._run()
        self.assertEqual(Store.objects.get(slug=STORE_SLUG).pk, first_store_id)
        self.assertEqual(Product.objects.filter(store__slug=STORE_SLUG).count(), 100)
        self.assertEqual(ProductImage.objects.filter(product__store__slug=STORE_SLUG).count(), 200)
        cache.clear()
        self._run("--reset")
        self.assertTrue(Store.objects.filter(pk=unrelated.pk).exists())
        self.assertEqual(Product.objects.filter(store__slug=STORE_SLUG).count(), 100)
