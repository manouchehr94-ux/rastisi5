from decimal import Decimal
from io import BytesIO
from unittest import mock

from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from PIL import Image

from apps.catalog.models import Category, Product, Vendor
from apps.content.models import HeroSlide, PromotionalBanner
from apps.storefront_builder.models import StorefrontSection
from apps.storefront_builder.services import layout_service as svc
from apps.storefront_builder.services.render_service import build_page_render_items, build_render_items
from apps.stores.models import Store


def _akhlaghi():
    return Store.objects.get(slug="akhlaghi")


def _img(name="test.png"):
    buf = BytesIO()
    Image.new("RGB", (800, 400), (100, 50, 200)).save(buf, "PNG")
    return SimpleUploadedFile(name, buf.getvalue(), content_type="image/png")


class BuildRenderItemsTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_unknown_section_key_silently_skipped(self):
        store = _akhlaghi()
        draft = svc.get_or_create_draft(store)
        StorefrontSection.objects.create(version=draft, section_key="not_a_real_type", order=999)
        items = build_render_items(draft, store)
        self.assertNotIn("not_a_real_type", [i["section"].section_key for i in items])

    def test_inactive_sections_excluded(self):
        store = _akhlaghi()
        draft = svc.get_or_create_draft(store)
        inactive = StorefrontSection.objects.create(
            version=draft, section_key="trust_features", order=999, is_active=False,
        )
        items = build_render_items(draft, store)
        self.assertNotIn(inactive.pk, [i["section"].pk for i in items])

    def test_items_ordered_by_section_order(self):
        store = _akhlaghi()
        draft = svc.get_or_create_draft(store)
        items = build_render_items(draft, store)
        orders = [i["section"].order for i in items]
        self.assertEqual(orders, sorted(orders))

    def test_each_item_carries_own_settings_and_section(self):
        store = _akhlaghi()
        draft = svc.get_or_create_draft(store)
        section = StorefrontSection.objects.create(
            version=draft, section_key="rich_text", order=1000, settings={"body_html": "hi"},
        )
        items = build_render_items(draft, store)
        item = next(i for i in items if i["section"].pk == section.pk)
        self.assertEqual(item["context"]["settings"], {"body_html": "hi"})
        self.assertEqual(item["context"]["section"].pk, section.pk)

    def test_duplicated_section_type_does_not_duplicate_queries(self):
        """بهینه‌سازی کوئری: دو نمونه از یک section_key یکسان (قابلیت
        پشتیبانی‌شده duplicable) نباید کوئری داده را دو بار اجرا کنند —
        هیچ‌کدام از context builderها به تنظیمات نمونه وابسته نیستند.

        به‌جای یک عدد ثابت (که به وجود/عدم‌وجود محصول در دیتابیس تست
        وابسته است — prefetch وقتی محصولی نیست کوئری اضافه نمی‌زند)،
        کوئری‌های «یک نمونه» را با کوئری‌های «دو نمونه» مقایسه می‌کنیم:
        باید دقیقاً برابر باشند، یعنی نمونه‌ی دوم هیچ کوئری اضافه‌ای
        نزده است."""
        store = _akhlaghi()
        draft = svc.get_or_create_draft(store)
        draft.sections.all().delete()
        StorefrontSection.objects.create(version=draft, section_key="newest_products", order=0)
        with CaptureQueriesContext(connection) as single_ctx:
            items = build_render_items(draft, store)
            for i in items:
                list(i["context"]["products"])
        single_count = len(single_ctx.captured_queries)

        StorefrontSection.objects.create(version=draft, section_key="newest_products", order=1)
        with CaptureQueriesContext(connection) as double_ctx:
            items = build_render_items(draft, store)
            for i in items:
                list(i["context"]["products"])
        self.assertEqual(len(items), 2)
        self.assertEqual(len(double_ctx.captured_queries), single_count)

    def test_different_instances_of_same_type_share_live_data_correctly(self):
        """اطمینان از این‌که کش سطح-تابع باعث نمایش داده‌ی «چسبیده» از یک
        section دیگر نمی‌شود — هر دو نمونه محتوای صحیح (یکسان، چون از
        همان store می‌آیند) را نشان می‌دهند، نه محتوای خالی/اشتباه."""
        store = _akhlaghi()
        HeroSlide.objects.create(store=store, title="اسلاید تست", desktop_image=_img(), is_active=True)
        draft = svc.get_or_create_draft(store)
        draft.sections.filter(section_key="hero_banner").delete()
        StorefrontSection.objects.create(version=draft, section_key="hero_banner", order=900)
        StorefrontSection.objects.create(version=draft, section_key="hero_banner", order=901)

        items = build_render_items(draft, store)
        hero_items = [i for i in items if i["section"].section_key == "hero_banner"]
        self.assertEqual(len(hero_items), 2)
        for item in hero_items:
            titles = [s.title for s in item["context"]["hero_slides"]]
            self.assertIn("اسلاید تست", titles)


