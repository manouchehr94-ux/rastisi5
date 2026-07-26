from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from apps.catalog.models import Category, Product, ProductVariant, Vendor
from apps.catalog.services.variant_service import (
    create_variant,
    deactivate_variant,
    set_product_type,
)
from apps.customers.models import Customer
from apps.orders.models import Order, OrderItem, PaymentGateway, ShippingMethod
from apps.stores.models import Store

User = get_user_model()


def _akhlaghi():
    return Store.objects.get(slug="akhlaghi")


class VariantViewsTestCase(TestCase):
    def setUp(self):
        self.store = _akhlaghi()
        self.vendor = Vendor.objects.create(store=self.store, name="فروشگاه", slug="shop-pvv")
        self.main = Category.objects.create(store=self.store, name="دیجیتال", slug="main-pvv")
        self.sub = Category.objects.create(store=self.store, name="موبایل", slug="sub-pvv", parent=self.main)
        self.product = Product.objects.create(
            store=self.store, vendor=self.vendor, category=self.sub, name="شیلنگ فن‌کویل", slug="hose-pvv",
            sku="SKU-HOSE-PVV", price=Decimal("200000"),
        )
        self.staff = User.objects.create_user(username="09121122301", password="pass12345", is_staff=True)
        self.client.login(username="09121122301", password="pass12345")

    def _make_variable(self):
        set_product_type(self.product, Product.ProductType.VARIABLE)
        return self.product

    def _other_product(self):
        return Product.objects.create(
            store=self.store, vendor=self.vendor, category=self.sub, name="کالای دیگر", slug="other-pvv",
            sku="SKU-OTHER-PVV", price=Decimal("50000"),
        )


# ------------------------------------------------------------ Routing/permissions


class RoutingPermissionTests(VariantViewsTestCase):
    def test_authorized_merchant_can_open_variation_page(self):
        self._make_variable()
        response = self.client.get(reverse("dashboard:product-variants", args=[self.product.pk]))
        self.assertEqual(response.status_code, 200)

    def test_anonymous_denied(self):
        self.client.logout()
        response = self.client.get(reverse("dashboard:product-variants", args=[self.product.pk]))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin-panel/login/", response.url)

    def test_non_staff_denied(self):
        self.client.logout()
        non_staff = User.objects.create_user(username="09121122302", password="pass12345", is_staff=False)
        self.client.login(username="09121122302", password="pass12345")
        response = self.client.get(reverse("dashboard:product-variants", args=[self.product.pk]))
        self.assertRedirects(response, reverse("catalog:home"))

    def test_unknown_product_id_returns_404(self):
        response = self.client.get(reverse("dashboard:product-variants", args=[999999]))
        self.assertEqual(response.status_code, 404)

    def test_variant_from_another_product_cannot_be_opened_through_this_product_url(self):
        self._make_variable()
        other = self._other_product()
        set_product_type(other, Product.ProductType.VARIABLE)
        foreign_variant = create_variant(other, attribute="رنگ", value="قرمز")

        response = self.client.get(
            reverse("dashboard:product-variant-edit", args=[self.product.pk, foreign_variant.pk])
        )
        self.assertEqual(response.status_code, 404)

    def test_variant_from_another_product_cannot_be_toggled_through_this_product_url(self):
        self._make_variable()
        other = self._other_product()
        set_product_type(other, Product.ProductType.VARIABLE)
        foreign_variant = create_variant(other, attribute="رنگ", value="قرمز")

        response = self.client.post(
            reverse("dashboard:product-variant-toggle", args=[self.product.pk, foreign_variant.pk])
        )
        self.assertEqual(response.status_code, 404)
        foreign_variant.refresh_from_db()
        self.assertTrue(foreign_variant.is_active)

    def test_variant_from_another_product_cannot_be_deleted_through_this_product_url(self):
        self._make_variable()
        other = self._other_product()
        set_product_type(other, Product.ProductType.VARIABLE)
        foreign_variant = create_variant(other, attribute="رنگ", value="قرمز")

        response = self.client.post(
            reverse("dashboard:product-variant-delete", args=[self.product.pk, foreign_variant.pk])
        )
        self.assertEqual(response.status_code, 404)
        self.assertTrue(ProductVariant.objects.filter(pk=foreign_variant.pk).exists())

    def test_variant_from_another_product_cannot_be_moved_through_this_product_url(self):
        self._make_variable()
        other = self._other_product()
        set_product_type(other, Product.ProductType.VARIABLE)
        foreign_variant = create_variant(other, attribute="رنگ", value="قرمز")

        response = self.client.post(
            reverse("dashboard:product-variant-move", args=[self.product.pk, foreign_variant.pk]),
            {"direction": "up"},
        )
        self.assertEqual(response.status_code, 404)


# ------------------------------------------------------------ Product type


