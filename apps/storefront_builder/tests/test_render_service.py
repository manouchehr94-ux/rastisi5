from io import BytesIO

from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from PIL import Image

from apps.content.models import HeroSlide
from apps.storefront_builder.models import StorefrontSection
from apps.storefront_builder.services import layout_service as svc
from apps.storefront_builder.services.render_service import build_render_items
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
