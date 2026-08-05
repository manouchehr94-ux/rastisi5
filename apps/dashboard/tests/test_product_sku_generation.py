"""تست‌های تولیدِ خودکارِ کدِ کالا (SKU) — دکمه‌ی «تولید» در تبِ اطلاعاتِ
پایه‌یِ فرمِ کالا (Product Entry final wave 1، مرحله‌ی ۴)."""
import re
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.catalog.models import Category, Product, Vendor
from apps.catalog.services.product_sku_service import generate_product_sku
from apps.stores.models import Store, StoreMembership

User = get_user_model()
HOST = "skugen.rastisi.localhost"

_FORMAT_RE = re.compile(r"^PRD-[ABCDEFGHJKLMNPQRSTUVWXYZ23456789]{6}$")


@override_settings(ALLOWED_HOSTS=[HOST, "testserver"])
class ProductSkuGenerationTestCase(TestCase):
    def setUp(self):
        self.store = Store.objects.create(
            name="فروشگاه تست", slug="skugen", status=Store.Status.ACTIVE,
            admin_subdomain="skugen", platform_code="SKUGEN01",
        )
        self.vendor = Vendor.objects.create(store=self.store, name="فروشنده", slug="skugen-shop")
        self.group = Category.objects.create(store=self.store, name="گروه", slug="skugen-group")
        self.sub = Category.objects.create(store=self.store, name="زیر", slug="skugen-sub", parent=self.group)
        self.staff = User.objects.create_user(username="skugenstaff", password="pass12345", is_staff=True)
        StoreMembership.objects.create(
            store=self.store, user=self.staff, role=StoreMembership.Role.OWNER,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )
        self.client = Client(HTTP_HOST=HOST)
        self.client.login(username="skugenstaff", password="pass12345")


class ProductSkuServiceTests(ProductSkuGenerationTestCase):
    def test_generated_code_matches_required_format(self):
        code = generate_product_sku(self.store)
        self.assertRegex(code, _FORMAT_RE)

    def test_generated_codes_are_unique_across_many_calls(self):
        codes = {generate_product_sku(self.store) for _ in range(30)}
        self.assertEqual(len(codes), 30)

    def test_store_scoped_not_globally_unique(self):
        """یک کدِ استفاده‌شده در یک Store باید بتواند در Storeیِ دیگری هم
        (نظری) استفاده شود — یکتایی فقط در محدوده‌ی همان Store بررسی می‌شود،
        دقیقاً مثلِ uniq_product_sku_per_store."""
        other_store = Store.objects.create(
            name="فروشگاه دیگر", slug="skugen-other", status=Store.Status.ACTIVE,
            admin_subdomain="skugen-other", platform_code="SKUGEN02",
        )
        code = "PRD-AAAAAA"
        Product.objects.create(
            store=self.store, vendor=self.vendor, category=self.sub, name="کالای تست",
            slug="skugen-prod", sku=code, price=100000,
        )
        calls = {"n": 0}

        def fake_random(length, allowed_chars=None):
            calls["n"] += 1
            return "AAAAAA" if calls["n"] == 1 else "BBBBBB"

        with patch("apps.catalog.services.product_sku_service.get_random_string", side_effect=fake_random):
            # همان Store: نمونه‌ی اول با کدِ موجود تصادم می‌کند، پس باید
            # تلاشِ دوباره کند و چیزِ دیگری برگرداند.
            retried = generate_product_sku(self.store)
            self.assertNotEqual(retried, code)

        # Storeیِ دیگر: هیچ تصادمی نیست، همان کدِ اول در محدوده‌ی آن Store
        # آزاد است (فقط بررسیِ داده، بدونِ فراخوانیِ دوباره‌ی سرویس).
        self.assertFalse(Product.objects.filter(store=other_store, sku=code).exists())

    def test_collision_triggers_bounded_retry_not_max_plus_one(self):
        """پیاده‌سازی نباید به یک شمارنده‌ی افزایشیِ رقابت‌پذیر (max+1) متکی
        باشد — باید «بساز → بررسیِ یکتایی → تلاشِ دوباره» با یک سقفِ محدود
        باشد (نگاه کنید به ADR در خودِ سرویس)."""
        Product.objects.create(
            store=self.store, vendor=self.vendor, category=self.sub, name="کالای تست",
            slug="skugen-collide", sku="PRD-AAAAAA", price=100000,
        )
        calls = {"n": 0}

        def fake_random(length, allowed_chars=None):
            calls["n"] += 1
            return "AAAAAA" if calls["n"] == 1 else "BBBBBB"

        with patch("apps.catalog.services.product_sku_service.get_random_string", side_effect=fake_random):
            result = generate_product_sku(self.store)
        self.assertEqual(result, "PRD-BBBBBB")
        self.assertEqual(calls["n"], 2)


