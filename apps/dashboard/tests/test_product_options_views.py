import json
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.catalog.models import Category, CategoryRecommendedOption, Product, ProductOption, ProductVariant, Vendor
from apps.catalog.services.attribute_service import create_attribute, create_attribute_value
from apps.catalog.services.variant_engine_service import add_product_option, generate_variants
from apps.customers.models import Customer
from apps.orders.models import Order, OrderItem, PaymentGateway, ShippingMethod
from apps.stores.models import Store, StoreMembership

User = get_user_model()

HOST = "popt-test.rastisi.ir"


def _akhlaghi():
    return Store.objects.get(slug="akhlaghi")


@override_settings(ALLOWED_HOSTS=[HOST, "testserver"])
class ProductOptionsViewsTestCase(TestCase):
    def setUp(self):
        self.store = _akhlaghi()
        self.store.admin_subdomain = HOST.split(".")[0]
        self.store.save(update_fields=["admin_subdomain"])
        self.vendor = Vendor.objects.create(store=self.store, name="فروشنده", slug="popt-shop")
        self.category = Category.objects.create(store=self.store, name="دسته", slug="popt-cat")
        self.product = Product.objects.create(
            store=self.store, vendor=self.vendor, category=self.category, name="تی‌شرت",
            slug="popt-tshirt", sku="POPT-SKU1", price=Decimal("300000"),
            product_type=Product.ProductType.VARIABLE,
        )
        self.staff = User.objects.create_user(username="09121155001", password="pass12345", is_staff=True)
        StoreMembership.objects.create(
            store=self.store, user=self.staff, role=StoreMembership.Role.OWNER,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )
        self.client = Client(HTTP_HOST=HOST)
        self.client.login(username="09121155001", password="pass12345")