class ProductSectionRenderTests(TestCase):
    """product_section به‌عمد جزوِ ``PER_INSTANCE_SECTION_KEYS`` است —
    این کلاس دقیقاً همان چیزی را تأیید می‌کند که آن پرچم برایش اضافه شد:
    دو نمونه‌ی تکرارشده با تنظیماتِ متفاوت (اینجا: دو کالکشنِ متفاوت)
    باید محتوایِ متفاوت نشان دهند، نه محتوایِ «قرض‌گرفته‌شده» از نمونه‌ی
    اول (باگی که کشِ سطح section_key بدونِ این فیکس ایجاد می‌کرد)."""

    def setUp(self):
        cache.clear()

    def _product(self, store, slug, *, vendor=None, category=None):
        from decimal import Decimal

        from apps.catalog.models import Category, Vendor

        vendor = vendor or Vendor.objects.create(store=store, name=f"فروشنده {slug}", slug=f"v-{slug}")
        category = category or Category.objects.create(store=store, name=f"دسته {slug}", slug=f"c-{slug}")
        from apps.catalog.models import Product

        return Product.objects.create(
            store=store, vendor=vendor, category=category, name=f"کالای {slug}", slug=slug,
            sku=f"SKU-{slug}", price=Decimal("10000"), status=Product.Status.ACTIVE,
        )

    def test_two_instances_with_different_collections_do_not_share_products(self):
        from apps.catalog.services import collection_service

        store = _akhlaghi()
        draft = svc.get_or_create_draft(store)

        collection_a = collection_service.create_collection(store, name="کالکشن الف رندر")
        collection_b = collection_service.create_collection(store, name="کالکشن ب رندر")
        product_a = self._product(store, "render-ps-a")
        product_b = self._product(store, "render-ps-b")
        collection_service.add_product(collection_a, product_a)
        collection_service.add_product(collection_b, product_b)

        base_settings = {
            "data_source": "collection", "product_ids": [], "item_limit": 8,
            "display_mode": "carousel", "show_view_all": True, "title": "", "subtitle": "",
        }
        section_a = StorefrontSection.objects.create(
            version=draft, section_key="product_section", order=900,
            settings={**base_settings, "source_id": collection_a.pk},
        )
        section_b = StorefrontSection.objects.create(
            version=draft, section_key="product_section", order=901,
            settings={**base_settings, "source_id": collection_b.pk},
        )

        items = build_render_items(draft, store)
        item_a = next(i for i in items if i["section"].pk == section_a.pk)
        item_b = next(i for i in items if i["section"].pk == section_b.pk)
        self.assertEqual([p.pk for p in item_a["context"]["products"]], [product_a.pk])
        self.assertEqual([p.pk for p in item_b["context"]["products"]], [product_b.pk])

    def test_algorithmic_sources_reachable_through_full_pipeline(self):
        store = _akhlaghi()
        draft = svc.get_or_create_draft(store)
        self._product(store, "render-ps-newest")
        section = StorefrontSection.objects.create(
            version=draft, section_key="product_section", order=902,
            settings={
                "data_source": "newest", "source_id": None, "product_ids": [], "item_limit": 8,
                "display_mode": "grid", "show_view_all": True, "title": "جدیدترین", "subtitle": "",
            },
        )
        items = build_render_items(draft, store)
        item = next(i for i in items if i["section"].pk == section.pk)
        self.assertGreaterEqual(len(item["context"]["products"]), 1)
        self.assertIsNone(item["context"]["view_all_url"])

    def test_two_collection_instances_do_not_multiply_queries_per_extra_product(self):
        """رگرسیونِ N+1: کشِ per-instance (نه per-section_key) نباید به
        قیمتِ برگشتن به یک کوئری به‌ازایِ هر کالا تمام شود — هر نمونه
        باید select_related/prefetch_related را حفظ کند. مقایسه‌ی کوئریِ
        «۲ کالا در ۱ نمونه» با «۴ کالا در ۲ نمونه» باید تقریباً برابر
        باشد (همان تعداد کوئریِ ثابت، نه رشدِ خطی با تعدادِ کالا/نمونه)."""
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        from apps.catalog.services import collection_service

        store = _akhlaghi()
        draft = svc.get_or_create_draft(store)
        draft.sections.filter(section_key="product_section").delete()

        collection_a = collection_service.create_collection(store, name="کالکشن N+1 الف")
        collection_service.add_product(collection_a, self._product(store, "n1-a1"))
        collection_service.add_product(collection_a, self._product(store, "n1-a2"))
        base_settings = {
            "data_source": "collection", "product_ids": [], "item_limit": 8,
            "display_mode": "carousel", "show_view_all": True, "title": "", "subtitle": "",
        }
        StorefrontSection.objects.create(
            version=draft, section_key="product_section", order=950,
            settings={**base_settings, "source_id": collection_a.pk},
        )
        with CaptureQueriesContext(connection) as single_ctx:
            items = build_render_items(draft, store)
            for item in items:
                list(item["context"].get("products", []))
        single_count = len(single_ctx.captured_queries)

        collection_b = collection_service.create_collection(store, name="کالکشن N+1 ب")
        collection_service.add_product(collection_b, self._product(store, "n1-b1"))
        collection_service.add_product(collection_b, self._product(store, "n1-b2"))
        StorefrontSection.objects.create(
            version=draft, section_key="product_section", order=951,
            settings={**base_settings, "source_id": collection_b.pk},
        )
        with CaptureQueriesContext(connection) as double_ctx:
            items = build_render_items(draft, store)
            for item in items:
                list(item["context"].get("products", []))
        double_count = len(double_ctx.captured_queries)

        # یک نمونه‌ی دومِ کامل (کالکشن + کالاهایش) چند کوئریِ ثابتِ اضافه
        # می‌زند (خودِ resolve + prefetch تصاویر) — نه یک کوئری به‌ازایِ
        # هر کالای اضافه‌شده.
        self.assertLessEqual(double_count - single_count, 4)