class ProductTypeWorkflowTests(VariantViewsTestCase):
    def test_product_type_badge_shown_on_product_list(self):
        response = self.client.get(reverse("dashboard:product-list"))
        self.assertContains(response, "کالای ساده")

    def test_variable_type_badge_shown_on_product_list(self):
        self._make_variable()
        response = self.client.get(reverse("dashboard:product-list"))
        self.assertContains(response, "کالای دارای تنوع")

    def test_simple_product_variant_page_shows_guarded_state_not_management_ui(self):
        response = self.client.get(reverse("dashboard:product-variants", args=[self.product.pk]))
        self.assertContains(response, "این کالا «ساده» است")
        self.assertNotContains(response, "افزودن سریع تنوع")

    def test_simple_product_bulk_add_is_blocked(self):
        response = self.client.post(
            reverse("dashboard:product-variant-bulk-add", args=[self.product.pk]),
            {"attribute": "رنگ", "raw_values": "قرمز", "default_stock": "0", "default_extra_price": "0"},
        )
        self.assertEqual(self.product.variants.count(), 0)
        self.assertRedirects(response, reverse("dashboard:product-variants", args=[self.product.pk]))

    def test_simple_to_variable_transition_via_product_edit_uses_service(self):
        payload = {
            "name": self.product.name, "sku": self.product.sku, "category": self.sub.id,
            "price": "200000", "discount_percent": "0", "stock": "0", "status": "active",
            "icon": "", "description": "", "product_type": "variable",
        }
        self.client.post(reverse("dashboard:product-edit", args=[self.product.pk]), payload)
        self.product.refresh_from_db()
        self.assertEqual(self.product.product_type, Product.ProductType.VARIABLE)

    def test_blocked_variable_to_simple_transition_shows_clear_error(self):
        self._make_variable()
        create_variant(self.product, attribute="رنگ", value="قرمز")
        payload = {
            "name": self.product.name, "sku": self.product.sku, "category": self.sub.id,
            "price": "200000", "discount_percent": "0", "stock": "0", "status": "active",
            "icon": "", "description": "", "product_type": "simple",
        }
        response = self.client.post(reverse("dashboard:product-edit", args=[self.product.pk]), payload)
        self.product.refresh_from_db()
        self.assertEqual(self.product.product_type, Product.ProductType.VARIABLE)
        self.assertContains(response, "تنوع")

    def test_blocked_transition_does_not_lose_other_field_edits(self):
        """اگر گذار نوع کالا مسدود شود، ویرایش‌های دیگر فرم هم اعمال نمی‌شود (اتمیک)."""
        self._make_variable()
        create_variant(self.product, attribute="رنگ", value="قرمز")
        payload = {
            "name": "نام تغییریافته", "sku": self.product.sku, "category": self.sub.id,
            "price": "999000", "discount_percent": "0", "stock": "0", "status": "active",
            "icon": "", "description": "", "product_type": "simple",
        }
        self.client.post(reverse("dashboard:product-edit", args=[self.product.pk]), payload)
        self.product.refresh_from_db()
        self.assertEqual(self.product.name, "شیلنگ فن‌کویل")
        self.assertEqual(self.product.price, Decimal("200000"))

    def test_omitting_product_type_field_does_not_change_existing_type(self):
        """درخواست‌های قدیمی/تستی که product_type ارسال نمی‌کنند نباید نوع کالا را تغییر دهند."""
        self._make_variable()
        payload = {
            "name": self.product.name, "sku": self.product.sku, "category": self.sub.id,
            "price": "200000", "discount_percent": "0", "stock": "0", "status": "active",
            "icon": "", "description": "",
        }
        self.client.post(reverse("dashboard:product-edit", args=[self.product.pk]), payload)
        self.product.refresh_from_db()
        self.assertEqual(self.product.product_type, Product.ProductType.VARIABLE)

    def test_new_product_defaults_to_simple_when_type_not_selected(self):
        payload = {
            "name": "کالای دیگر", "sku": "SKU-NEWTYPE-PVV", "category": self.sub.id,
            "price": "100000", "discount_percent": "0", "stock": "0", "status": "active",
            "icon": "", "description": "",
        }
        self.client.post(reverse("dashboard:product-add"), payload)
        product = Product.objects.get(sku="SKU-NEWTYPE-PVV")
        self.assertEqual(product.product_type, Product.ProductType.SIMPLE)


# ------------------------------------------------------------ Product list annotations/queries


class ProductListVariantAnnotationTests(VariantViewsTestCase):
    def test_variant_counts_shown_for_variable_product(self):
        self._make_variable()
        create_variant(self.product, attribute="رنگ", value="قرمز", stock=5)
        v2 = create_variant(self.product, attribute="رنگ", value="آبی", stock=3)
        deactivate_variant(v2)
        response = self.client.get(reverse("dashboard:product-list"))
        self.assertContains(response, "۱ از ۲ تنوع فعال")

    def test_query_count_does_not_grow_with_variant_count(self):
        """تعداد کوئری صفحه‌ی فهرست کالاها نباید با تعداد تنوع‌های یک کالا رشد کند (بدون N+1)."""
        self._make_variable()
        create_variant(self.product, attribute="رنگ", value="اول", stock=1)
        self.client.get(reverse("dashboard:product-list"))  # warm-up: establish session/CSRF once

        with CaptureQueriesContext(connection) as ctx_small:
            response = self.client.get(reverse("dashboard:product-list"))
        self.assertEqual(response.status_code, 200)
        query_count_small = len(ctx_small)

        for i in range(30):
            create_variant(self.product, attribute="رنگ", value=f"رنگ{i}", stock=1)

        with CaptureQueriesContext(connection) as ctx_large:
            response = self.client.get(reverse("dashboard:product-list"))
        self.assertEqual(response.status_code, 200)
        query_count_large = len(ctx_large)

        self.assertEqual(
            query_count_small, query_count_large,
            f"Query count grew from {query_count_small} to {query_count_large} as variant count increased",
        )


# ------------------------------------------------------------ Bulk creation


