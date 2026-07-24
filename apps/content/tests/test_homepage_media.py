"""تست‌های مدل‌ها و رندر اسلاید و بنر صفحه اصلی."""

from decimal import Decimal
from io import BytesIO

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from PIL import Image

from apps.catalog.models import Category, Product, Vendor
from apps.content.models import DestinationType, HeroSlide, PromotionalBanner
from apps.content.services import resolve_destination_url

User = get_user_model()


def _img(name="test.png"):
    buf = BytesIO()
    Image.new("RGB", (800, 400), (100, 50, 200)).save(buf, "PNG")
    return SimpleUploadedFile(name, buf.getvalue(), content_type="image/png")


class HeroSlideModelTests(TestCase):
    def test_valid_creation(self):
        slide = HeroSlide.objects.create(
            title="تست", desktop_image=_img(), is_active=True, display_order=0
        )
        self.assertEqual(slide.title, "تست")

    def test_desktop_image_required(self):
        slide = HeroSlide(title="No img")
        with self.assertRaises(Exception):
            slide.full_clean()

    def test_mobile_image_optional(self):
        slide = HeroSlide(title="OK", desktop_image=_img())
        slide.full_clean()  # Should not raise

    def test_button_label_required_when_visible(self):
        slide = HeroSlide(
            title="T", desktop_image=_img(), show_button=True, button_label="",
            destination_type=DestinationType.EXTERNAL,
            destination_external_url="https://example.com",
        )
        with self.assertRaises(ValidationError) as ctx:
            slide.full_clean()
        self.assertIn("button_label", ctx.exception.message_dict)

    def test_destination_required_when_button_visible(self):
        slide = HeroSlide(
            title="T", desktop_image=_img(), show_button=True,
            button_label="کلیک", destination_type=DestinationType.NONE,
        )
        with self.assertRaises(ValidationError):
            slide.full_clean()

    def test_hidden_button_no_destination_ok(self):
        slide = HeroSlide(
            title="T", desktop_image=_img(), show_button=False,
            destination_type=DestinationType.NONE,
        )
        slide.full_clean()  # OK

    def test_ordering(self):
        HeroSlide.objects.create(title="B", desktop_image=_img(), display_order=2)
        HeroSlide.objects.create(title="A", desktop_image=_img(), display_order=1)
        slides = list(HeroSlide.objects.values_list("title", flat=True))
        self.assertEqual(slides, ["A", "B"])

    def test_destination_resolves(self):
        vendor = Vendor.objects.create(name="V", slug="v")
        cat = Category.objects.create(name="C", slug="c")
        slide = HeroSlide(
            title="T", desktop_image=_img(), show_button=True,
            button_label="مشاهده", destination_type=DestinationType.CATEGORY,
            destination_category=cat,
        )
        url = resolve_destination_url(slide)
        self.assertIn("category=c", url)


class PromotionalBannerModelTests(TestCase):
    def test_valid_creation(self):
        banner = PromotionalBanner.objects.create(
            title="بنر", desktop_image=_img(), is_active=True,
        )
        self.assertTrue(banner.pk)

    def test_button_label_required_when_visible(self):
        banner = PromotionalBanner(
            title="B", desktop_image=_img(), show_button=True, button_label="",
            destination_type=DestinationType.EXTERNAL,
            destination_external_url="https://x.com",
        )
        with self.assertRaises(ValidationError):
            banner.full_clean()

    def test_inactive_not_in_active_queryset(self):
        PromotionalBanner.objects.create(title="Active", desktop_image=_img(), is_active=True)
        PromotionalBanner.objects.create(title="Inactive", desktop_image=_img(), is_active=False)
        active = PromotionalBanner.objects.filter(is_active=True)
        self.assertEqual(active.count(), 1)
        self.assertEqual(active.first().title, "Active")


class HomepageRenderingTests(TestCase):
    def setUp(self):
        self.slide = HeroSlide.objects.create(
            title="اسلاید فعال", desktop_image=_img("hero.png"),
            is_active=True, display_order=0,
        )
        self.inactive_slide = HeroSlide.objects.create(
            title="غیرفعال", desktop_image=_img("hero2.png"),
            is_active=False, display_order=1,
        )

    def test_active_slide_on_homepage(self):
        response = self.client.get("/")
        self.assertContains(response, "اسلاید فعال")

    def test_inactive_slide_hidden(self):
        response = self.client.get("/")
        self.assertNotContains(response, "غیرفعال")
