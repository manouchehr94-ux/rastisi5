"""تست‌های زیرساخت مقصد امن — اعتبارسنجی و حل مقصد.

تست‌ها از مدل واقعی HeroSlide (که از DestinationMixin ارث‌بری می‌کند)
برای اعتبارسنجی استفاده می‌کنند. این روش بدون مدل تستی جداگانه کار
می‌کند و از مشکل table-collision در full suite جلوگیری می‌کند.

علت: مدل تستی managed=False با FK به Category/Product/Brand باعث می‌شد
Django delete-collector هنگام حذف Category به جدول ناموجود مراجعه کند.
"""

from decimal import Decimal
from io import BytesIO

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase

from apps.catalog.models import Brand, Category, Product, Vendor
from apps.content.models import DestinationType, HeroSlide, validate_external_url
from apps.content.services import resolve_destination_url
from apps.stores.models import Store

User = get_user_model()


def _img(name="dest_test.png"):
    """ساخت تصویر حداقلی برای فیلد اجباری desktop_image."""
    from PIL import Image
    buf = BytesIO()
    Image.new("RGB", (10, 10), (200, 100, 50)).save(buf, "PNG")
    return SimpleUploadedFile(name, buf.getvalue(), content_type="image/png")


def _make_instance(**kwargs):
    """ساخت یک HeroSlide بدون ذخیره — برای تست اعتبارسنجی DestinationMixin."""
    defaults = {
        "title": "تست مقصد",
        "desktop_image": _img(),
        "destination_type": DestinationType.NONE,
        "destination_category": None,
        "destination_product": None,
        "destination_brand": None,
        "destination_external_url": "",
        "open_in_new_tab": False,
        "show_button": False,
    }
    defaults.update(kwargs)
    obj = HeroSlide(**defaults)
    # Set _id fields for FK validation
    if defaults.get("destination_category"):
        obj.destination_category_id = defaults["destination_category"].pk
    if defaults.get("destination_product"):
        obj.destination_product_id = defaults["destination_product"].pk
    if defaults.get("destination_brand"):
        obj.destination_brand_id = defaults["destination_brand"].pk
    return obj