class ProductOptionsPageTests(ProductOptionsViewsTestCase):
    def test_renders_empty_state(self):
        response = self.client.get(reverse("dashboard:product-options", args=[self.product.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "هنوز محوری تعریف نشده است")

    def test_anonymous_denied(self):
        self.client.logout()
        response = self.client.get(reverse("dashboard:product-options", args=[self.product.pk]))
        self.assertEqual(response.status_code, 302)

    def test_legacy_variant_banner_shown(self):
        ProductVariant.objects.create(product=self.product, store=self.store, attribute="رنگ", value="قرمز")
        response = self.client.get(reverse("dashboard:product-options", args=[self.product.pk]))
        self.assertContains(response, "تنوع‌های تک‌محوره‌ی قدیمی")

    def test_other_store_product_404s(self):
        other_store = Store.objects.create(name="فروشگاه دیگر", slug="popt-other", status=Store.Status.ACTIVE)
        other_vendor = Vendor.objects.create(store=other_store, name="ف2", slug="popt-other-v")
        other_category = Category.objects.create(store=other_store, name="د2", slug="popt-other-c")
        other_product = Product.objects.create(
            store=other_store, vendor=other_vendor, category=other_category, name="کالای دیگر",
            slug="popt-other-p", sku="POPT-OTHER-SKU", price=Decimal("1000"),
        )
        response = self.client.get(reverse("dashboard:product-options", args=[other_product.pk]))
        self.assertEqual(response.status_code, 404)

    def test_media_management_link_opens_via_htmx_not_full_navigation(self):
        """لینکِ «مدیریتِ تصاویر» باید با htmx داخلِ مودالِ صفحه باز شود، نه با ناوبریِ کاملِ صفحه.

        چون صفحه‌ی مودالِ تصاویر به‌تنهایی (بدون لایه‌ی اصلی) رندر می‌شود، یک <a href> ساده
        صفحه‌ای بدونِ htmx/Alpine نمایش می‌دهد و هیچ تعاملی کار نمی‌کند.
        """
        add_product_option(self.product, label="رنگ", values=["سبز"])
        generate_variants(self.product)
        images_url = reverse("dashboard:product-images", args=[self.product.pk])
        response = self.client.get(reverse("dashboard:product-options", args=[self.product.pk]))
        self.assertContains(response, f'hx-get="{images_url}"')
        self.assertContains(response, 'hx-target="#admin-modal-content"')


class ProductOptionAddViewTests(ProductOptionsViewsTestCase):
    def test_add_option_with_values(self):
        response = self.client.post(reverse("dashboard:product-option-add", args=[self.product.pk]), {
            "label": "رنگ", "raw_values": "سبز، آبی، زرد",
        })
        self.assertEqual(response.status_code, 200)
        option = ProductOption.objects.get(product=self.product, label="رنگ")
        self.assertEqual(option.values.count(), 3)

    def test_blank_label_rejected(self):
        response = self.client.post(reverse("dashboard:product-option-add", args=[self.product.pk]), {
            "label": "", "raw_values": "",
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(ProductOption.objects.filter(product=self.product).exists())

    def test_cross_store_product_rejected(self):
        other_store = Store.objects.create(name="فروشگاه دیگر", slug="popt-other2", status=Store.Status.ACTIVE)
        other_vendor = Vendor.objects.create(store=other_store, name="ف3", slug="popt-other-v2")
        other_category = Category.objects.create(store=other_store, name="د3", slug="popt-other-c2")
        other_product = Product.objects.create(
            store=other_store, vendor=other_vendor, category=other_category, name="کالای دیگر۲",
            slug="popt-other-p2", sku="POPT-OTHER-SKU2", price=Decimal("1000"),
        )
        response = self.client.post(reverse("dashboard:product-option-add", args=[other_product.pk]), {
            "label": "رنگ",
        })
        self.assertEqual(response.status_code, 404)


class ProductOptionDeactivateActivateTests(ProductOptionsViewsTestCase):
    def test_deactivate_and_activate(self):
        option = add_product_option(self.product, label="رنگ", values=["سبز"])
        self.client.post(reverse("dashboard:product-option-deactivate", args=[self.product.pk, option.pk]))
        option.refresh_from_db()
        self.assertFalse(option.is_active)
        self.client.post(reverse("dashboard:product-option-activate", args=[self.product.pk, option.pk]))
        option.refresh_from_db()
        self.assertTrue(option.is_active)

    def test_other_product_option_404s(self):
        other_product = Product.objects.create(
            store=self.store, vendor=self.vendor, category=self.category, name="کالای دیگر۳",
            slug="popt-other-p3", sku="POPT-OTHER-SKU3", price=Decimal("1000"),
            product_type=Product.ProductType.VARIABLE,
        )
        option = add_product_option(other_product, label="رنگ", values=["سبز"])
        response = self.client.post(
            reverse("dashboard:product-option-deactivate", args=[self.product.pk, option.pk])
        )
        self.assertEqual(response.status_code, 404)


class ProductOptionMoveViewTests(ProductOptionsViewsTestCase):
    def test_move_up_swaps_position(self):
        color = add_product_option(self.product, label="رنگ", values=["سبز"])
        size = add_product_option(self.product, label="سایز", values=["S"])
        self.client.post(
            reverse("dashboard:product-option-move", args=[self.product.pk, size.pk]), {"direction": "up"},
        )
        color.refresh_from_db()
        size.refresh_from_db()
        self.assertEqual(size.position, 0)
        self.assertEqual(color.position, 1)


class ProductOptionValueViewTests(ProductOptionsViewsTestCase):
    def test_add_value(self):
        option = add_product_option(self.product, label="رنگ", values=["سبز"])
        response = self.client.post(
            reverse("dashboard:product-option-value-add", args=[self.product.pk, option.pk]), {"label": "آبی"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(option.values.filter(label="آبی").exists())

    def test_remove_unused_value(self):
        option = add_product_option(self.product, label="رنگ", values=["سبز", "آبی"])
        value = option.values.get(label="سبز")
        self.client.post(reverse("dashboard:product-option-value-remove", args=[self.product.pk, value.pk]))
        self.assertFalse(option.values.filter(pk=value.pk).exists())

    def test_remove_value_from_other_product_404s(self):
        other_product = Product.objects.create(
            store=self.store, vendor=self.vendor, category=self.category, name="کالای دیگر۴",
            slug="popt-other-p4", sku="POPT-OTHER-SKU4", price=Decimal("1000"),
            product_type=Product.ProductType.VARIABLE,
        )
        option = add_product_option(other_product, label="رنگ", values=["سبز"])
        value = option.values.get()
        response = self.client.post(
            reverse("dashboard:product-option-value-remove", args=[self.product.pk, value.pk])
        )
        self.assertEqual(response.status_code, 404)


class ProductVariantsGenerateViewTests(ProductOptionsViewsTestCase):
    def test_generate_creates_variants(self):
        add_product_option(self.product, label="رنگ", values=["سبز", "آبی"])
        add_product_option(self.product, label="سایز", values=["S", "M"])
        response = self.client.post(reverse("dashboard:product-variants-generate", args=[self.product.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.product.variants.count(), 4)

    def test_generate_without_axis_shows_error_toast(self):
        response = self.client.post(reverse("dashboard:product-variants-generate", args=[self.product.pk]))
        self.assertEqual(response.status_code, 200)
        trigger = json.loads(response.headers["HX-Trigger"])
        self.assertEqual(trigger["toast"]["type"], "err")

    def test_idempotent_via_view(self):
        add_product_option(self.product, label="رنگ", values=["سبز"])
        self.client.post(reverse("dashboard:product-variants-generate", args=[self.product.pk]))
        self.client.post(reverse("dashboard:product-variants-generate", args=[self.product.pk]))
        self.assertEqual(self.product.variants.count(), 1)


class ProductVariantSetDefaultViewTests(ProductOptionsViewsTestCase):
    def test_sets_default(self):
        add_product_option(self.product, label="رنگ", values=["سبز", "آبی"])
        generate_variants(self.product)
        variant = self.product.variants.exclude(is_default=True).first()
        self.client.post(
            reverse("dashboard:product-variant-set-default", args=[self.product.pk, variant.pk])
        )
        variant.refresh_from_db()
        self.assertTrue(variant.is_default)


class ProductVariantsBulkUpdateViewTests(ProductOptionsViewsTestCase):
    def _generate(self):
        add_product_option(self.product, label="رنگ", values=["سبز", "آبی"])
        generate_variants(self.product)
        return list(self.product.variants.all())

    def test_bulk_updates_price_stock_sku(self):
        variants = self._generate()
        v1, v2 = variants[0], variants[1]
        response = self.client.post(reverse("dashboard:product-variants-bulk-update", args=[self.product.pk]), {
            "variant_ids": [v1.pk, v2.pk],
            f"variant_{v1.pk}_sku": "NEW-SKU-1", f"variant_{v1.pk}_barcode": "1234567890123",
            f"variant_{v1.pk}_extra_price": "5000", f"variant_{v1.pk}_compare_at_price": "350000",
            f"variant_{v1.pk}_cost": "200000", f"variant_{v1.pk}_stock": "20", f"variant_{v1.pk}_is_active": "on",
            f"variant_{v2.pk}_sku": v2.sku, f"variant_{v2.pk}_barcode": "",
            f"variant_{v2.pk}_extra_price": "0", f"variant_{v2.pk}_compare_at_price": "",
            f"variant_{v2.pk}_cost": "", f"variant_{v2.pk}_stock": "5", f"variant_{v2.pk}_is_active": "on",
        })
        self.assertEqual(response.status_code, 200)
        v1.refresh_from_db()
        self.assertEqual(v1.sku, "NEW-SKU-1")
        self.assertEqual(v1.barcode, "1234567890123")
        self.assertEqual(v1.extra_price, Decimal("5000"))
        self.assertEqual(v1.compare_at_price, Decimal("350000"))
        self.assertEqual(v1.cost, Decimal("200000"))
        self.assertEqual(v1.stock, 20)

    def test_bulk_update_rejects_negative_stock(self):
        variants = self._generate()
        v1 = variants[0]
        response = self.client.post(reverse("dashboard:product-variants-bulk-update", args=[self.product.pk]), {
            "variant_ids": [v1.pk],
            f"variant_{v1.pk}_sku": v1.sku, f"variant_{v1.pk}_barcode": "",
            f"variant_{v1.pk}_extra_price": "0", f"variant_{v1.pk}_compare_at_price": "",
            f"variant_{v1.pk}_cost": "", f"variant_{v1.pk}_stock": "-5", f"variant_{v1.pk}_is_active": "on",
        })
        self.assertEqual(response.status_code, 200)
        v1.refresh_from_db()
        self.assertNotEqual(v1.stock, -5)

    def test_bulk_update_tenant_isolation(self):
        variants = self._generate()
        v1 = variants[0]
        other_store = Store.objects.create(name="فروشگاه دیگر", slug="popt-other5", status=Store.Status.ACTIVE)
        other_vendor = Vendor.objects.create(store=other_store, name="ف5", slug="popt-other-v5")
        other_category = Category.objects.create(store=other_store, name="د5", slug="popt-other-c5")
        other_product = Product.objects.create(
            store=other_store, vendor=other_vendor, category=other_category, name="کالای دیگر۵",
            slug="popt-other-p5", sku="POPT-OTHER-SKU5", price=Decimal("1000"),
            product_type=Product.ProductType.VARIABLE,
        )
        add_product_option(other_product, label="رنگ", values=["زرد"])
        generate_variants(other_product)
        other_variant = other_product.variants.first()
        original_sku = other_variant.sku

        self.client.post(reverse("dashboard:product-variants-bulk-update", args=[self.product.pk]), {
            "variant_ids": [v1.pk, other_variant.pk],
            f"variant_{v1.pk}_sku": v1.sku, f"variant_{v1.pk}_barcode": "",
            f"variant_{v1.pk}_extra_price": "0", f"variant_{v1.pk}_compare_at_price": "",
            f"variant_{v1.pk}_cost": "", f"variant_{v1.pk}_stock": "9", f"variant_{v1.pk}_is_active": "on",
            f"variant_{other_variant.pk}_sku": "HACKED-SKU", f"variant_{other_variant.pk}_barcode": "",
            f"variant_{other_variant.pk}_extra_price": "0", f"variant_{other_variant.pk}_compare_at_price": "",
            f"variant_{other_variant.pk}_cost": "", f"variant_{other_variant.pk}_stock": "9",
            f"variant_{other_variant.pk}_is_active": "on",
        })
        other_variant.refresh_from_db()
        self.assertEqual(other_variant.sku, original_sku)
        self.assertNotEqual(other_variant.sku, "HACKED-SKU")


class ProductVariantsBulkDeleteViewTests(ProductOptionsViewsTestCase):
    def _generate(self):
        add_product_option(self.product, label="رنگ", values=["سبز", "آبی"])
        generate_variants(self.product)
        return list(self.product.variants.all())

    def test_bulk_deletes_selected_variants(self):
        variants = self._generate()
        v1, v2 = variants[0], variants[1]
        response = self.client.post(reverse("dashboard:product-variants-bulk-delete", args=[self.product.pk]), {
            "delete_variant_ids": [v1.pk, v2.pk],
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(ProductVariant.objects.filter(pk__in=[v1.pk, v2.pk]).exists())

    def test_bulk_delete_skips_variant_used_in_order(self):
        variants = self._generate()
        v1 = variants[0]
        customer_user = User.objects.create_user(username="09129990002", password="pass12345")
        customer = Customer.objects.create(user=customer_user, full_name="مشتری", phone="09129990002")
        shipping = ShippingMethod.objects.create(store=self.store, name="پست", slug="post-popt1", cost=Decimal("10000"))
        gateway = PaymentGateway.objects.create(store=self.store, name="درگاه", slug="gw-popt1")
        order = Order.objects.create(
            code="POPT-ORD-1", store=self.store, customer=customer, vendor=self.vendor,
            shipping_method=shipping, payment_gateway=gateway,
        )
        OrderItem.objects.create(
            order=order, product=self.product, variant=v1, product_name=self.product.name,
            unit_price=Decimal("300000"), quantity=1, line_total=Decimal("300000"),
        )
        response = self.client.post(reverse("dashboard:product-variants-bulk-delete", args=[self.product.pk]), {
            "delete_variant_ids": [v1.pk],
        })
        self.assertEqual(response.status_code, 200)
        self.assertTrue(ProductVariant.objects.filter(pk=v1.pk).exists())

    def test_get_not_allowed(self):
        response = self.client.get(reverse("dashboard:product-variants-bulk-delete", args=[self.product.pk]))
        self.assertEqual(response.status_code, 405)

    def test_tenant_isolation(self):
        variants = self._generate()
        v1 = variants[0]
        other_store = Store.objects.create(name="فروشگاه دیگر", slug="popt-other6", status=Store.Status.ACTIVE)
        other_vendor = Vendor.objects.create(store=other_store, name="ف6", slug="popt-other-v6")
        other_category = Category.objects.create(store=other_store, name="د6", slug="popt-other-c6")
        other_product = Product.objects.create(
            store=other_store, vendor=other_vendor, category=other_category, name="کالای دیگر۶",
            slug="popt-other-p6", sku="POPT-OTHER-SKU6", price=Decimal("1000"),
            product_type=Product.ProductType.VARIABLE,
        )
        add_product_option(other_product, label="رنگ", values=["زرد"])
        generate_variants(other_product)
        other_variant = other_product.variants.first()

        self.client.post(reverse("dashboard:product-variants-bulk-delete", args=[self.product.pk]), {
            "delete_variant_ids": [v1.pk, other_variant.pk],
        })
        self.assertFalse(ProductVariant.objects.filter(pk=v1.pk).exists())
        self.assertTrue(ProductVariant.objects.filter(pk=other_variant.pk).exists())  # از فروشگاه دیگر، دست‌نخورده


class ProductOptionsPermissionTests(ProductOptionsViewsTestCase):
    def _login_as(self, role, suffix):
        user = User.objects.create_user(username=f"09121155{suffix}", password="pass12345", is_staff=True)
        StoreMembership.objects.create(
            store=self.store, user=user, role=role,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )
        self.client.logout()
        self.client.login(username=user.username, password="pass12345")

    def test_catalog_manager_can_manage_options(self):
        self._login_as(StoreMembership.Role.CATALOG_MANAGER, "201")
        response = self.client.post(reverse("dashboard:product-option-add", args=[self.product.pk]), {
            "label": "رنگ",
        })
        self.assertEqual(response.status_code, 200)
        self.assertTrue(ProductOption.objects.filter(product=self.product, label="رنگ").exists())

    def test_analyst_cannot_manage_options(self):
        self._login_as(StoreMembership.Role.ANALYST, "202")
        response = self.client.post(reverse("dashboard:product-option-add", args=[self.product.pk]), {
            "label": "رنگ",
        })
        self.assertEqual(response.status_code, 403)

    def test_content_editor_cannot_view_options_page(self):
        self._login_as(StoreMembership.Role.CONTENT_EDITOR, "203")
        response = self.client.get(reverse("dashboard:product-options", args=[self.product.pk]))
        self.assertEqual(response.status_code, 403)

    def test_order_manager_cannot_manage_options(self):
        self._login_as(StoreMembership.Role.ORDER_MANAGER, "204")
        response = self.client.get(reverse("dashboard:product-options", args=[self.product.pk]))
        self.assertEqual(response.status_code, 403)

    def test_staff_without_membership_denied(self):
        user = User.objects.create_user(username="09121155888", password="pass12345", is_staff=True)
        self.client.logout()
        self.client.login(username="09121155888", password="pass12345")
        response = self.client.get(reverse("dashboard:product-options", args=[self.product.pk]))
        self.assertRedirects(response, reverse("catalog:home"), fetch_redirect_response=False)

    def test_wrong_store_membership_denied(self):
        other_store = Store.objects.create(name="فروشگاه دیگر", slug="popt-other6", status=Store.Status.ACTIVE)
        user = User.objects.create_user(username="09121155999", password="pass12345", is_staff=True)
        StoreMembership.objects.create(
            store=other_store, user=user, role=StoreMembership.Role.OWNER,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )
        self.client.logout()
        self.client.login(username="09121155999", password="pass12345")
        response = self.client.get(reverse("dashboard:product-options", args=[self.product.pk]))
        self.assertRedirects(response, reverse("catalog:home"), fetch_redirect_response=False)


class RecommendedOptionTests(ProductOptionsViewsTestCase):
    def _recommend(self, label="رنگ", values=("سبز", "آبی")):
        attribute = create_attribute(self.store, label=label, is_variant_axis=True)
        for value_label in values:
            create_attribute_value(attribute, label=value_label)
        return CategoryRecommendedOption.objects.create(category=self.category, attribute=attribute)

    def test_recommendation_shown_on_page(self):
        self._recommend()
        response = self.client.get(reverse("dashboard:product-options", args=[self.product.pk]))
        self.assertContains(response, "پیشنهادی")
        self.assertContains(response, "رنگ")

    def test_apply_recommendation_creates_option_with_values(self):
        recommendation = self._recommend()
        response = self.client.post(
            reverse("dashboard:product-apply-recommended-option", args=[self.product.pk, recommendation.pk])
        )
        self.assertEqual(response.status_code, 200)
        option = ProductOption.objects.get(product=self.product, label="رنگ")
        self.assertEqual(option.values.count(), 2)

    def test_applied_recommendation_no_longer_listed(self):
        recommendation = self._recommend()
        self.client.post(
            reverse("dashboard:product-apply-recommended-option", args=[self.product.pk, recommendation.pk])
        )
        response = self.client.get(reverse("dashboard:product-options", args=[self.product.pk]))
        self.assertNotContains(response, "پیشنهادی")

    def test_ignoring_recommendation_never_auto_applies(self):
        self._recommend()
        self.client.get(reverse("dashboard:product-options", args=[self.product.pk]))
        self.assertFalse(ProductOption.objects.filter(product=self.product).exists())

    def test_recommendation_from_other_category_not_shown(self):
        other_category = Category.objects.create(store=self.store, name="دسته دیگر", slug="popt-rec-other")
        attribute = create_attribute(self.store, label="جنس", is_variant_axis=True)
        CategoryRecommendedOption.objects.create(category=other_category, attribute=attribute)
        response = self.client.get(reverse("dashboard:product-options", args=[self.product.pk]))
        self.assertNotContains(response, "پیشنهادی")

    def test_apply_recommendation_from_other_product_category_404s(self):
        other_product = Product.objects.create(
            store=self.store, vendor=self.vendor, category=self.category, name="کالای دیگر۷",
            slug="popt-other-p7", sku="POPT-OTHER-SKU7", price=Decimal("1000"),
            product_type=Product.ProductType.VARIABLE,
        )
        other_category = Category.objects.create(store=self.store, name="دسته دیگر۲", slug="popt-rec-other2")
        other_product.category = other_category
        other_product.save(update_fields=["category"])
        recommendation = self._recommend()  # tied to self.category, not other_category
        response = self.client.post(
            reverse("dashboard:product-apply-recommended-option", args=[other_product.pk, recommendation.pk])
        )
        self.assertEqual(response.status_code, 404)