class BulkCreateViewTests(VariantViewsTestCase):
    def setUp(self):
        super().setUp()
        self._make_variable()
        self.url = reverse("dashboard:product-variant-bulk-add", args=[self.product.pk])

    def test_multiple_values_create_multiple_variants(self):
        self.client.post(self.url, {
            "attribute": "طول", "raw_values": "30\n40\n50", "default_stock": "0", "default_extra_price": "0",
        })
        self.assertEqual(self.product.variants.count(), 3)

    def test_persian_values_work(self):
        self.client.post(self.url, {
            "attribute": "رنگ", "raw_values": "قرمز، آبی، مشکی", "default_stock": "0", "default_extra_price": "0",
        })
        self.assertEqual(self.product.variants.count(), 3)
        self.assertTrue(self.product.variants.filter(value="قرمز").exists())

    def test_duplicate_normalized_value_against_existing_active_is_rejected_safely(self):
        create_variant(self.product, attribute="رنگ", value="قرمز")
        response = self.client.post(self.url, {
            "attribute": "رنگ", "raw_values": "قرمز", "default_stock": "0", "default_extra_price": "0",
            "is_active": "on",
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.product.variants.count(), 1)

    def test_duplicate_values_in_same_batch_created_once(self):
        self.client.post(self.url, {
            "attribute": "رنگ", "raw_values": "قرمز\nقرمز\nآبی", "default_stock": "0", "default_extra_price": "0",
        })
        self.assertEqual(self.product.variants.count(), 2)

    def test_blank_lines_ignored(self):
        self.client.post(self.url, {
            "attribute": "رنگ", "raw_values": "قرمز\n\n\nآبی\n", "default_stock": "0", "default_extra_price": "0",
        })
        self.assertEqual(self.product.variants.count(), 2)

    def test_default_stock_applied(self):
        self.client.post(self.url, {
            "attribute": "رنگ", "raw_values": "قرمز", "default_stock": "12", "default_extra_price": "0",
        })
        variant = self.product.variants.get(value="قرمز")
        self.assertEqual(variant.stock, 12)

    def test_default_extra_price_applied(self):
        self.client.post(self.url, {
            "attribute": "رنگ", "raw_values": "قرمز", "default_stock": "0", "default_extra_price": "15000",
        })
        variant = self.product.variants.get(value="قرمز")
        self.assertEqual(variant.extra_price, Decimal("15000"))

    def test_inactive_initial_state_applied(self):
        response = self.client.post(self.url, {
            "attribute": "رنگ", "raw_values": "قرمز", "default_stock": "0", "default_extra_price": "0",
        })
        # is_active checkbox omitted => False
        variant = self.product.variants.get(value="قرمز")
        self.assertFalse(variant.is_active)

    def test_active_initial_state_applied_when_checked(self):
        self.client.post(self.url, {
            "attribute": "رنگ", "raw_values": "قرمز", "default_stock": "0", "default_extra_price": "0",
            "is_active": "on",
        })
        variant = self.product.variants.get(value="قرمز")
        self.assertTrue(variant.is_active)

    def test_product_scope_enforced_variants_belong_to_correct_product(self):
        self.client.post(self.url, {
            "attribute": "رنگ", "raw_values": "قرمز", "default_stock": "0", "default_extra_price": "0",
        })
        variant = ProductVariant.objects.get(value="قرمز")
        self.assertEqual(variant.product_id, self.product.pk)

    def test_empty_values_create_nothing(self):
        response = self.client.post(self.url, {
            "attribute": "رنگ", "raw_values": "   ", "default_stock": "0", "default_extra_price": "0",
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.product.variants.count(), 0)

    def test_empty_attribute_rejected_with_field_error(self):
        response = self.client.post(self.url, {
            "attribute": "", "raw_values": "قرمز", "default_stock": "0", "default_extra_price": "0",
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.product.variants.count(), 0)

    def test_submitted_values_preserved_on_failure(self):
        create_variant(self.product, attribute="رنگ", value="قرمز")
        response = self.client.post(self.url, {
            "attribute": "رنگ", "raw_values": "قرمز", "default_stock": "7", "default_extra_price": "0",
            "is_active": "on",
        })
        self.assertContains(response, 'value="7"')

    def test_get_not_allowed(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 405)

    def test_anonymous_denied(self):
        self.client.logout()
        response = self.client.post(self.url, {
            "attribute": "رنگ", "raw_values": "قرمز", "default_stock": "0", "default_extra_price": "0",
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.product.variants.count(), 0)


# ------------------------------------------------------------ Editing


class VariantEditViewTests(VariantViewsTestCase):
    def setUp(self):
        super().setUp()
        self._make_variable()
        self.variant = create_variant(self.product, attribute="طول", value="30", stock=10)
        self.url = reverse("dashboard:product-variant-edit", args=[self.product.pk, self.variant.pk])

    def _payload(self, **overrides):
        payload = {
            "attribute": "طول", "value": "30", "sku": "", "extra_price": "0", "stock": "10", "is_active": "on",
        }
        payload.update(overrides)
        return payload

    def test_get_prefills_form(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'value="30"')

    def test_variant_can_be_edited(self):
        self.client.post(self.url, self._payload(value="35"))
        self.variant.refresh_from_db()
        self.assertEqual(self.variant.value, "35")

    def test_sku_can_be_added(self):
        self.client.post(self.url, self._payload(sku="HOSE-30"))
        self.variant.refresh_from_db()
        self.assertEqual(self.variant.sku, "HOSE-30")

    def test_duplicate_sku_rejected(self):
        original_sku = self.variant.sku
        create_variant(self.product, attribute="طول", value="40", sku="HOSE-40")
        response = self.client.post(self.url, self._payload(sku="HOSE-40"))
        self.assertEqual(response.status_code, 200)
        self.variant.refresh_from_db()
        self.assertEqual(self.variant.sku, original_sku)

    def test_duplicate_normalized_active_variant_rejected(self):
        create_variant(self.product, attribute="طول", value="40")
        response = self.client.post(self.url, self._payload(value="40"))
        self.assertEqual(response.status_code, 200)
        self.variant.refresh_from_db()
        self.assertEqual(self.variant.value, "30")

    def test_stock_update_works(self):
        self.client.post(self.url, self._payload(stock="25"))
        self.variant.refresh_from_db()
        self.assertEqual(self.variant.stock, 25)

    def test_extra_price_update_works(self):
        self.client.post(self.url, self._payload(extra_price="30000"))
        self.variant.refresh_from_db()
        self.assertEqual(self.variant.extra_price, Decimal("30000"))

    def test_inactive_state_update_works(self):
        self.client.post(self.url, self._payload(is_active=""))
        self.variant.refresh_from_db()
        self.assertFalse(self.variant.is_active)

    def test_empty_value_validation_error_no_500(self):
        response = self.client.post(self.url, self._payload(value=""))
        self.assertEqual(response.status_code, 200)

    def test_negative_stock_validation_error_no_500(self):
        response = self.client.post(self.url, self._payload(stock="-5"))
        self.assertEqual(response.status_code, 200)
        self.variant.refresh_from_db()
        self.assertEqual(self.variant.stock, 10)

    def test_success_redirects_to_variant_page(self):
        response = self.client.post(self.url, self._payload(value="35"))
        self.assertRedirects(response, reverse("dashboard:product-variants", args=[self.product.pk]))

    def test_anonymous_denied(self):
        self.client.logout()
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)


# ------------------------------------------------------------ Activation/deactivation


class VariantToggleViewTests(VariantViewsTestCase):
    def setUp(self):
        super().setUp()
        self._make_variable()
        self.variant = create_variant(self.product, attribute="رنگ", value="قرمز")
        self.url = reverse("dashboard:product-variant-toggle", args=[self.product.pk, self.variant.pk])

    def test_active_variant_can_be_deactivated(self):
        self.client.post(self.url)
        self.variant.refresh_from_db()
        self.assertFalse(self.variant.is_active)

    def test_inactive_variant_can_be_activated(self):
        deactivate_variant(self.variant)
        self.client.post(self.url)
        self.variant.refresh_from_db()
        self.assertTrue(self.variant.is_active)

    def test_conflicting_activation_rejected_safely(self):
        deactivate_variant(self.variant)
        create_variant(self.product, attribute="رنگ", value="قرمز")  # new active duplicate
        response = self.client.post(self.url)
        self.assertEqual(response.status_code, 302)
        self.variant.refresh_from_db()
        self.assertFalse(self.variant.is_active)

    def test_get_cannot_mutate_state(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 405)
        self.variant.refresh_from_db()
        self.assertTrue(self.variant.is_active)

    def test_csrf_protected_post_required(self):
        csrf_client = self.client_class(enforce_csrf_checks=True)
        csrf_client.login(username="09121122301", password="pass12345")
        response = csrf_client.post(self.url)
        self.assertEqual(response.status_code, 403)
        self.variant.refresh_from_db()
        self.assertTrue(self.variant.is_active)

    def test_anonymous_denied(self):
        self.client.logout()
        response = self.client.post(self.url)
        self.assertEqual(response.status_code, 302)
        self.variant.refresh_from_db()
        self.assertTrue(self.variant.is_active)


# ------------------------------------------------------------ Deletion


class VariantDeleteViewTests(VariantViewsTestCase):
    def setUp(self):
        super().setUp()
        self._make_variable()
        self.variant = create_variant(self.product, attribute="رنگ", value="قرمز")
        self.delete_url = reverse("dashboard:product-variant-delete", args=[self.product.pk, self.variant.pk])

    def _make_sold_variant(self):
        customer_user = User.objects.create_user(username="09129990001", password="pass12345")
        customer = Customer.objects.create(user=customer_user, full_name="مشتری", phone="09129990001")
        shipping = ShippingMethod.objects.create(store=self.store, name="پست", slug="post-pvv", cost=Decimal("10000"))
        gateway = PaymentGateway.objects.create(store=self.store, name="درگاه", slug="gw-pvv")
        order = Order.objects.create(
            code="DM-PVV1", store=self.store, customer=customer, vendor=self.vendor,
            shipping_method=shipping, payment_gateway=gateway,
        )
        sold_variant = create_variant(self.product, attribute="رنگ", value="آبی")
        OrderItem.objects.create(
            order=order, product=self.product, variant=sold_variant, product_name=self.product.name,
            quantity=1, unit_price=Decimal("200000"), line_total=Decimal("200000"),
        )
        return sold_variant, order

    def test_unsold_safe_variant_can_be_deleted(self):
        response = self.client.post(self.delete_url)
        self.assertRedirects(response, reverse("dashboard:product-variants", args=[self.product.pk]))
        self.assertFalse(ProductVariant.objects.filter(pk=self.variant.pk).exists())

    def test_sold_variant_cannot_be_deleted(self):
        sold_variant, _ = self._make_sold_variant()
        url = reverse("dashboard:product-variant-delete", args=[self.product.pk, sold_variant.pk])
        response = self.client.post(url)
        self.assertRedirects(response, reverse("dashboard:product-variants", args=[self.product.pk]))
        self.assertTrue(ProductVariant.objects.filter(pk=sold_variant.pk).exists())

    def test_blocked_deletion_preserves_order_item_relationship(self):
        sold_variant, order = self._make_sold_variant()
        url = reverse("dashboard:product-variant-delete", args=[self.product.pk, sold_variant.pk])
        self.client.post(url)
        order_item = OrderItem.objects.get(order=order)
        self.assertEqual(order_item.variant_id, sold_variant.pk)

    def test_get_confirm_page_does_not_delete(self):
        response = self.client.get(self.delete_url)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(ProductVariant.objects.filter(pk=self.variant.pk).exists())

    def test_get_confirm_page_for_sold_variant_shows_blocked_message_not_destructive_form(self):
        sold_variant, _ = self._make_sold_variant()
        url = reverse("dashboard:product-variant-delete", args=[self.product.pk, sold_variant.pk])
        response = self.client.get(url)
        self.assertRedirects(response, reverse("dashboard:product-variants", args=[self.product.pk]))

    def test_anonymous_denied(self):
        self.client.logout()
        response = self.client.post(self.delete_url)
        self.assertEqual(response.status_code, 302)
        self.assertTrue(ProductVariant.objects.filter(pk=self.variant.pk).exists())


# ------------------------------------------------------------ Reordering


class VariantReorderViewTests(VariantViewsTestCase):
    def setUp(self):
        super().setUp()
        self._make_variable()
        self.v1 = create_variant(self.product, attribute="طول", value="30")
        self.v2 = create_variant(self.product, attribute="طول", value="40")
        self.v3 = create_variant(self.product, attribute="طول", value="50")

    def test_move_up_succeeds_and_persists(self):
        url = reverse("dashboard:product-variant-move", args=[self.product.pk, self.v2.pk])
        self.client.post(url, {"direction": "up"})
        self.v1.refresh_from_db()
        self.v2.refresh_from_db()
        self.assertEqual(self.v2.display_order, 0)
        self.assertEqual(self.v1.display_order, 1)

    def test_move_down_succeeds_and_persists(self):
        url = reverse("dashboard:product-variant-move", args=[self.product.pk, self.v1.pk])
        self.client.post(url, {"direction": "down"})
        self.v1.refresh_from_db()
        self.v2.refresh_from_db()
        self.assertEqual(self.v1.display_order, 1)
        self.assertEqual(self.v2.display_order, 0)

    def test_move_first_item_up_is_noop(self):
        url = reverse("dashboard:product-variant-move", args=[self.product.pk, self.v1.pk])
        self.client.post(url, {"direction": "up"})
        self.v1.refresh_from_db()
        self.assertEqual(self.v1.display_order, 0)

    def test_invalid_direction_is_noop(self):
        url = reverse("dashboard:product-variant-move", args=[self.product.pk, self.v1.pk])
        self.client.post(url, {"direction": "sideways"})
        self.v1.refresh_from_db()
        self.assertEqual(self.v1.display_order, 0)

    def test_get_not_allowed(self):
        url = reverse("dashboard:product-variant-move", args=[self.product.pk, self.v1.pk])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 405)


# ------------------------------------------------------------ UI rendering


class VariantPageUITests(VariantViewsTestCase):
    def test_empty_state_renders(self):
        self._make_variable()
        response = self.client.get(reverse("dashboard:product-variants", args=[self.product.pk]))
        self.assertContains(response, "این کالا هنوز هیچ مقدار تنوعی ندارد")

    def test_existing_variants_render(self):
        self._make_variable()
        create_variant(self.product, attribute="رنگ", value="قرمز", stock=5)
        response = self.client.get(reverse("dashboard:product-variants", args=[self.product.pk]))
        self.assertContains(response, "رنگ")
        self.assertContains(response, "قرمز")

    def test_product_title_and_type_render(self):
        self._make_variable()
        response = self.client.get(reverse("dashboard:product-variants", args=[self.product.pk]))
        self.assertContains(response, self.product.name)
        self.assertContains(response, "کالای دارای تنوع")

    def test_active_badge_renders(self):
        self._make_variable()
        create_variant(self.product, attribute="رنگ", value="قرمز")
        response = self.client.get(reverse("dashboard:product-variants", args=[self.product.pk]))
        self.assertContains(response, "فعال")

    def test_inactive_badge_renders(self):
        self._make_variable()
        variant = create_variant(self.product, attribute="رنگ", value="قرمز")
        deactivate_variant(variant)
        response = self.client.get(reverse("dashboard:product-variants", args=[self.product.pk]))
        self.assertContains(response, "غیرفعال")

    def test_edit_link_renders(self):
        self._make_variable()
        variant = create_variant(self.product, attribute="رنگ", value="قرمز")
        response = self.client.get(reverse("dashboard:product-variants", args=[self.product.pk]))
        self.assertContains(response, reverse("dashboard:product-variant-edit", args=[self.product.pk, variant.pk]))

    def test_delete_action_hidden_for_sold_variant(self):
        self._make_variable()
        customer_user = User.objects.create_user(username="09129990002", password="pass12345")
        customer = Customer.objects.create(user=customer_user, full_name="مشتری", phone="09129990002")
        shipping = ShippingMethod.objects.create(store=self.store, name="پست", slug="post-pvv2", cost=Decimal("10000"))
        gateway = PaymentGateway.objects.create(store=self.store, name="درگاه", slug="gw-pvv2")
        order = Order.objects.create(
            code="DM-PVV2", store=self.store, customer=customer, vendor=self.vendor,
            shipping_method=shipping, payment_gateway=gateway,
        )
        sold_variant = create_variant(self.product, attribute="رنگ", value="آبی")
        OrderItem.objects.create(
            order=order, product=self.product, variant=sold_variant, product_name=self.product.name,
            quantity=1, unit_price=Decimal("200000"), line_total=Decimal("200000"),
        )
        response = self.client.get(reverse("dashboard:product-variants", args=[self.product.pk]))
        self.assertNotContains(
            response, reverse("dashboard:product-variant-delete", args=[self.product.pk, sold_variant.pk])
        )

    def test_warning_shown_when_variable_with_zero_active_variants(self):
        self._make_variable()
        variant = create_variant(self.product, attribute="رنگ", value="قرمز")
        deactivate_variant(variant)
        response = self.client.get(reverse("dashboard:product-variants", args=[self.product.pk]))
        self.assertContains(response, "هیچ مقدار فعالی وجود ندارد")

    def test_no_warning_when_at_least_one_active_variant(self):
        self._make_variable()
        create_variant(self.product, attribute="رنگ", value="قرمز")
        response = self.client.get(reverse("dashboard:product-variants", args=[self.product.pk]))
        self.assertNotContains(response, "هیچ مقدار فعالی ندارد")


# ------------------------------------------------------------ Query performance on the variant page


class VariantPageQueryPerformanceTests(VariantViewsTestCase):
    def test_query_count_bounded_regardless_of_variant_count(self):
        """کوئری‌های صفحه‌ی مدیریت تنوع نباید به ازای هر ردیف تنوع رشد کند (بدون N+1)."""
        self._make_variable()
        create_variant(self.product, attribute="رنگ", value="اول", stock=1)
        self.client.get(reverse("dashboard:product-variants", args=[self.product.pk]))  # warm-up

        with CaptureQueriesContext(connection) as ctx_small:
            response = self.client.get(reverse("dashboard:product-variants", args=[self.product.pk]))
        self.assertEqual(response.status_code, 200)
        query_count_small = len(ctx_small)

        for i in range(30):
            create_variant(self.product, attribute="رنگ", value=f"رنگ{i}", stock=1)

        with CaptureQueriesContext(connection) as ctx_large:
            response = self.client.get(reverse("dashboard:product-variants", args=[self.product.pk]))
        self.assertEqual(response.status_code, 200)
        query_count_large = len(ctx_large)

        self.assertEqual(
            query_count_small, query_count_large,
            f"Query count grew from {query_count_small} to {query_count_large} as variant count increased",
        )


# ------------------------------------------------------------ Search and filters


class VariantSearchFilterTests(VariantViewsTestCase):
    def setUp(self):
        super().setUp()
        self._make_variable()
        self.red = create_variant(self.product, attribute="رنگ", value="قرمز", sku="SKU-RED-1")
        self.blue = create_variant(self.product, attribute="رنگ", value="آبی", sku="SKU-BLUE-1")
        self.size_m = create_variant(self.product, attribute="سایز", value="M", sku="SKU-SIZE-M")
        deactivate_variant(self.size_m)

    def _get(self, **params):
        return self.client.get(reverse("dashboard:product-variants", args=[self.product.pk]), params)

    def test_search_by_attribute_name(self):
        response = self._get(q="سایز")
        self.assertContains(response, "SKU-SIZE-M")
        self.assertNotContains(response, "SKU-RED-1")

    def test_search_by_value(self):
        response = self._get(q="قرمز")
        self.assertContains(response, "SKU-RED-1")
        self.assertNotContains(response, "SKU-BLUE-1")

    def test_search_by_sku(self):
        response = self._get(q="SKU-BLUE-1")
        self.assertContains(response, "SKU-BLUE-1")
        self.assertNotContains(response, "SKU-RED-1")

    def test_search_case_insensitive_and_partial(self):
        response = self._get(q="blue")
        self.assertContains(response, "SKU-BLUE-1")

    def test_search_scoped_to_product(self):
        other = self._other_product()
        set_product_type(other, Product.ProductType.VARIABLE)
        create_variant(other, attribute="رنگ", value="قرمز", sku="SKU-OTHER-RED")
        response = self._get(q="قرمز")
        self.assertContains(response, "SKU-RED-1")
        self.assertNotContains(response, "SKU-OTHER-RED")

    def test_status_filter_active_only(self):
        response = self._get(status="active")
        self.assertContains(response, "SKU-RED-1")
        self.assertContains(response, "SKU-BLUE-1")
        self.assertNotContains(response, "SKU-SIZE-M")

    def test_status_filter_inactive_only(self):
        response = self._get(status="inactive")
        self.assertContains(response, "SKU-SIZE-M")
        self.assertNotContains(response, "SKU-RED-1")

    def test_invalid_status_filter_falls_back_to_all(self):
        response = self._get(status="bogus")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "SKU-RED-1")
        self.assertContains(response, "SKU-SIZE-M")

    def test_search_and_status_filter_combined(self):
        response = self._get(q="رنگ", status="active")
        self.assertContains(response, "SKU-RED-1")
        self.assertContains(response, "SKU-BLUE-1")
        self.assertNotContains(response, "SKU-SIZE-M")

    def test_clear_filters_link_present_when_filtered(self):
        response = self._get(q="قرمز")
        self.assertContains(response, "پاک‌کردن جست‌وجو و فیلتر")

    def test_clear_filters_link_absent_when_unfiltered(self):
        response = self._get()
        self.assertNotContains(response, "پاک‌کردن جست‌وجو و فیلتر")

    def test_active_filter_chip_marked_active_in_html(self):
        response = self._get(status="active")
        self.assertContains(response, "filter-chip active")


# ------------------------------------------------------------ Search-empty state


class VariantSearchEmptyStateTests(VariantViewsTestCase):
    def test_search_no_results_shows_distinct_message(self):
        self._make_variable()
        create_variant(self.product, attribute="رنگ", value="قرمز")
        response = self.client.get(
            reverse("dashboard:product-variants", args=[self.product.pk]), {"q": "nonexistent-xyz"}
        )
        self.assertContains(response, "نتیجه‌ای یافت نشد")

    def test_search_no_results_does_not_show_genuine_empty_message(self):
        self._make_variable()
        create_variant(self.product, attribute="رنگ", value="قرمز")
        response = self.client.get(
            reverse("dashboard:product-variants", args=[self.product.pk]), {"q": "nonexistent-xyz"}
        )
        self.assertNotContains(response, "این کالا هنوز هیچ مقدار تنوعی ندارد")

    def test_genuine_empty_state_does_not_show_search_empty_message(self):
        self._make_variable()
        response = self.client.get(reverse("dashboard:product-variants", args=[self.product.pk]))
        self.assertNotContains(response, "نتیجه‌ای یافت نشد")

    def test_search_empty_state_includes_clear_link(self):
        self._make_variable()
        create_variant(self.product, attribute="رنگ", value="قرمز")
        response = self.client.get(
            reverse("dashboard:product-variants", args=[self.product.pk]), {"q": "nonexistent-xyz"}
        )
        self.assertContains(response, "پاک‌کردن جست‌وجو و فیلترها")

    def test_status_filter_with_no_matches_shows_search_empty_state(self):
        self._make_variable()
        create_variant(self.product, attribute="رنگ", value="قرمز")
        response = self.client.get(
            reverse("dashboard:product-variants", args=[self.product.pk]), {"status": "inactive"}
        )
        self.assertContains(response, "نتیجه‌ای یافت نشد")


# ------------------------------------------------------------ Summary counts stay whole-product


class VariantSummaryCountIndependenceTests(VariantViewsTestCase):
    def setUp(self):
        super().setUp()
        self._make_variable()
        create_variant(self.product, attribute="رنگ", value="قرمز")
        create_variant(self.product, attribute="رنگ", value="آبی")
        inactive = create_variant(self.product, attribute="رنگ", value="سبز")
        deactivate_variant(inactive)

    def test_summary_counts_unaffected_by_search_filter(self):
        response = self.client.get(
            reverse("dashboard:product-variants", args=[self.product.pk]), {"q": "قرمز"}
        )
        self.assertEqual(response.context["variant_count"], 3)
        self.assertEqual(response.context["active_variant_count"], 2)
        self.assertEqual(response.context["inactive_variant_count"], 1)

    def test_summary_counts_unaffected_by_status_filter(self):
        response = self.client.get(
            reverse("dashboard:product-variants", args=[self.product.pk]), {"status": "inactive"}
        )
        self.assertEqual(response.context["variant_count"], 3)
        self.assertEqual(response.context["active_variant_count"], 2)


# ------------------------------------------------------------ Pagination


class VariantPaginationTests(VariantViewsTestCase):
    def setUp(self):
        super().setUp()
        self._make_variable()
        for i in range(30):
            create_variant(self.product, attribute="رنگ", value=f"رنگ{i:02d}", sku=f"SKU-P-{i:02d}")

    def test_first_page_shows_default_page_size(self):
        response = self.client.get(reverse("dashboard:product-variants", args=[self.product.pk]))
        self.assertEqual(len(response.context["variants"]), 25)

    def test_second_page_shows_remainder(self):
        response = self.client.get(
            reverse("dashboard:product-variants", args=[self.product.pk]), {"page": 2}
        )
        self.assertEqual(len(response.context["variants"]), 5)

    def test_invalid_page_number_falls_back_to_last_page(self):
        response = self.client.get(
            reverse("dashboard:product-variants", args=[self.product.pk]), {"page": 9999}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["page_obj"].number, 2)

    def test_non_integer_page_falls_back_to_first_page(self):
        response = self.client.get(
            reverse("dashboard:product-variants", args=[self.product.pk]), {"page": "abc"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["page_obj"].number, 1)

    def test_no_duplicate_or_missing_rows_across_pages(self):
        page1 = self.client.get(reverse("dashboard:product-variants", args=[self.product.pk]))
        page2 = self.client.get(
            reverse("dashboard:product-variants", args=[self.product.pk]), {"page": 2}
        )
        ids_1 = {v.pk for v in page1.context["variants"]}
        ids_2 = {v.pk for v in page2.context["variants"]}
        self.assertEqual(len(ids_1), 25)
        self.assertEqual(len(ids_2), 5)
        self.assertEqual(ids_1 & ids_2, set())
        self.assertEqual(ids_1 | ids_2, set(self.product.variants.values_list("pk", flat=True)))

    def test_pagination_preserves_search_querystring(self):
        response = self.client.get(
            reverse("dashboard:product-variants", args=[self.product.pk]), {"q": "رنگ", "page": 1}
        )
        self.assertIn("q=", response.context["querystring"])
        self.assertNotIn("page=", response.context["querystring"])

    def test_pagination_not_shown_when_single_page(self):
        response = self.client.get(
            reverse("dashboard:product-variants", args=[self.product.pk]), {"status": "inactive"}
        )
        self.assertNotContains(response, 'class="pagination"')

    def test_pagination_shown_when_multiple_pages(self):
        response = self.client.get(reverse("dashboard:product-variants", args=[self.product.pk]))
        self.assertContains(response, 'class="pagination"')


# ------------------------------------------------------------ Ordering-lock while filtered


class VariantOrderingLockUITests(VariantViewsTestCase):
    def setUp(self):
        super().setUp()
        self._make_variable()
        self.v1 = create_variant(self.product, attribute="رنگ", value="قرمز")
        self.v2 = create_variant(self.product, attribute="رنگ", value="آبی")

    def test_move_controls_visible_when_unfiltered(self):
        response = self.client.get(reverse("dashboard:product-variants", args=[self.product.pk]))
        self.assertContains(response, "جابه‌جایی به بالا")
        self.assertFalse(response.context["ordering_locked"])

    def test_move_controls_hidden_when_search_active(self):
        response = self.client.get(
            reverse("dashboard:product-variants", args=[self.product.pk]), {"q": "قرمز"}
        )
        self.assertNotContains(response, "جابه‌جایی به بالا")
        self.assertTrue(response.context["ordering_locked"])

    def test_move_controls_hidden_when_status_filter_active(self):
        response = self.client.get(
            reverse("dashboard:product-variants", args=[self.product.pk]), {"status": "active"}
        )
        self.assertNotContains(response, "جابه‌جایی به بالا")
        self.assertTrue(response.context["ordering_locked"])

    def test_move_endpoint_still_operates_on_full_product_order_regardless_of_filter_querystring(self):
        url = reverse("dashboard:product-variant-move", args=[self.product.pk, self.v2.pk])
        self.client.post(f"{url}?q=آبی", {"direction": "up"})
        self.v1.refresh_from_db()
        self.v2.refresh_from_db()
        self.assertLess(self.v2.display_order, self.v1.display_order)


# ------------------------------------------------------------ Querystring preservation across mutations


class VariantActionQuerystringPreservationTests(VariantViewsTestCase):
    def setUp(self):
        super().setUp()
        self._make_variable()
        self.variant = create_variant(self.product, attribute="رنگ", value="قرمز")

    def test_toggle_redirect_preserves_search_query(self):
        url = reverse("dashboard:product-variant-toggle", args=[self.product.pk, self.variant.pk])
        response = self.client.post(f"{url}?q=قرمز", {})
        self.assertEqual(response.status_code, 302)
        self.assertIn("q=", response.url)

    def test_toggle_redirect_preserves_status_filter(self):
        url = reverse("dashboard:product-variant-toggle", args=[self.product.pk, self.variant.pk])
        response = self.client.post(f"{url}?status=active", {})
        self.assertIn("status=active", response.url)

    def test_delete_redirect_preserves_query_when_blocked(self):
        customer_user = User.objects.create_user(username="09129990003", password="pass12345")
        customer = Customer.objects.create(user=customer_user, full_name="مشتری", phone="09129990003")
        shipping = ShippingMethod.objects.create(store=self.store, name="پست", slug="post-pvv3", cost=Decimal("10000"))
        gateway = PaymentGateway.objects.create(store=self.store, name="درگاه", slug="gw-pvv3")
        order = Order.objects.create(
            code="DM-PVV3", store=self.store, customer=customer, vendor=self.vendor,
            shipping_method=shipping, payment_gateway=gateway,
        )
        OrderItem.objects.create(
            order=order, product=self.product, variant=self.variant, product_name=self.product.name,
            quantity=1, unit_price=Decimal("200000"), line_total=Decimal("200000"),
        )
        url = reverse("dashboard:product-variant-delete", args=[self.product.pk, self.variant.pk])
        response = self.client.get(f"{url}?status=active")
        self.assertEqual(response.status_code, 302)
        self.assertIn("status=active", response.url)

    def test_move_redirect_preserves_query(self):
        create_variant(self.product, attribute="رنگ", value="آبی")
        url = reverse("dashboard:product-variant-move", args=[self.product.pk, self.variant.pk])
        response = self.client.post(f"{url}?status=active", {"direction": "down"})
        self.assertIn("status=active", response.url)

    def test_edit_get_back_url_includes_query(self):
        url = reverse("dashboard:product-variant-edit", args=[self.product.pk, self.variant.pk])
        response = self.client.get(f"{url}?q=قرمز")
        self.assertIn("q=", response.context["back_url"])

    def test_edit_success_redirect_preserves_query_via_back_query_field(self):
        url = reverse("dashboard:product-variant-edit", args=[self.product.pk, self.variant.pk])
        response = self.client.post(url, {
            "attribute": "رنگ", "value": "قرمز", "sku": "", "stock": "5",
            "extra_price": "0", "is_active": "on", "back_query": "status=active",
        })
        self.assertEqual(response.status_code, 302)
        self.assertIn("status=active", response.url)

    def test_edit_success_redirect_without_back_query_goes_to_plain_list(self):
        url = reverse("dashboard:product-variant-edit", args=[self.product.pk, self.variant.pk])
        response = self.client.post(url, {
            "attribute": "رنگ", "value": "قرمز", "sku": "", "stock": "5",
            "extra_price": "0", "is_active": "on",
        })
        self.assertRedirects(response, reverse("dashboard:product-variants", args=[self.product.pk]))


# ------------------------------------------------------------ Query performance under filter/pagination


class VariantPageFilteredQueryPerformanceTests(VariantViewsTestCase):
    def test_query_count_bounded_with_search_active(self):
        self._make_variable()
        for i in range(20):
            create_variant(self.product, attribute="رنگ", value=f"رنگ{i}", stock=1)
        self.client.get(reverse("dashboard:product-variants", args=[self.product.pk]), {"q": "رنگ1"})

        with CaptureQueriesContext(connection) as ctx:
            response = self.client.get(
                reverse("dashboard:product-variants", args=[self.product.pk]), {"q": "رنگ"}
            )
        self.assertEqual(response.status_code, 200)
        query_count_filtered = len(ctx)

        for i in range(20, 50):
            create_variant(self.product, attribute="رنگ", value=f"رنگ{i}", stock=1)

        with CaptureQueriesContext(connection) as ctx2:
            response = self.client.get(
                reverse("dashboard:product-variants", args=[self.product.pk]), {"q": "رنگ"}
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(query_count_filtered, len(ctx2))

    def test_query_count_bounded_across_pages(self):
        self._make_variable()
        for i in range(60):
            create_variant(self.product, attribute="رنگ", value=f"رنگ{i:03d}", stock=1)
        self.client.get(reverse("dashboard:product-variants", args=[self.product.pk]))  # warm-up

        with CaptureQueriesContext(connection) as ctx_p1:
            response = self.client.get(reverse("dashboard:product-variants", args=[self.product.pk]))
        self.assertEqual(response.status_code, 200)

        with CaptureQueriesContext(connection) as ctx_p2:
            response = self.client.get(
                reverse("dashboard:product-variants", args=[self.product.pk]), {"page": 2}
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(ctx_p1), len(ctx_p2))