class DestinationValidationTests(TestCase):
    """اعتبارسنجی انسجام مقصد."""

    def setUp(self):
        store = Store.objects.get(slug="akhlaghi")
        self.vendor = Vendor.objects.create(store=store, name="فروشنده", slug="vendor-dv")
        self.category = Category.objects.create(store=store, name="دسته", slug="cat-dv")
        self.product = Product.objects.create(
            store=store, vendor=self.vendor, category=self.category,
            name="محصول", slug="prod-dv", sku="DV-1",
            price=Decimal("100000"), stock=10,
        )
        self.brand = Brand.objects.create(store=store, name="برند", slug="brand-dv")

    def test_none_with_no_destination_passes(self):
        obj = _make_instance(destination_type=DestinationType.NONE)
        obj.clean()  # Should not raise

    def test_none_with_category_fails(self):
        obj = _make_instance(
            destination_type=DestinationType.NONE,
            destination_category=self.category,
        )
        with self.assertRaises(ValidationError):
            obj.clean()

    def test_none_with_external_url_fails(self):
        obj = _make_instance(
            destination_type=DestinationType.NONE,
            destination_external_url="https://example.com",
        )
        with self.assertRaises(ValidationError):
            obj.clean()

    def test_category_with_category_passes(self):
        obj = _make_instance(
            destination_type=DestinationType.CATEGORY,
            destination_category=self.category,
        )
        obj.clean()

    def test_category_without_category_fails(self):
        obj = _make_instance(destination_type=DestinationType.CATEGORY)
        with self.assertRaises(ValidationError):
            obj.clean()

    def test_category_with_product_also_fails(self):
        obj = _make_instance(
            destination_type=DestinationType.CATEGORY,
            destination_category=self.category,
            destination_product=self.product,
        )
        with self.assertRaises(ValidationError):
            obj.clean()

    def test_product_with_product_passes(self):
        obj = _make_instance(
            destination_type=DestinationType.PRODUCT,
            destination_product=self.product,
        )
        obj.clean()

    def test_product_without_product_fails(self):
        obj = _make_instance(destination_type=DestinationType.PRODUCT)
        with self.assertRaises(ValidationError):
            obj.clean()

    def test_brand_with_brand_passes(self):
        obj = _make_instance(
            destination_type=DestinationType.BRAND,
            destination_brand=self.brand,
        )
        obj.clean()

    def test_brand_without_brand_fails(self):
        obj = _make_instance(destination_type=DestinationType.BRAND)
        with self.assertRaises(ValidationError):
            obj.clean()

    def test_external_with_https_passes(self):
        obj = _make_instance(
            destination_type=DestinationType.EXTERNAL,
            destination_external_url="https://example.com/page",
        )
        obj.clean()

    def test_external_with_http_passes(self):
        obj = _make_instance(
            destination_type=DestinationType.EXTERNAL,
            destination_external_url="http://example.com",
        )
        obj.clean()

    def test_external_without_url_fails(self):
        obj = _make_instance(destination_type=DestinationType.EXTERNAL)
        with self.assertRaises(ValidationError):
            obj.clean()

    def test_external_with_internal_fk_fails(self):
        obj = _make_instance(
            destination_type=DestinationType.EXTERNAL,
            destination_external_url="https://example.com",
            destination_category=self.category,
        )
        with self.assertRaises(ValidationError):
            obj.clean()

    def test_javascript_scheme_rejected(self):
        obj = _make_instance(
            destination_type=DestinationType.EXTERNAL,
            destination_external_url="javascript:alert(1)",
        )
        with self.assertRaises(ValidationError):
            obj.clean()

    def test_data_scheme_rejected(self):
        obj = _make_instance(
            destination_type=DestinationType.EXTERNAL,
            destination_external_url="data:text/html,<script>alert(1)</script>",
        )
        with self.assertRaises(ValidationError):
            obj.clean()

    def test_protocol_relative_rejected(self):
        obj = _make_instance(
            destination_type=DestinationType.EXTERNAL,
            destination_external_url="//evil.com/path",
        )
        with self.assertRaises(ValidationError):
            obj.clean()

    def test_malformed_url_rejected(self):
        obj = _make_instance(
            destination_type=DestinationType.EXTERNAL,
            destination_external_url="not a url at all",
        )
        with self.assertRaises(ValidationError):
            obj.clean()

    def test_whitespace_normalized(self):
        obj = _make_instance(
            destination_type=DestinationType.EXTERNAL,
            destination_external_url="  https://example.com  ",
        )
        obj.clean()  # Should pass after strip

    def test_search_with_no_destination_passes(self):
        obj = _make_instance(destination_type=DestinationType.SEARCH)
        obj.clean()

    def test_search_with_category_fails(self):
        obj = _make_instance(destination_type=DestinationType.SEARCH, destination_category=self.category)
        with self.assertRaises(ValidationError):
            obj.clean()

    def test_cart_with_no_destination_passes(self):
        obj = _make_instance(destination_type=DestinationType.CART)
        obj.clean()

    def test_cart_with_external_url_fails(self):
        obj = _make_instance(destination_type=DestinationType.CART, destination_external_url="https://example.com")
        with self.assertRaises(ValidationError):
            obj.clean()


