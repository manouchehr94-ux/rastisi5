from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.catalog.models import Category, Product, Vendor
from apps.customers.models import Customer, Wishlist

User = get_user_model()


class WishlistToggleTests(TestCase):
    def setUp(self):
        vendor = Vendor.objects.create(name="فروشگاه", slug="shop-wl")
        category = Category.objects.create(name="دیجیتال", slug="digital-wl")
        self.product = Product.objects.create(
            vendor=vendor, category=category, name="کالای نمونه", slug="sample-wl",
            sku="SKU-WL1", price=Decimal("150000"),
        )
        self.url = reverse("customers:wishlist-toggle", args=[self.product.slug])

    def test_anonymous_user_cannot_toggle_and_gets_login_prompt(self):
        response = self.client.post(self.url)
        self.assertEqual(Wishlist.objects.count(), 0)
        self.assertIn("HX-Trigger", response.headers)
        self.assertIn("open-login", response.headers["HX-Trigger"])

    def test_logged_in_customer_can_add_to_wishlist(self):
        user = User.objects.create_user(username="wl_user1", password="pass12345")
        customer = Customer.objects.create(user=user, full_name="کاربر تست", phone="09121110031")
        self.client.login(username="wl_user1", password="pass12345")

        response = self.client.post(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(Wishlist.objects.filter(customer=customer, product=self.product).exists())
        self.assertContains(response, "on")

    def test_toggling_twice_removes_from_wishlist(self):
        user = User.objects.create_user(username="wl_user2", password="pass12345")
        Customer.objects.create(user=user, full_name="کاربر تست ۲", phone="09121110032")
        self.client.login(username="wl_user2", password="pass12345")

        self.client.post(self.url)
        self.assertEqual(Wishlist.objects.count(), 1)
        self.client.post(self.url)
        self.assertEqual(Wishlist.objects.count(), 0)

    def test_toggle_updates_header_wishlist_count_oob(self):
        user = User.objects.create_user(username="wl_user3", password="pass12345")
        Customer.objects.create(user=user, full_name="کاربر تست ۳", phone="09121110033")
        self.client.login(username="wl_user3", password="pass12345")

        response = self.client.post(self.url)
        self.assertContains(response, 'id="wishlist-count"')
        self.assertContains(response, "hx-swap-oob")

    def test_get_request_not_allowed(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 405)


class WishlistListViewTests(TestCase):
    def setUp(self):
        vendor = Vendor.objects.create(name="فروشگاه", slug="shop-wll")
        category = Category.objects.create(name="دیجیتال", slug="digital-wll")
        self.product = Product.objects.create(
            vendor=vendor, category=category, name="کالای مورد علاقه", slug="sample-wll",
            sku="SKU-WLL1", price=Decimal("150000"),
        )
        self.other_product = Product.objects.create(
            vendor=vendor, category=category, name="کالای دیگر", slug="sample-wll-2",
            sku="SKU-WLL2", price=Decimal("50000"),
        )

    def test_anonymous_user_sees_login_prompt(self):
        response = self.client.get(reverse("customers:wishlist"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "ابتدا وارد حساب کاربری خود شوید")

    def test_logged_in_customer_with_empty_wishlist_sees_empty_state(self):
        user = User.objects.create_user(username="wl_user4", password="pass12345")
        Customer.objects.create(user=user, full_name="کاربر تست ۴", phone="09121110034")
        self.client.login(username="wl_user4", password="pass12345")

        response = self.client.get(reverse("customers:wishlist"))
        self.assertContains(response, "لیست علاقه‌مندی‌های شما خالی است")

    def test_logged_in_customer_sees_only_their_wishlisted_products(self):
        user = User.objects.create_user(username="wl_user5", password="pass12345")
        customer = Customer.objects.create(user=user, full_name="کاربر تست ۵", phone="09121110035")
        Wishlist.objects.create(customer=customer, product=self.product)
        self.client.login(username="wl_user5", password="pass12345")

        response = self.client.get(reverse("customers:wishlist"))
        self.assertContains(response, "کالای مورد علاقه")
        self.assertNotContains(response, "کالای دیگر")