class ScopedHeroSlidesTests(TestCase):
    """چکپوینتِ ادغامِ اسلایدرِ اصلی در سازنده بصری — اسلایدهایِ مخصوصِ یک
    section در برابرِ fallback به اسلایدهایِ سراسری (رفتارِ قدیمی)."""

    def setUp(self):
        cache.clear()

    def _items_for(self, draft, store, section_key):
        items = build_render_items(draft, store)
        return next(i for i in items if i["section"].section_key == section_key)

    def test_legacy_global_slides_still_render_when_section_has_none_scoped(self):
        """سازگاریِ کامل با گذشته: یک section جدید بدونِ اسلایدِ اختصاصی
        باید همچنان اسلایدهایِ سراسریِ فروشگاه (section=None) را نشان دهد."""
        store = _akhlaghi()
        HeroSlide.objects.create(store=store, section=None, title="اسلایدِ سراسری", desktop_image=_img(), is_active=True)
        draft = svc.get_or_create_draft(store)
        draft.sections.filter(section_key="hero_banner").delete()
        section = StorefrontSection.objects.create(version=draft, section_key="hero_banner", order=900)
        item = self._items_for(draft, store, "hero_banner")
        self.assertEqual(item["context"]["section"].pk, section.pk)
        titles = [s.title for s in item["context"]["hero_slides"]]
        self.assertIn("اسلایدِ سراسری", titles)

    def test_scoped_slides_take_priority_over_global(self):
        store = _akhlaghi()
        HeroSlide.objects.create(store=store, section=None, title="سراسری", desktop_image=_img(), is_active=True)
        draft = svc.get_or_create_draft(store)
        draft.sections.filter(section_key="hero_banner").delete()
        section = StorefrontSection.objects.create(version=draft, section_key="hero_banner", order=900)
        HeroSlide.objects.create(store=store, section=section, title="اختصاصی", desktop_image=_img(), is_active=True)
        item = self._items_for(draft, store, "hero_banner")
        titles = [s.title for s in item["context"]["hero_slides"]]
        self.assertEqual(titles, ["اختصاصی"])

    def test_two_independent_hero_sections_show_different_slides(self):
        """الزامِ صریحِ کار: «Hero Slider A و Hero Slider B با اسلایدهایِ
        متفاوت» — قلبِ چکپوینتِ اسلایدرِ اصلی."""
        store = _akhlaghi()
        draft = svc.get_or_create_draft(store)
        section_a = StorefrontSection.objects.create(version=draft, section_key="hero_banner", order=900)
        section_b = StorefrontSection.objects.create(version=draft, section_key="hero_banner", order=901)
        HeroSlide.objects.create(store=store, section=section_a, title="A1", desktop_image=_img(), is_active=True)
        HeroSlide.objects.create(store=store, section=section_b, title="B1", desktop_image=_img(), is_active=True)

        items = build_render_items(draft, store)
        hero_items = [i for i in items if i["section"].section_key == "hero_banner"]
        self.assertEqual(len(hero_items), 2)
        titles_by_section = {
            i["context"]["section"].pk: [s.title for s in i["context"]["hero_slides"]] for i in hero_items
        }
        self.assertEqual(titles_by_section[section_a.pk], ["A1"])
        self.assertEqual(titles_by_section[section_b.pk], ["B1"])

    def test_slider_settings_default_when_settings_empty(self):
        store = _akhlaghi()
        draft = svc.get_or_create_draft(store)
        StorefrontSection.objects.create(version=draft, section_key="hero_banner", order=900, settings={})
        item = self._items_for(draft, store, "hero_banner")
        self.assertIs(item["context"]["slider_settings"]["autoplay"], True)
        self.assertEqual(item["context"]["slider_settings"]["interval_ms"], 4500)

    def test_slider_settings_explicit_false_preserved(self):
        """همان دلیلِ ``effective_header_config`` — False صریح نباید با
        پیش‌فرضِ True بازنویسی شود."""
        store = _akhlaghi()
        draft = svc.get_or_create_draft(store)
        StorefrontSection.objects.create(
            version=draft, section_key="hero_banner", order=900,
            settings={"autoplay": False, "interval_ms": 4500, "show_arrows": True, "show_dots": True, "loop": True},
        )
        item = self._items_for(draft, store, "hero_banner")
        self.assertIs(item["context"]["slider_settings"]["autoplay"], False)

    def test_inactive_scoped_slide_falls_back_to_global(self):
        """اگر تنها اسلایدِ اختصاصیِ یک section غیرفعال شود، باید دقیقاً
        مثلِ «هیچ اسلایدِ اختصاصی ندارد» رفتار شود (fail-closed، نه بومِ
        خالی) — نه نمایشِ خالی و نه نمایشِ اسلایدِ غیرفعال."""
        store = _akhlaghi()
        HeroSlide.objects.create(store=store, section=None, title="سراسری", desktop_image=_img(), is_active=True)
        draft = svc.get_or_create_draft(store)
        draft.sections.filter(section_key="hero_banner").delete()
        section = StorefrontSection.objects.create(version=draft, section_key="hero_banner", order=900)
        HeroSlide.objects.create(store=store, section=section, title="غیرفعال", desktop_image=_img(), is_active=False)
        item = self._items_for(draft, store, "hero_banner")
        titles = [s.title for s in item["context"]["hero_slides"]]
        self.assertEqual(titles, ["سراسری"])


class ScopedBannersTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_two_multi_banner_sections_show_different_banners(self):
        store = _akhlaghi()
        draft = svc.get_or_create_draft(store)
        section_a = StorefrontSection.objects.create(version=draft, section_key="multi_banner", order=900)
        section_b = StorefrontSection.objects.create(version=draft, section_key="multi_banner", order=901)
        PromotionalBanner.objects.create(store=store, section=section_a, title="بنر A", desktop_image=_img(), is_active=True)
        PromotionalBanner.objects.create(store=store, section=section_b, title="بنر B", desktop_image=_img(), is_active=True)

        items = build_render_items(draft, store)
        banner_items = [i for i in items if i["section"].section_key == "multi_banner"]
        titles_by_section = {
            i["context"]["section"].pk: [b.title for b in i["context"]["banners"]] for i in banner_items
        }
        self.assertEqual(titles_by_section[section_a.pk], ["بنر A"])
        self.assertEqual(titles_by_section[section_b.pk], ["بنر B"])

    def test_single_banner_takes_first_scoped_banner_only(self):
        store = _akhlaghi()
        draft = svc.get_or_create_draft(store)
        section = StorefrontSection.objects.create(version=draft, section_key="single_banner", order=900)
        PromotionalBanner.objects.create(store=store, section=section, title="اول", desktop_image=_img(), is_active=True, display_order=0)
        PromotionalBanner.objects.create(store=store, section=section, title="دوم", desktop_image=_img(), is_active=True, display_order=1)
        items = build_render_items(draft, store)
        item = next(i for i in items if i["section"].section_key == "single_banner")
        titles = [b.title for b in item["context"]["banners"]]
        self.assertEqual(titles, ["اول"])


class CategoryGridRenderTests(TestCase):
    """چکپوینتِ ۱۱: category_grid از یک بلوکِ auto سراسری به یک section
    واقعاً per-instance ارتقا یافت."""

    def setUp(self):
        cache.clear()

    def _items_for(self, draft, store):
        items = build_render_items(draft, store)
        return [i for i in items if i["section"].section_key == "category_grid"]

    def test_empty_selection_falls_back_to_legacy_auto_pick(self):
        """سازگاریِ کامل با گذشته: section بدونِ category_ids دقیقاً همان
        رفتارِ ۳+۱ قبل از این چکپوینت را دارد."""
        from apps.catalog.models import Category

        store = _akhlaghi()
        for i in range(5):
            Category.objects.create(store=store, name=f"دسته {i}", slug=f"cat-{i}", order=i, is_active=True)
        draft = svc.get_or_create_draft(store)
        draft.sections.filter(section_key="category_grid").delete()
        StorefrontSection.objects.create(version=draft, section_key="category_grid", order=900)
        item = self._items_for(draft, store)[0]
        self.assertEqual(len(item["context"]["tiles"]), 3)
        self.assertIsNotNone(item["context"]["cream_category"])

    def test_two_independent_category_grids_show_different_categories(self):
        """الزامِ صریحِ کار: تکرارِ گرید دسته‌بندی باید دسته‌های متفاوت
        نشان دهد — نه همان فهرستِ نمونه‌ی اول."""
        from apps.catalog.models import Category

        store = _akhlaghi()
        cat_a = Category.objects.create(store=store, name="دسته A", slug="cat-a", is_active=True)
        cat_b = Category.objects.create(store=store, name="دسته B", slug="cat-b", is_active=True)
        draft = svc.get_or_create_draft(store)
        draft.sections.filter(section_key="category_grid").delete()
        section_a = StorefrontSection.objects.create(
            version=draft, section_key="category_grid", order=900,
            settings={"title": "", "display_mode": "grid", "category_ids": [cat_a.pk]},
        )
        section_b = StorefrontSection.objects.create(
            version=draft, section_key="category_grid", order=901,
            settings={"title": "", "display_mode": "grid", "category_ids": [cat_b.pk]},
        )
        items = self._items_for(draft, store)
        names_by_section = {i["context"]["section"].pk: [c.name for c in i["context"]["top_categories"]] for i in items}
        self.assertEqual(names_by_section[section_a.pk], ["دسته A"])
        self.assertEqual(names_by_section[section_b.pk], ["دسته B"])

    def test_selection_preserves_merchant_order_not_database_order(self):
        from apps.catalog.models import Category

        store = _akhlaghi()
        cat_a = Category.objects.create(store=store, name="آ", slug="cat-aa", is_active=True)
        cat_b = Category.objects.create(store=store, name="ب", slug="cat-bb", is_active=True)
        draft = svc.get_or_create_draft(store)
        draft.sections.filter(section_key="category_grid").delete()
        StorefrontSection.objects.create(
            version=draft, section_key="category_grid", order=900,
            settings={"title": "", "display_mode": "grid", "category_ids": [cat_b.pk, cat_a.pk]},
        )
        item = self._items_for(draft, store)[0]
        self.assertEqual([c.name for c in item["context"]["top_categories"]], ["ب", "آ"])

    def test_inactive_category_silently_excluded(self):
        from apps.catalog.models import Category

        store = _akhlaghi()
        cat = Category.objects.create(store=store, name="غیرفعال", slug="cat-inactive", is_active=False)
        draft = svc.get_or_create_draft(store)
        draft.sections.filter(section_key="category_grid").delete()
        StorefrontSection.objects.create(
            version=draft, section_key="category_grid", order=900,
            settings={"title": "", "display_mode": "grid", "category_ids": [cat.pk]},
        )
        item = self._items_for(draft, store)[0]
        self.assertEqual(item["context"]["top_categories"], [])