class DestinationResolverTests(TestCase):
    """تست‌های حل‌کننده‌ی مقصد."""

    def setUp(self):
        store = Store.objects.get(slug="akhlaghi")
        self.vendor = Vendor.objects.create(store=store, name="فروشنده", slug="vendor-dr")
        self.category = Category.objects.create(store=store, name="دسته", slug="cat-dr")
        self.product = Product.objects.create(
            store=store, vendor=self.vendor, category=self.category,
            name="محصول", slug="prod-dr", sku="DR-1",
            price=Decimal("100000"), stock=10,
        )
        self.brand = Brand.objects.create(store=store, name="برند", slug="brand-dr")

    def test_category_resolves(self):
        obj = _make_instance(
            destination_type=DestinationType.CATEGORY,
            destination_category=self.category,
        )
        url = resolve_destination_url(obj)
        self.assertIn("category=cat-dr", url)

    def test_product_resolves(self):
        obj = _make_instance(
            destination_type=DestinationType.PRODUCT,
            destination_product=self.product,
        )
        url = resolve_destination_url(obj)
        self.assertIn("prod-dr", url)

    def test_brand_resolves(self):
        obj = _make_instance(
            destination_type=DestinationType.BRAND,
            destination_brand=self.brand,
        )
        url = resolve_destination_url(obj)
        self.assertIn("brand=brand-dr", url)

    def test_external_resolves(self):
        obj = _make_instance(
            destination_type=DestinationType.EXTERNAL,
            destination_external_url="https://example.com/page",
        )
        url = resolve_destination_url(obj)
        self.assertEqual(url, "https://example.com/page")

    def test_none_returns_none(self):
        obj = _make_instance(destination_type=DestinationType.NONE)
        self.assertIsNone(resolve_destination_url(obj))

    def test_deleted_category_returns_none(self):
        obj = _make_instance(
            destination_type=DestinationType.CATEGORY,
            destination_category=None,  # Simulates SET_NULL after deletion
        )
        obj.destination_category_id = None
        self.assertIsNone(resolve_destination_url(obj))

    def test_deleted_product_returns_none(self):
        obj = _make_instance(
            destination_type=DestinationType.PRODUCT,
            destination_product=None,
        )
        obj.destination_product_id = None
        self.assertIsNone(resolve_destination_url(obj))

    def test_search_resolves(self):
        obj = _make_instance(destination_type=DestinationType.SEARCH)
        url = resolve_destination_url(obj)
        self.assertIsNotNone(url)
        self.assertIn("/products/", url)

    def test_cart_resolves(self):
        obj = _make_instance(destination_type=DestinationType.CART)
        url = resolve_destination_url(obj)
        self.assertIsNotNone(url)

    def test_resolver_never_returns_hash(self):
        """Resolver must never return '#' under any circumstance."""
        for dtype in DestinationType.values:
            obj = _make_instance(destination_type=dtype)
            url = resolve_destination_url(obj)
            self.assertNotEqual(url, "#")


class ExternalURLValidatorTests(TestCase):
    """تست‌های اعتبارسنجی URL خارجی."""

    def test_https_valid(self):
        validate_external_url("https://example.com")  # No exception

    def test_http_valid(self):
        validate_external_url("http://example.com")

    def test_mailto_valid(self):
        validate_external_url("mailto:info@example.com")

    def test_tel_valid(self):
        validate_external_url("tel:+989121234567")

    def test_javascript_rejected(self):
        with self.assertRaises(ValidationError):
            validate_external_url("javascript:alert(1)")

    def test_data_rejected(self):
        with self.assertRaises(ValidationError):
            validate_external_url("data:text/html,test")

    def test_protocol_relative_rejected(self):
        with self.assertRaises(ValidationError):
            validate_external_url("//evil.com")

    def test_empty_rejected(self):
        with self.assertRaises(ValidationError):
            validate_external_url("")

    def test_whitespace_only_rejected(self):
        with self.assertRaises(ValidationError):
            validate_external_url("   ")

    def test_vbscript_rejected(self):
        with self.assertRaises(ValidationError):
            validate_external_url("vbscript:MsgBox")

    def test_ftp_rejected(self):
        with self.assertRaises(ValidationError):
            validate_external_url("ftp://files.example.com")
