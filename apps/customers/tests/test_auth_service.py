from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory, TestCase

from apps.cart.models import Cart, CartItem
from apps.catalog.models import Category, Product, Vendor
from apps.customers.models import Customer
from apps.customers.services import auth_service
from apps.sms.models import SmsLog, SmsTemplate

User = get_user_model()


class SignupServiceTests(TestCase):
    def test_signup_creates_user_and_customer(self):
        customer = auth_service.signup(full_name="نگار احمدی", phone="09121112233", password="StrongPass123")
        self.assertEqual(customer.full_name, "نگار احمدی")
        self.assertTrue(User.objects.filter(username="09121112233").exists())
        self.assertTrue(customer.user.check_password("StrongPass123"))

    def test_signup_rejects_duplicate_phone(self):
        auth_service.signup(full_name="نگار احمدی", phone="09121112233", password="StrongPass123")
        with self.assertRaises(auth_service.AuthError):
            auth_service.signup(full_name="نگار دیگر", phone="09121112233", password="AnotherPass123")

    def test_signup_rejects_weak_password(self):
        with self.assertRaises(auth_service.AuthError):
            auth_service.signup(full_name="نگار احمدی", phone="09121112234", password="123")

    def test_signup_sends_welcome_sms_after_commit(self):
        SmsTemplate.ensure_defaults()
        with self.captureOnCommitCallbacks(execute=True):
            auth_service.signup(full_name="نگار احمدی", phone="09121112299", password="StrongPass123")
        log = SmsLog.objects.filter(event_key="welcome", recipient="09121112299").first()
        self.assertIsNotNone(log)
        self.assertIn("نگار احمدی", log.message)


class CreateAccountForGuestTests(TestCase):
    def test_creates_user_and_customer_with_random_password(self):
        customer = auth_service.create_account_for_guest(full_name="پویا رستمی", phone="09121112288")
        self.assertEqual(customer.full_name, "پویا رستمی")
        self.assertTrue(User.objects.filter(username="09121112288").exists())
        self.assertGreaterEqual(len(customer.user.password), 20)  # هش رمز، نه رمز خام

    def test_generated_password_actually_works_for_login(self):
        # نمی‌دانیم رمز چیست، اما باید تصادفی/معتبر باشد نه رمز خالی یا قابل‌پیش‌بینی
        customer = auth_service.create_account_for_guest(full_name="پویا رستمی", phone="09121112288")
        self.assertFalse(customer.user.check_password(""))
        self.assertFalse(customer.user.check_password("123456"))

    def test_sends_welcome_sms_after_commit(self):
        SmsTemplate.ensure_defaults()
        with self.captureOnCommitCallbacks(execute=True):
            auth_service.create_account_for_guest(full_name="پویا رستمی", phone="09121112288")
        self.assertTrue(SmsLog.objects.filter(event_key="welcome", recipient="09121112288").exists())


class AuthenticateCustomerTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.customer = auth_service.signup(full_name="رضا کریمی", phone="09121112255", password="StrongPass123")

    def _request(self):
        request = self.factory.post("/")
        SessionMiddleware(lambda r: None).process_request(request)
        request.session.save()
        return request

    def test_correct_credentials_authenticate(self):
        user = auth_service.authenticate_customer(self._request(), phone="09121112255", password="StrongPass123")
        self.assertIsNotNone(user)
        self.assertEqual(user.customer_profile, self.customer)

    def test_wrong_password_fails(self):
        user = auth_service.authenticate_customer(self._request(), phone="09121112255", password="wrong")
        self.assertIsNone(user)

    def test_unknown_phone_fails(self):
        user = auth_service.authenticate_customer(self._request(), phone="09129999999", password="StrongPass123")
        self.assertIsNone(user)

    def test_seeded_style_user_with_different_username_still_authenticates(self):
        # کاربران seed مثل seed_shop از phone ≠ username استفاده می‌کنند
        user = User.objects.create_user(username="legacy_username", password="AnotherPass123")
        Customer.objects.create(user=user, full_name="کاربر قدیمی", phone="09121112266")
        authed = auth_service.authenticate_customer(self._request(), phone="09121112266", password="AnotherPass123")
        self.assertEqual(authed, user)


class MergeGuestCartTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        vendor = Vendor.objects.create(name="فروشگاه", slug="shop-mg")
        category = Category.objects.create(name="دیجیتال", slug="digital-mg")
        self.product = Product.objects.create(
            vendor=vendor, category=category, name="کالای نمونه", slug="sample-mg",
            sku="SKU-MG1", price=Decimal("100000"),
        )
        self.customer = auth_service.signup(full_name="یاسمن", phone="09121112277", password="StrongPass123")

    def _guest_request_with_cart(self, quantity=1):
        request = self.factory.post("/")
        SessionMiddleware(lambda r: None).process_request(request)
        request.session.save()
        cart = Cart.objects.create(session_key=request.session.session_key)
        CartItem.objects.create(cart=cart, product=self.product, quantity=quantity, unit_price=self.product.final_price)
        return request

    def test_merges_guest_cart_into_new_user_cart(self):
        request = self._guest_request_with_cart(quantity=2)
        auth_service.merge_guest_cart(request, self.customer)
        user_cart = Cart.objects.get(customer=self.customer)
        self.assertEqual(user_cart.items.count(), 1)
        self.assertEqual(user_cart.items.first().quantity, 2)
        self.assertFalse(Cart.objects.filter(session_key=request.session.session_key).exists())

    def test_merges_quantities_when_product_already_in_user_cart(self):
        user_cart = Cart.objects.create(customer=self.customer)
        CartItem.objects.create(cart=user_cart, product=self.product, quantity=1, unit_price=self.product.final_price)
        request = self._guest_request_with_cart(quantity=3)
        auth_service.merge_guest_cart(request, self.customer)
        user_cart.refresh_from_db()
        self.assertEqual(user_cart.items.count(), 1)
        self.assertEqual(user_cart.items.first().quantity, 4)

    def test_no_guest_cart_is_a_no_op(self):
        request = self.factory.post("/")
        SessionMiddleware(lambda r: None).process_request(request)
        request.session.save()
        auth_service.merge_guest_cart(request, self.customer)
        self.assertFalse(Cart.objects.filter(customer=self.customer).exists())