class BrandCarouselRenderTests(TestCase):
    def setUp(self):
        cache.clear()

    def _items_for(self, draft, store):
        items = build_render_items(draft, store)
        return [i for i in items if i["section"].section_key == "brand_carousel"]

    def test_empty_selection_falls_back_to_all_active_brands(self):
        from apps.catalog.models import Brand

        store = _akhlaghi()
        Brand.objects.create(store=store, name="برند فعال", slug="brand-active", is_active=True)
        Brand.objects.create(store=store, name="برند غیرفعال", slug="brand-inactive", is_active=False)
        draft = svc.get_or_create_draft(store)
        draft.sections.filter(section_key="brand_carousel").delete()
        StorefrontSection.objects.create(version=draft, section_key="brand_carousel", order=900)
        item = self._items_for(draft, store)[0]
        self.assertEqual([b.name for b in item["context"]["brands"]], ["برند فعال"])

    def test_two_independent_brand_carousels_show_different_brands(self):
        from apps.catalog.models import Brand

        store = _akhlaghi()
        brand_a = Brand.objects.create(store=store, name="برند A", slug="brand-a", is_active=True)
        brand_b = Brand.objects.create(store=store, name="برند B", slug="brand-b", is_active=True)
        draft = svc.get_or_create_draft(store)
        draft.sections.filter(section_key="brand_carousel").delete()
        section_a = StorefrontSection.objects.create(
            version=draft, section_key="brand_carousel", order=900,
            settings={"title": "", "display_mode": "grid", "show_view_all": False, "brand_ids": [brand_a.pk]},
        )
        section_b = StorefrontSection.objects.create(
            version=draft, section_key="brand_carousel", order=901,
            settings={"title": "", "display_mode": "grid", "show_view_all": False, "brand_ids": [brand_b.pk]},
        )
        items = self._items_for(draft, store)
        names_by_section = {i["context"]["section"].pk: [b.name for b in i["context"]["brands"]] for i in items}
        self.assertEqual(names_by_section[section_a.pk], ["برند A"])
        self.assertEqual(names_by_section[section_b.pk], ["برند B"])

    def test_view_all_link_absent_without_show_view_all(self):
        store = _akhlaghi()
        draft = svc.get_or_create_draft(store)
        draft.sections.filter(section_key="brand_carousel").delete()
        StorefrontSection.objects.create(version=draft, section_key="brand_carousel", order=900)
        item = self._items_for(draft, store)[0]
        self.assertIsNone(item["context"]["view_all_url"])

    def test_view_all_link_resolves_when_enabled_with_destination(self):
        from apps.catalog.models import Category

        store = _akhlaghi()
        category = Category.objects.create(store=store, name="همه برندها", slug="all-brands-cat", is_active=True)
        draft = svc.get_or_create_draft(store)
        draft.sections.filter(section_key="brand_carousel").delete()
        StorefrontSection.objects.create(
            version=draft, section_key="brand_carousel", order=900,
            settings={
                "title": "", "display_mode": "grid", "show_view_all": True, "brand_ids": [],
                "destination": {"destination_type": "category", "destination_id": category.pk, "open_in_new_tab": False},
            },
        )
        item = self._items_for(draft, store)[0]
        self.assertIsNotNone(item["context"]["view_all_url"])
        self.assertIn(category.slug, item["context"]["view_all_url"])


class CollectionTilesRenderTests(TestCase):
    def setUp(self):
        cache.clear()

    def _items_for(self, draft, store):
        items = build_render_items(draft, store)
        return [i for i in items if i["section"].section_key == "collection_tiles"]

    def test_empty_selection_falls_back_to_all_active_collections(self):
        from apps.catalog.models import MerchantCollection

        store = _akhlaghi()
        MerchantCollection.objects.create(store=store, name="کالکشن فعال", slug="ct-active", is_active=True)
        MerchantCollection.objects.create(store=store, name="کالکشن غیرفعال", slug="ct-inactive", is_active=False)
        draft = svc.get_or_create_draft(store)
        StorefrontSection.objects.create(version=draft, section_key="collection_tiles", order=900)
        item = self._items_for(draft, store)[0]
        names = [row["collection"].name for row in item["context"]["collection_tiles"]]
        self.assertEqual(names, ["کالکشن فعال"])

    def test_two_independent_collection_tile_sections_show_different_collections(self):
        from apps.catalog.models import MerchantCollection

        store = _akhlaghi()
        coll_a = MerchantCollection.objects.create(store=store, name="کالکشن A", slug="ct-a", is_active=True)
        coll_b = MerchantCollection.objects.create(store=store, name="کالکشن B", slug="ct-b", is_active=True)
        draft = svc.get_or_create_draft(store)
        section_a = StorefrontSection.objects.create(
            version=draft, section_key="collection_tiles", order=900,
            settings={"title": "", "collection_ids": [coll_a.pk]},
        )
        section_b = StorefrontSection.objects.create(
            version=draft, section_key="collection_tiles", order=901,
            settings={"title": "", "collection_ids": [coll_b.pk]},
        )
        items = self._items_for(draft, store)
        names_by_section = {
            i["context"]["section"].pk: [row["collection"].name for row in i["context"]["collection_tiles"]]
            for i in items
        }
        self.assertEqual(names_by_section[section_a.pk], ["کالکشن A"])
        self.assertEqual(names_by_section[section_b.pk], ["کالکشن B"])

    def test_item_count_reflects_real_products_in_collection(self):
        from decimal import Decimal

        from apps.catalog.models import Category, MerchantCollection, MerchantCollectionItem, Product, Vendor

        store = _akhlaghi()
        vendor = Vendor.objects.create(store=store, name="فروشنده ct-count", slug="v-ct-count")
        category = Category.objects.create(store=store, name="دسته", slug="ct-count-cat", is_active=True)
        collection = MerchantCollection.objects.create(store=store, name="کالکشن شمارشی", slug="ct-count", is_active=True)
        for i in range(3):
            product = Product.objects.create(
                store=store, vendor=vendor, category=category, name=f"کالای {i}", slug=f"ct-count-p{i}",
                sku=f"SKU-CT-{i}", price=Decimal("10000"), status=Product.Status.ACTIVE,
            )
            MerchantCollectionItem.objects.create(collection=collection, product=product, order=i)
        draft = svc.get_or_create_draft(store)
        StorefrontSection.objects.create(
            version=draft, section_key="collection_tiles", order=900,
            settings={"title": "", "collection_ids": [collection.pk]},
        )
        item = self._items_for(draft, store)[0]
        self.assertEqual(item["context"]["collection_tiles"][0]["item_count"], 3)