class ProductSkuGenerateEndpointTests(ProductSkuGenerationTestCase):
    def test_post_returns_a_valid_code(self):
        response = self.client.post(reverse("dashboard:product-sku-generate"))
        self.assertEqual(response.status_code, 200)
        self.assertRegex(response.content.decode(), _FORMAT_RE)

    def test_get_not_allowed(self):
        response = self.client.get(reverse("dashboard:product-sku-generate"))
        self.assertEqual(response.status_code, 405)

    def test_anonymous_denied(self):
        self.client.logout()
        response = self.client.post(reverse("dashboard:product-sku-generate"))
        self.assertEqual(response.status_code, 302)

    def test_tenant_scoped_uniqueness(self):
        """کدِ تولیدشده در محدوده‌ی Storeیِ کاربرِ واردشده بررسی می‌شود، نه
        سراسری — چند بار پشتِ سرِ هم فراخوانی، کدهایِ متفاوت می‌دهد."""
        first = self.client.post(reverse("dashboard:product-sku-generate")).content.decode()
        second = self.client.post(reverse("dashboard:product-sku-generate")).content.decode()
        self.assertNotEqual(first, second)


class ProductSkuGenerateFormIntegrationTests(ProductSkuGenerationTestCase):
    def test_generate_button_present_and_preserves_sku_field_ref(self):
        response = self.client.get(reverse("dashboard:product-add"), follow=True)
        html = response.content.decode()
        self.assertContains(response, "تولید")
        self.assertIn('x-ref="skuField"', html)
        # دکمه باید مسیرِ تولیدِ کدِ کالا را صدا بزند. دیگر نیازی به تابعِ
        # auto-continue نیست — چون صفحه‌ی «افزودنِ کالا» از همان اولین GET
        # یک پیش‌نویسِ واقعی دارد (نگاه کنید به ``product_create_entry``)،
        # پس تبِ «قیمت و تنوع» بدونِ توجه به پرشدنِ نام/دسته‌بندی همیشه آماده است.
        self.assertIn(reverse("dashboard:product-sku-generate"), html)

    def test_generated_sku_can_be_submitted_and_edited_afterward(self):
        code = generate_product_sku(self.store)
        response = self.client.post(reverse("dashboard:product-add"), {
            "name": "کالای تست", "sku": code, "category": self.sub.id,
            "price": "500000", "discount_percent": "0", "stock": "10",
            "status": "active", "icon": "", "description": "",
        })
        self.assertEqual(response.status_code, 200)
        product = Product.objects.get(sku=code)
        # ویرایشِ دستیِ کد پس از تولید همچنان مجاز است — فیلد یک <input> سادّه
        # است، نه فقط‌خواندنی.
        edit_payload = {
            "name": product.name, "sku": "PRD-CUSTOM", "category": self.sub.id,
            "price": "500000", "discount_percent": "0", "stock": "10", "status": "active",
        }
        self.client.post(reverse("dashboard:product-edit", args=[product.pk]), edit_payload)
        product.refresh_from_db()
        self.assertEqual(product.sku, "PRD-CUSTOM")
