from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.cart.models import Cart, CartItem
from apps.catalog.models import Category, Product, Vendor
from apps.customers.models import Customer
from apps.sms.models import OtpCode, SmsTemplate

User = get_user_model()


class SignupViewTests(TestCase):
    def test_valid_signup_logs_user_in_with_full_page_refresh(self):
        response = self.client.post(reverse("customers:signup"), {
            "full_name": "نگار احمدی", "phone": "09121114455", "password": "StrongPass123",
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("HX-Refresh"), "true")
        self.assertTrue(Customer.objects.filter(phone="09121114455").exists())
        self.assertIn("_auth_user_id", self.client.session)

    def test_duplicate_phone_shows_error_and_does_not_log_in(self):
        Customer.objects.create(
            user=User.objects.create_user(username="09121114466", password="StrongPass123"),
            full_name="کاربر موجود", phone="09121114466",
        )
        response = self.client.post(reverse("customers:signup"), {
            "full_name": "دیگری", "phone": "09121114466", "password": "StrongPass123",
        })
        self.assertNotIn("HX-Refresh", response.headers)
        self.assertContains(response, "قبلاً ثبت‌نام کرده است")
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_signup_merges_guest_cart(self):
        vendor = Vendor.objects.create(name="فروشگاه", slug="shop-sgc")
        category = Category.objects.create(name="دیجیتال", slug="digital-sgc")
        product = Product.objects.create(
            vendor=vendor, category=category, name="کالای نمونه", slug="sample-sgc",
            sku="SKU-SGC1", price=Decimal("100000"),
        )
        self.client.post(reverse("cart:add", args=[product.slug]), {"quantity": 2})
        self.client.post(reverse("customers:signup"), {
            "full_name": "پویا", "phone": "09121114477", "password": "StrongPass123",
        })
        customer = Customer.objects.get(phone="09121114477")
        cart = Cart.objects.get(customer=customer)
        self.assertEqual(cart.items.first().quantity, 2)


class LoginViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="09121115566", password="StrongPass123")
        Customer.objects.create(user=self.user, full_name="سینا رستمی", phone="09121115566")

    def test_valid_login_refreshes_page(self):
        response = self.client.post(reverse("customers:login"), {
            "phone": "09121115566", "password": "StrongPass123",
        })
        self.assertEqual(response.headers.get("HX-Refresh"), "true")
        self.assertIn("_auth_user_id", self.client.session)

    def test_wrong_password_shows_error(self):
        response = self.client.post(reverse("customers:login"), {
            "phone": "09121115566", "password": "wrongpass",
        })
        self.assertNotIn("HX-Refresh", response.headers)
        self.assertContains(response, "اشتباه است")
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_login_merges_guest_cart(self):
        vendor = Vendor.objects.create(name="فروشگاه", slug="shop-lgc")
        category = Category.objects.create(name="دیجیتال", slug="digital-lgc")
        product = Product.objects.create(
            vendor=vendor, category=category, name="کالای نمونه", slug="sample-lgc",
            sku="SKU-LGC1", price=Decimal("50000"),
        )
        self.client.post(reverse("cart:add", args=[product.slug]), {"quantity": 3})
        self.client.post(reverse("customers:login"), {"phone": "09121115566", "password": "StrongPass123"})
        cart = Cart.objects.get(customer=self.user.customer_profile)
        self.assertEqual(cart.items.first().quantity, 3)


class LogoutViewTests(TestCase):
    def test_logout_ends_session_and_redirects_home(self):
        user = User.objects.create_user(username="09121116677", password="StrongPass123")
        Customer.objects.create(user=user, full_name="کاربر", phone="09121116677")
        self.client.login(username="09121116677", password="StrongPass123")
        response = self.client.post(reverse("customers:logout"))
        self.assertRedirects(response, reverse("catalog:home"))
        self.assertNotIn("_auth_user_id", self.client.session)


class OtpLoginViewTests(TestCase):
    def setUp(self):
        SmsTemplate.ensure_defaults()
        self.user = User.objects.create_user(username="09121118899", password="StrongPass123")
        Customer.objects.create(user=self.user, full_name="مهسا کریمی", phone="09121118899")

    def test_request_for_existing_account_moves_to_verify_stage(self):
        response = self.client.post(reverse("customers:otp-request"), {"phone": "09121118899"})
        self.assertContains(response, "کد تأیید")
        self.assertTrue(OtpCode.objects.filter(phone="09121118899").exists())

    def test_request_for_unknown_phone_shows_error_and_sends_nothing(self):
        response = self.client.post(reverse("customers:otp-request"), {"phone": "09129990000"})
        self.assertContains(response, "یافت نشد")
        self.assertFalse(OtpCode.objects.filter(phone="09129990000").exists())

    def test_verify_with_correct_code_logs_in(self):
        self.client.post(reverse("customers:otp-request"), {"phone": "09121118899"})
        otp = OtpCode.objects.get(phone="09121118899")
        response = self.client.post(reverse("customers:otp-login"), {"phone": "09121118899", "code": otp.code})
        self.assertEqual(response.headers.get("HX-Refresh"), "true")
        self.assertIn("_auth_user_id", self.client.session)

    def test_verify_with_wrong_code_shows_error_and_does_not_log_in(self):
        self.client.post(reverse("customers:otp-request"), {"phone": "09121118899"})
        response = self.client.post(reverse("customers:otp-login"), {"phone": "09121118899", "code": "000000"})
        self.assertContains(response, "صحیح نیست")
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_reset_view_does_not_send_a_new_code(self):
        self.client.post(reverse("customers:otp-request"), {"phone": "09121118899"})
        count_before = OtpCode.objects.count()
        response = self.client.get(reverse("customers:otp-reset"))
        self.assertContains(response, "شماره موبایل")
        self.assertEqual(OtpCode.objects.count(), count_before)

    def test_otp_login_merges_guest_cart(self):
        vendor = Vendor.objects.create(name="فروشگاه", slug="shop-ogc")
        category = Category.objects.create(name="دیجیتال", slug="digital-ogc")
        product = Product.objects.create(
            vendor=vendor, category=category, name="کالای نمونه", slug="sample-ogc",
            sku="SKU-OGC1", price=Decimal("70000"),
        )
        self.client.post(reverse("cart:add", args=[product.slug]), {"quantity": 1})
        self.client.post(reverse("customers:otp-request"), {"phone": "09121118899"})
        otp = OtpCode.objects.get(phone="09121118899")
        self.client.post(reverse("customers:otp-login"), {"phone": "09121118899", "code": otp.code})
        cart = Cart.objects.get(customer=self.user.customer_profile)
        self.assertEqual(cart.items.first().quantity, 1)


class HeaderAuthStateTests(TestCase):
    def test_anonymous_sees_login_button(self):
        response = self.client.get(reverse("catalog:home"))
        self.assertContains(response, "ورود | ثبت‌نام")

    def test_authenticated_sees_account_link(self):
        user = User.objects.create_user(username="09121117788", password="StrongPass123")
        Customer.objects.create(user=user, full_name="کاربر وارد‌شده", phone="09121117788")
        self.client.login(username="09121117788", password="StrongPass123")
        response = self.client.get(reverse("catalog:home"))
        self.assertContains(response, "کاربر وارد‌شده")
        self.assertNotContains(response, "ورود | ثبت‌نام")