class QuickLinksRenderTests(TestCase):
    def setUp(self):
        cache.clear()

    def _items_for(self, draft, store):
        items = build_render_items(draft, store)
        return [i for i in items if i["section"].section_key == "quick_links"]

    def test_no_menu_configured_renders_no_items(self):
        store = _akhlaghi()
        draft = svc.get_or_create_draft(store)
        StorefrontSection.objects.create(version=draft, section_key="quick_links", order=900)
        item = self._items_for(draft, store)[0]
        self.assertEqual(item["context"]["quick_link_items"], [])

    def test_menu_items_resolved_with_real_destination_urls(self):
        from apps.catalog.models import Category
        from apps.content.models import DestinationType, Menu, MenuItem

        store = _akhlaghi()
        category = Category.objects.create(store=store, name="دسته دسترسی سریع", slug="ql-cat", is_active=True)
        menu = Menu.objects.create(store=store, title="دسترسی سریع", location=Menu.Location.HEADER, is_active=True)
        MenuItem.objects.create(
            menu=menu, title="مشاهده دسته", display_order=0, is_active=True,
            destination_type=DestinationType.CATEGORY, destination_category=category,
        )
        draft = svc.get_or_create_draft(store)
        StorefrontSection.objects.create(
            version=draft, section_key="quick_links", order=900,
            settings={"title": "", "menu_id": menu.pk},
        )
        item = self._items_for(draft, store)[0]
        items = item["context"]["quick_link_items"]
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["title"], "مشاهده دسته")
        self.assertIn(category.slug, items[0]["url"])

    def test_menu_items_query_count_is_constant_not_per_item(self):
        """رگرسیون: نسخه‌ی اولِ این تابع ``prefetch_related`` را با یک
        ``.filter()`` دیگر رویِ ``menu.items`` ترکیب می‌کرد که کشِ
        prefetch را بی‌اثر می‌گذاشت — این تست تضمین می‌کند تعدادِ کوئریِ
        خودِ این section (نه کلِ صفحه — سکشن‌های bootstrap-شده‌ی دیگر
        کوئریِ خودشان را دارند) با تعدادِ آیتم‌های منو رشد نمی‌کند."""
        from apps.catalog.models import Category
        from apps.content.models import DestinationType, Menu, MenuItem

        def _query_count_for(item_count):
            store = _akhlaghi()
            MenuItem.objects.filter(menu__store=store, menu__location=Menu.Location.HEADER).delete()
            Menu.objects.filter(store=store, location=Menu.Location.HEADER).delete()
            menu = Menu.objects.create(store=store, title="منوی کوئری", location=Menu.Location.HEADER, is_active=True)
            for i in range(item_count):
                category = Category.objects.create(store=store, name=f"دسته {i}", slug=f"ql-q-{item_count}-{i}", is_active=True)
                MenuItem.objects.create(
                    menu=menu, title=f"آیتم {i}", display_order=i, is_active=True,
                    destination_type=DestinationType.CATEGORY, destination_category=category,
                )
            draft = svc.get_or_create_draft(store)
            draft.sections.all().delete()
            StorefrontSection.objects.create(
                version=draft, section_key="quick_links", order=900, settings={"title": "", "menu_id": menu.pk},
            )
            with CaptureQueriesContext(connection) as ctx:
                item = self._items_for(draft, store)[0]
                self.assertEqual(len(item["context"]["quick_link_items"]), item_count)
            return len(ctx.captured_queries)

        small_count = _query_count_for(2)
        large_count = _query_count_for(15)
        self.assertEqual(small_count, large_count)

    def test_menu_from_another_store_never_leaks(self):
        from apps.content.models import Menu

        store = _akhlaghi()
        other_store = Store.objects.exclude(pk=store.pk).first()
        if other_store is None:
            self.skipTest("no second store fixture available")
        other_menu = Menu.objects.create(store=other_store, title="منوی فروشگاه دیگر", location=Menu.Location.HEADER, is_active=True)
        draft = svc.get_or_create_draft(store)
        StorefrontSection.objects.create(
            version=draft, section_key="quick_links", order=900,
            settings={"title": "", "menu_id": other_menu.pk},
        )
        item = self._items_for(draft, store)[0]
        self.assertEqual(item["context"]["quick_link_items"], [])


