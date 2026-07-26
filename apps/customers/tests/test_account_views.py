from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.catalog.models import Category, Product, Vendor
from apps.customers.models import Address, Customer
from apps.orders.models import Order, PaymentGateway, ShippingMethod
from apps.stores.models import Store

User = get_user_model()


class AccountHomeViewTests(TestCase):
    def test_anonymous_sees_login_prompt(self):
        response = self.client.get(reverse("customers:account"))
        self.assertContains(response, "ابتدا وارد حساب کاربری خود شوید")

    def test_authenticated_sees_profile_and_stats(self):
        user = User.objects.create_user(username="09121118811", password="pass12345")
        Customer.objects.create(user=user, full_name="بهار نجفی", phone="09121118811", city="اصفهان")
        self.client.login(username="09121118811", password="pass12345")
        response = self.client.get(reverse("customers:account"))
        self.assertContains(response, "بهار نجفی")
        self.assertContains(response, "09121118811")


class ProfileUpdateViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="09121118822", password="pass12345")
        self.customer = Customer.objects.create(user=self.user, full_name="نام قدیمی", phone="09121118822")
        self.client.login(username="09121118822", password="pass12345")

    def test_valid_update_changes_customer_fields(self):
        response = self.client.post(reverse("customers:account-profile-update"), {
            "full_name": "نام جدید", "email": "new@example.com", "city": "شیراز",
        })
        self.assertEqual(response.status_code, 200)
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.full_name, "نام جدید")
        self.assertEqual(self.customer.city, "شیراز")

    def test_blank_full_name_is_rejected(self):
        response = self.client.post(reverse("customers:account-profile-update"), {
            "full_name": "", "email": "", "city": "",
        })
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.full_name, "نام قدیمی")
        self.assertContains(response, "این فیلد لازم است")


class AddressManagementTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="09121118833", password="pass12345")
        self.customer = Customer.objects.create(user=self.user, full_name="کاربر", phone="09121118833")
        self.client.login(username="09121118833", password="pass12345")
        self.payload = {
            "receiver_name": "کاربر", "phone": "09121118833", "province": "تهران",
            "city": "تهران", "postal_code": "1234567890", "full_address": "خیابان اصلی، پلاک ۱",
        }

    def test_first_address_added_becomes_default(self):
        response = self.client.post(reverse("customers:address-add"), self.payload)
        self.assertEqual(response.status_code, 200)
        address = Address.objects.get(customer=self.customer)
        self.assertTrue(address.is_default)

    def test_second_address_is_not_default(self):
        self.client.post(reverse("customers:address-add"), self.payload)
        self.client.post(reverse("customers:address-add"), dict(self.payload, receiver_name="دومی"))
        addresses = Address.objects.filter(customer=self.customer).order_by("id")
        self.assertTrue(addresses[0].is_default)
        self.assertFalse(addresses[1].is_default)

    def test_set_default_switches_flag(self):
        self.client.post(reverse("customers:address-add"), self.payload)
        self.client.post(reverse("customers:address-add"), dict(self.payload, receiver_name="دومی"))
        second = Address.objects.get(receiver_name="دومی")
        self.client.post(reverse("customers:address-set-default", args=[second.id]))
        second.refresh_from_db()
        first = Address.objects.exclude(pk=second.pk).get()
        self.assertTrue(second.is_default)
        self.assertFalse(first.is_default)

    def test_delete_default_promotes_another_address(self):
        self.client.post(reverse("customers:address-add"), self.payload)
        self.client.post(reverse("customers:address-add"), dict(self.payload, receiver_name="دومی"))
        first = Address.objects.get(receiver_name="کاربر")
        self.client.post(reverse("customers:address-delete", args=[first.id]))
        remaining = Address.objects.get()
        self.assertTrue(remaining.is_default)

    def test_invalid_phone_rejected(self):
        response = self.client.post(reverse("customers:address-add"), dict(self.payload, phone="123"))
        self.assertEqual(Address.objects.count(), 0)
        self.assertContains(response, "شماره موبایل معتبر نیست")

    def test_cannot_delete_another_customers_address(self):
        other_user = User.objects.create_user(username="09121118844", password="pass12345")
        other_customer = Customer.objects.create(user=other_user, full_name="دیگری", phone="09121118844")
        other_address = Address.objects.create(
            customer=other_customer, receiver_name="دیگری", phone="09121118844",
            province="تهران", city="تهران", full_address="جایی",
        )
        response = self.client.post(reverse("customers:address-delete", args=[other_address.id]))
        self.assertEqual(response.status_code, 404)
        self.assertTrue(Address.objects.filter(pk=other_address.pk).exists())


class AccountOrderDetailViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="09121118855", password="pass12345")
        self.customer = Customer.objects.create(user=self.user, full_name="کاربر", phone="09121118855")
        store = Store.objects.get(slug="akhlaghi")
        vendor = Vendor.objects.create(store=store, name="فروشگاه", slug="shop-aod")
        category = Category.objects.create(store=store, name="دیجیتال", slug="digital-aod")
        Product.objects.create(
            store=store, vendor=vendor, category=category, name="کالا", slug="sample-aod",
            sku="SKU-AOD1", price=Decimal("100000"),
        )
        shipping = ShippingMethod.objects.create(name="پست", slug="post-aod", cost=45_000)
        gateway = PaymentGateway.objects.create(name="زرین‌پال", slug="zarin-aod")
        self.order = Order.objects.create(
            code="DM-99001", customer=self.customer, vendor=vendor, address={"receiver_name": "کاربر", "city": "تهران"},
            shipping_method=shipping, payment_gateway=gateway,
            items_total=Decimal("100000"), grand_total=Decimal("145000"),
        )

    def test_anonymous_sees_login_prompt(self):
        response = self.client.get(reverse("customers:account-order-detail", args=[self.order.code]))
        self.assertContains(response, "ابتدا وارد حساب کاربری خود شوید")

    def test_owner_sees_order_detail(self):
        self.client.login(username="09121118855", password="pass12345")
        response = self.client.get(reverse("customers:account-order-detail", args=[self.order.code]))
        self.assertContains(response, self.order.code)

    def test_other_customer_gets_404(self):
        other_user = User.objects.create_user(username="09121118866", password="pass12345")
        Customer.objects.create(user=other_user, full_name="دیگری", phone="09121118866")
        self.client.login(username="09121118866", password="pass12345")
        response = self.client.get(reverse("customers:account-order-detail", args=[self.order.code]))
        self.assertEqual(response.status_code, 404)
