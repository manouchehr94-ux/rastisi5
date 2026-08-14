"""Phase 1 correction (tenant safety) — ``resolve_background_media_url``.

مکملِ ``apps.storefront_builder.section_registry.validate_background_settings``:
آن تابع فقط شکلِ ``media_asset_id`` را اعتبارسنجی می‌کند (بدونِ دیتابیس)؛
این تابع لایه‌ای است که واقعاً مالکیتِ Store را چک می‌کند و URLِ نهایی را
حل می‌کند — دقیقاً همان تفکیکِ مسئولیتی که ``resolve_destination_setting``
برایِ بلوکِ ``destination`` دارد."""

from io import BytesIO

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from PIL import Image

from apps.content.models import MediaAsset
from apps.content.services import resolve_background_media_url
from apps.stores.models import Store


def _akhlaghi():
    return Store.objects.get(slug="akhlaghi")


def _img(name="bg.png"):
    buf = BytesIO()
    Image.new("RGB", (10, 10), (10, 20, 30)).save(buf, "PNG")
    return SimpleUploadedFile(name, buf.getvalue(), content_type="image/png")


class ResolveBackgroundMediaUrlTests(TestCase):
    def setUp(self):
        self.store = _akhlaghi()

    def test_non_image_mode_returns_none(self):
        self.assertIsNone(resolve_background_media_url(self.store, {"mode": "theme", "media_asset_id": 1}))

    def test_missing_media_asset_id_returns_none(self):
        self.assertIsNone(resolve_background_media_url(self.store, {"mode": "image", "media_asset_id": None}))

    def test_none_background_returns_none(self):
        self.assertIsNone(resolve_background_media_url(self.store, None))

    def test_valid_own_store_asset_resolves_to_real_url(self):
        asset = MediaAsset.objects.create(store=self.store, image=_img())
        url = resolve_background_media_url(self.store, {"mode": "image", "media_asset_id": asset.pk})
        self.assertEqual(url, asset.image.url)
        self.assertIn("media-assets", url)  # sanity: a real MEDIA_URL-backed path, not a placeholder

    def test_nonexistent_media_asset_id_returns_none_not_crash(self):
        url = resolve_background_media_url(self.store, {"mode": "image", "media_asset_id": 999999})
        self.assertIsNone(url)

    def test_another_stores_asset_never_leaks(self):
        """قلبِ تصمیمِ ایمنیِ مستأجر: یک section نباید بتواند به رسانه‌ی
        فروشگاهِ دیگری اشاره کند و آن را نمایش دهد."""
        other_store = Store.objects.create(name="فروشگاه ب", slug="bg-cross", admin_subdomain="bg-cross")
        other_asset = MediaAsset.objects.create(store=other_store, image=_img())
        url = resolve_background_media_url(self.store, {"mode": "image", "media_asset_id": other_asset.pk})
        self.assertIsNone(url)