class VideoSectionRenderTests(TestCase):
    def setUp(self):
        cache.clear()

    def _items_for(self, draft, store):
        items = build_render_items(draft, store)
        return [i for i in items if i["section"].section_key == "video_section"]

    def test_no_url_renders_nothing(self):
        store = _akhlaghi()
        draft = svc.get_or_create_draft(store)
        StorefrontSection.objects.create(version=draft, section_key="video_section", order=900)
        item = self._items_for(draft, store)[0]
        self.assertIsNone(item["context"]["video_embed_url"])
        self.assertFalse(item["context"]["video_is_instagram"])

    def test_youtube_url_produces_embed_url(self):
        store = _akhlaghi()
        draft = svc.get_or_create_draft(store)
        StorefrontSection.objects.create(
            version=draft, section_key="video_section", order=900,
            settings={"title": "", "video_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ", "caption": ""},
        )
        item = self._items_for(draft, store)[0]
        self.assertIn("youtube.com/embed/dQw4w9WgXcQ", item["context"]["video_embed_url"])

    def test_instagram_url_never_produces_an_iframe_only_a_permalink(self):
        store = _akhlaghi()
        draft = svc.get_or_create_draft(store)
        StorefrontSection.objects.create(
            version=draft, section_key="video_section", order=900,
            settings={"title": "", "video_url": "https://instagram.com/p/ABC123xyz/", "caption": ""},
        )
        item = self._items_for(draft, store)[0]
        self.assertIsNone(item["context"]["video_embed_url"])
        self.assertTrue(item["context"]["video_is_instagram"])
        self.assertIsNotNone(item["context"]["video_permalink"])

    def test_two_independent_video_sections_show_different_videos(self):
        store = _akhlaghi()
        draft = svc.get_or_create_draft(store)
        section_a = StorefrontSection.objects.create(
            version=draft, section_key="video_section", order=900,
            settings={"title": "", "video_url": "https://www.youtube.com/watch?v=aaaaaaaaaaa", "caption": ""},
        )
        section_b = StorefrontSection.objects.create(
            version=draft, section_key="video_section", order=901,
            settings={"title": "", "video_url": "https://www.youtube.com/watch?v=bbbbbbbbbbb", "caption": ""},
        )
        items = self._items_for(draft, store)
        urls_by_section = {i["context"]["section"].pk: i["context"]["video_embed_url"] for i in items}
        self.assertIn("aaaaaaaaaaa", urls_by_section[section_a.pk])
        self.assertIn("bbbbbbbbbbb", urls_by_section[section_b.pk])


class PageContextPassthroughTests(TestCase):
    """Phase 5: ``build_page_render_items``یِ ``page_context`` را عیناً و
    بدونِ کوئریِ اضافه به سازنده‌یِ context-awareِ همان section_key پاس
    می‌دهد — این تست مکانیزم را مستقل از هر نوعِ section واقعیِ آینده
    اثبات می‌کند (با یک builderِ آزمایشی موقت در ``_CONTEXT_AWARE_BUILDERS``)."""

    def setUp(self):
        cache.clear()
        from apps.storefront_builder.services import render_service
        self.render_service = render_service

    def test_page_context_reaches_a_context_aware_builder_unchanged(self):
        store = _akhlaghi()
        draft = svc.get_or_create_draft(store)
        page = draft.get_page("cart")
        StorefrontSection.objects.create(page=page, section_key="trust_features", order=0)

        received = {}

        def _fake_builder(store_arg, section_arg, page_context_arg):
            received["store"] = store_arg
            received["page_context"] = page_context_arg
            return {"marker": "PAGE-CONTEXT-REACHED"}

        with mock.patch.dict(
            self.render_service._CONTEXT_AWARE_BUILDERS, {"trust_features": _fake_builder},
        ):
            sentinel = {"cart": "SENTINEL-CART-OBJECT"}
            items = self.render_service.build_page_render_items(page, store, page_context=sentinel)

        self.assertEqual(received["store"], store)
        self.assertIs(received["page_context"], sentinel)
        self.assertEqual(items[0]["context"]["marker"], "PAGE-CONTEXT-REACHED")

    def test_missing_page_context_defaults_to_empty_dict_not_none(self):
        store = _akhlaghi()
        draft = svc.get_or_create_draft(store)
        page = draft.get_page("cart")
        StorefrontSection.objects.create(page=page, section_key="trust_features", order=0)

        received = {}

        def _fake_builder(store_arg, section_arg, page_context_arg):
            received["page_context"] = page_context_arg
            return {}

        with mock.patch.dict(
            self.render_service._CONTEXT_AWARE_BUILDERS, {"trust_features": _fake_builder},
        ):
            self.render_service.build_page_render_items(page, store)

        self.assertEqual(received["page_context"], {})

    def test_non_context_aware_sections_unaffected_by_page_context(self):
        """بخش‌هایِ معمولی (مثلِ trust_features واقعی، بدونِ mock) باید
        دقیقاً همان context را بگیرند، صرف‌نظر از اینکه page_context چه
        باشد — مکانیزمِ جدید نباید رفتارِ ۱۷ نوعِ موجود را تغییر دهد."""
        store = _akhlaghi()
        draft = svc.get_or_create_draft(store)
        page = draft.get_page("home")
        StorefrontSection.objects.create(page=page, section_key="trust_features", order=0)

        without = self.render_service.build_page_render_items(page, store)
        with_noise = self.render_service.build_page_render_items(
            page, store, page_context={"anything": "irrelevant-to-trust-features"},
        )
        self.assertEqual(without[0]["context"]["settings"], with_noise[0]["context"]["settings"])


class ProductDetailContextAwareSectionsTests(TestCase):
    """Phase 5: چهار نوعِ context-aware صفحه محصول — داده از
    ``page_context`` می‌آید (شبیه‌سازیِ همان دیکشنری که
    ``build_product_detail_context`` واقعاً می‌سازد)، هرگز کوئریِ تازه."""

    def setUp(self):
        cache.clear()
        self.store = _akhlaghi()
        self.vendor = Vendor.objects.create(store=self.store, name="فروشنده رندر", slug="render-vendor")
        self.category = Category.objects.create(store=self.store, name="دسته رندر", slug="render-cat", is_active=True)
        self.product = Product.objects.create(
            store=self.store, vendor=self.vendor, category=self.category, name="کالای رندر",
            slug="render-product", sku="RENDER-1", price=Decimal("50000"), stock=3, status=Product.Status.ACTIVE,
        )
        self.draft = svc.get_or_create_draft(self.store)
        self.page = self.draft.get_page("product_detail")

    def _page_context(self, **overrides):
        base = {
            "product": self.product,
            "variant_selector": {"mode": "none"},
            "product_price_json": {"price": 50000, "regular": 50000, "savings": 0, "stock": 3, "sku": "RENDER-1"},
            "gallery_slides": [],
            "review_count": 2,
            "spec_variant_summary": {},
            "approved_reviews": [],
            "rating_breakdown": [],
            "can_review": False,
            "product_videos": [],
            "related_products": [],
        }
        base.update(overrides)
        return base

    def _item_for(self, section_key, page_context):
        StorefrontSection.objects.create(page=self.page, section_key=section_key, order=0)
        items = build_page_render_items(self.page, self.store, page_context=page_context)
        self.assertEqual(len(items), 1)
        return items[0]

    def test_product_main_receives_the_current_product(self):
        item = self._item_for("product_main", self._page_context())
        self.assertEqual(item["context"]["product"], self.product)
        self.assertEqual(item["context"]["review_count"], 2)

    def test_product_main_fails_safe_without_a_product(self):
        item = self._item_for("product_main", {})
        self.assertNotIn("product", item["context"])

    def test_product_description_receives_review_and_spec_data(self):
        item = self._item_for("product_description", self._page_context(spec_variant_summary={"رنگ": "قرمز"}))
        self.assertEqual(item["context"]["product"], self.product)
        self.assertEqual(item["context"]["spec_variant_summary"], {"رنگ": "قرمز"})

    def test_product_description_fails_safe_without_a_product(self):
        item = self._item_for("product_description", {})
        self.assertNotIn("product", item["context"])

    def test_product_video_passes_through_video_list(self):
        item = self._item_for("product_video", self._page_context(product_videos=[{"title": "v"}]))
        self.assertEqual(item["context"]["product_videos"], [{"title": "v"}])

    def test_product_video_fails_safe_without_a_product(self):
        item = self._item_for("product_video", {})
        self.assertNotIn("product_videos", item["context"])

    def test_related_products_passes_through_queryset(self):
        other = Product.objects.create(
            store=self.store, vendor=self.vendor, category=self.category, name="کالای مرتبط",
            slug="render-related", sku="RENDER-2", price=Decimal("10000"), stock=1, status=Product.Status.ACTIVE,
        )
        item = self._item_for("related_products", self._page_context(related_products=[other]))
        self.assertEqual(list(item["context"]["related_products"]), [other])

    def test_related_products_fails_safe_without_a_product(self):
        item = self._item_for("related_products", {})
        self.assertNotIn("related_products", item["context"])

    def test_context_aware_sections_only_resolve_on_product_detail_page(self):
        """صفحاتِ دیگر (مثلاً cart) اصلاً امکانِ داشتنِ این section_key را
        ندارند (allowlist سمتِ سرور در ``storefront_section_add`` رد
        می‌کند) — این تست خودِ لایه‌یِ رندر را مستقل اثبات می‌کند: حتی اگر
        یک ردیفِ StorefrontSection نامعتبر (دستکاریِ مستقیمِ دیتابیس) روی
        صفحه‌ی اشتباه بنشیند، رندر همچنان بدونِ کرش کار می‌کند."""
        cart_page = self.draft.get_page("cart")
        StorefrontSection.objects.create(page=cart_page, section_key="product_main", order=0)
        items = build_page_render_items(cart_page, self.store, page_context={"cart": None})
        self.assertEqual(len(items), 1)
        self.assertNotIn("product", items[0]["context"])


class ProductListingContextAwareSectionTests(TestCase):
    """Phase 5: ``product_listing`` روی هر دو نوعِ صفحه (listing/search)
    مجاز است و همیشه (حتی بدونِ هیچ کلیدی در page_context) بی‌خطا رندر
    می‌شود — برخلافِ چهار نوعِ صفحه محصول، هیچ «شیءِ لازم»ی ندارد."""

    def setUp(self):
        cache.clear()
        self.store = _akhlaghi()
        self.draft = svc.get_or_create_draft(self.store)

    def test_receives_listing_context_unchanged(self):
        page = self.draft.get_page("listing")
        StorefrontSection.objects.create(page=page, section_key="product_listing", order=0)
        page_context = {
            "page_obj": "PAGE-OBJ-SENTINEL", "products": ["p1"], "query": "", "sort_key": "newest",
            "sort_options": {"newest": ("x", "جدیدترین")}, "filter_categories": [], "brands": [],
            "selected_category": "", "selected_brand": "", "min_price": "", "max_price": "",
            "discounted_only": False, "querystring": "",
        }
        items = build_page_render_items(page, self.store, page_context=page_context)
        self.assertEqual(items[0]["context"]["page_obj"], "PAGE-OBJ-SENTINEL")
        self.assertEqual(items[0]["context"]["products"], ["p1"])

    def test_allowed_on_search_page_too(self):
        page = self.draft.get_page("search")
        StorefrontSection.objects.create(page=page, section_key="product_listing", order=0)
        items = build_page_render_items(page, self.store, page_context={})
        self.assertEqual(len(items), 1)

    def test_missing_page_context_keys_default_safely(self):
        page = self.draft.get_page("listing")
        StorefrontSection.objects.create(page=page, section_key="product_listing", order=0)
        items = build_page_render_items(page, self.store, page_context={})
        context = items[0]["context"]
        self.assertEqual(context["query"], "")
        self.assertEqual(context["discounted_only"], False)
        self.assertIsNone(context["page_obj"])
