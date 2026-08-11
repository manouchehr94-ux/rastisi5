"""تست‌های پنل Django Admin (django.contrib.admin در مسیر /admin/) — نه پنل
اختصاصی فروشگاه (apps.dashboard). این تست‌ها اثبات می‌کنند که در انتظار
پنل مدیریت تنوع در PR2، مسیر Django Admin نمی‌تواند قواعد سرویس تنوع را
دور بزند: نوع کالا فقط-خواندنی است، افزودن/ویرایش/حذف تنوع از این پنل ممکن
نیست، و تنوعِ استفاده‌شده در سفارش هرگز از این پنل حذف نمی‌شود.
"""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.catalog.models import Category, Product, ProductVariant, Vendor
from apps.customers.models import Customer
from apps.orders.models import Order, OrderItem, PaymentGateway, ShippingMethod
from apps.stores.models import Store

User = get_user_model()


def _akhlaghi():
    return Store.objects.get(slug="akhlaghi")


def _full_inline_post_data(get_response, product, category, vendor):
    """داده‌ی POST کامل فرم ویرایش کالا را با پرکردن مدیریت‌فرم واقعی هر سه این‌لاین می‌سازد
    (بدون افزودن/تغییر هیچ ردیفی — فقط برای POST بدون خطای اعتبارسنجی فرمست).

    عمداً TOTAL_FORMS را برابر INITIAL_FORMS نگه می‌داریم (نه total_form_count که شامل
    ردیف خالی «extra» هم می‌شود)، چون آن ردیف خالی هیچ داده‌ای ندارد و اعتبارسنجی آن
    (فیلدهای اجباری مثل تصویر/عنوان مشخصه) بی‌ربط به این تست است.
    """
    management_form = get_response.context["inline_admin_formsets"]
    data = {
        "name": product.name, "slug": product.slug, "sku": product.sku,
        "category": category.pk, "vendor": vendor.pk, "price": str(product.price),
        "discount_percent": "0", "stock": "0", "status": "active",
        "rating": "0", "reviews_count": "0", "sold_count": "0", "views_count": "0",
    }
    for inline in management_form:
        formset = inline.formset
        prefix = formset.prefix
        initial_count = formset.initial_form_count()
        data[f"{prefix}-TOTAL_FORMS"] = str(initial_count)
        data[f"{prefix}-INITIAL_FORMS"] = str(initial_count)
        data[f"{prefix}-MIN_NUM_FORMS"] = "0"
        data[f"{prefix}-MAX_NUM_FORMS"] = "0"
        for index in range(initial_count):
            form = formset.forms[index]
            for field_name, value in form.initial.items():
                data[f"{prefix}-{index}-{field_name}"] = value
            data[f"{prefix}-{index}-id"] = form.instance.pk
    return data


class DjangoAdminVariantFixture(TestCase):
    def setUp(self):
        self.superuser = User.objects.create_superuser(
            username="admin-diag", email="admin-diag@example.com", password="pass12345"
        )
        self.client.login(username="admin-diag", password="pass12345")

        self.store = _akhlaghi()
        self.vendor = Vendor.objects.create(store=self.store, name="فروشگاه", slug="shop-adm")
        self.category = Category.objects.create(store=self.store, name="دسته", slug="cat-adm")
        self.product = Product.objects.create(
            store=self.store, vendor=self.vendor, category=self.category, name="شیلنگ فن‌کویل", slug="hose-adm",
            sku="SKU-HOSE-ADM", price=Decimal("200000"),
        )
        self.variant = ProductVariant.objects.create(product=self.product, attribute="طول", value="30")


class ProductTypeReadOnlyTests(DjangoAdminVariantFixture):
    def test_product_type_declared_readonly_on_admin_class(self):
        from apps.catalog.admin import ProductAdmin

        self.assertIn("product_type", ProductAdmin.readonly_fields)

    def test_change_form_has_no_editable_product_type_widget(self):
        url = reverse("admin:catalog_product_change", args=[self.product.pk])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'name="product_type"')

    def test_posting_a_different_product_type_does_not_change_it(self):
        url = reverse("admin:catalog_product_change", args=[self.product.pk])
        get_resp = self.client.get(url)
        data = _full_inline_post_data(get_resp, self.product, self.category, self.vendor)
        data["unit"] = self.product.unit
        data["product_type"] = "variable"   
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 302, response.content[:2000])
        self.product.refresh_from_db()
        self.assertEqual(self.product.product_type, Product.ProductType.SIMPLE)


class ProductVariantInlineRestrictionTests(DjangoAdminVariantFixture):
    def test_cannot_add_variant_through_inline(self):
        url = reverse("admin:catalog_product_change", args=[self.product.pk])
        get_resp = self.client.get(url)
        management_form = get_resp.context["inline_admin_formsets"]
        variant_inline = next(
            f for f in management_form if f.opts.model is ProductVariant
        )
        prefix = variant_inline.formset.prefix
        data = self._base_product_post_data()
        data.update({
            f"{prefix}-TOTAL_FORMS": "1",
            f"{prefix}-INITIAL_FORMS": "0",
            f"{prefix}-MIN_NUM_FORMS": "0",
            f"{prefix}-MAX_NUM_FORMS": "0",
            f"{prefix}-0-product": str(self.product.pk),
            f"{prefix}-0-attribute": "رنگ",
            f"{prefix}-0-value": "قرمز",
        })
        self.client.post(url, data)
        self.assertEqual(self.product.variants.count(), 1)

    def test_cannot_edit_variant_through_inline(self):
        url = reverse("admin:catalog_product_change", args=[self.product.pk])
        get_resp = self.client.get(url)
        management_form = get_resp.context["inline_admin_formsets"]
        variant_inline = next(
            f for f in management_form if f.opts.model is ProductVariant
        )
        prefix = variant_inline.formset.prefix
        data = self._base_product_post_data()
        data.update({
            f"{prefix}-TOTAL_FORMS": "1",
            f"{prefix}-INITIAL_FORMS": "1",
            f"{prefix}-MIN_NUM_FORMS": "0",
            f"{prefix}-MAX_NUM_FORMS": "0",
            f"{prefix}-0-id": str(self.variant.pk),
            f"{prefix}-0-product": str(self.product.pk),
            f"{prefix}-0-attribute": "طول",
            f"{prefix}-0-value": "999-تغییر-غیرمجاز",
        })
        self.client.post(url, data)
        self.variant.refresh_from_db()
        self.assertEqual(self.variant.value, "30")

    def test_cannot_delete_variant_through_inline(self):
        url = reverse("admin:catalog_product_change", args=[self.product.pk])
        get_resp = self.client.get(url)
        management_form = get_resp.context["inline_admin_formsets"]
        variant_inline = next(
            f for f in management_form if f.opts.model is ProductVariant
        )
        prefix = variant_inline.formset.prefix
        data = self._base_product_post_data()
        data.update({
            f"{prefix}-TOTAL_FORMS": "1",
            f"{prefix}-INITIAL_FORMS": "1",
            f"{prefix}-MIN_NUM_FORMS": "0",
            f"{prefix}-MAX_NUM_FORMS": "0",
            f"{prefix}-0-id": str(self.variant.pk),
            f"{prefix}-0-product": str(self.product.pk),
            f"{prefix}-0-attribute": "طول",
            f"{prefix}-0-value": "30",
            f"{prefix}-0-DELETE": "on",
        })
        self.client.post(url, data)
        self.assertTrue(ProductVariant.objects.filter(pk=self.variant.pk).exists())

    def test_existing_variant_still_visible_on_change_page(self):
        url = reverse("admin:catalog_product_change", args=[self.product.pk])
        response = self.client.get(url)
        self.assertContains(response, "طول")
        self.assertContains(response, "30")

    def _base_product_post_data(self):
        return {
            "name": self.product.name, "slug": self.product.slug, "sku": self.product.sku,
            "category": self.category.pk, "vendor": self.vendor.pk, "price": str(self.product.price),
            "discount_percent": "0", "stock": "0", "status": "active",
            "images-TOTAL_FORMS": "0", "images-INITIAL_FORMS": "0",
            "images-MIN_NUM_FORMS": "0", "images-MAX_NUM_FORMS": "0",
            "specifications-TOTAL_FORMS": "0", "specifications-INITIAL_FORMS": "0",
            "specifications-MIN_NUM_FORMS": "0", "specifications-MAX_NUM_FORMS": "0",
        }


class StandaloneProductVariantAdminTests(DjangoAdminVariantFixture):
    def test_add_view_denied(self):
        response = self.client.get(reverse("admin:catalog_productvariant_add"))
        self.assertEqual(response.status_code, 403)

    def test_change_view_get_renders_read_only_not_editable_form(self):
        """GET همچنان ۲۰۰ برمی‌گرداند (بازرسی فقط-خواندنی مطابق ترجیح این بازسازی) اما بدون فیلد قابل‌ویرایش."""
        response = self.client.get(reverse("admin:catalog_productvariant_change", args=[self.variant.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'name="value"')
        self.assertNotContains(response, 'name="stock"')

    def test_change_view_post_edit_denied(self):
        url = reverse("admin:catalog_productvariant_change", args=[self.variant.pk])
        response = self.client.post(url, {
            "product": self.product.pk, "attribute": "طول", "value": "999-تغییر-غیرمجاز",
            "stock": "0", "extra_price": "0", "display_order": "0", "is_active": "on",
        })
        self.assertEqual(response.status_code, 403)
        self.variant.refresh_from_db()
        self.assertEqual(self.variant.value, "30")

    def test_delete_view_denied(self):
        response = self.client.get(reverse("admin:catalog_productvariant_delete", args=[self.variant.pk]))
        self.assertEqual(response.status_code, 403)
        self.assertTrue(ProductVariant.objects.filter(pk=self.variant.pk).exists())

    def test_bulk_delete_action_not_available_in_changelist(self):
        response = self.client.get(reverse("admin:catalog_productvariant_changelist"))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'value="delete_selected"')

    def test_bulk_delete_action_post_denied(self):
        response = self.client.post(reverse("admin:catalog_productvariant_changelist"), {
            "action": "delete_selected",
            "_selected_action": [str(self.variant.pk)],
        })
        self.assertTrue(ProductVariant.objects.filter(pk=self.variant.pk).exists())
        self.assertIn(response.status_code, (200, 302, 400))

    def test_list_view_still_shows_existing_variants(self):
        response = self.client.get(reverse("admin:catalog_productvariant_changelist"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "طول")


class SoldVariantCannotBeDeletedThroughAdminTests(DjangoAdminVariantFixture):
    def setUp(self):
        super().setUp()
        user = User.objects.create_user(username="09121112233adm", password="pass12345")
        customer = Customer.objects.create(user=user, full_name="مشتری", phone="09121112233")
        shipping = ShippingMethod.objects.create(store=self.store, name="پست", slug="post-adm", cost=Decimal("10000"))
        gateway = PaymentGateway.objects.create(store=self.store, name="درگاه", slug="gw-adm")
        self.order = Order.objects.create(
            code="DM-ADMXYZ", store=self.store, customer=customer, vendor=self.vendor,
            shipping_method=shipping, payment_gateway=gateway,
        )
        self.sold_variant = ProductVariant.objects.create(product=self.product, attribute="طول", value="50")
        OrderItem.objects.create(
            order=self.order, product=self.product, variant=self.sold_variant,
            product_name=self.product.name, quantity=1,
            unit_price=Decimal("200000"), line_total=Decimal("200000"),
        )

    def test_delete_view_denied_for_sold_variant(self):
        response = self.client.get(
            reverse("admin:catalog_productvariant_delete", args=[self.sold_variant.pk])
        )
        self.assertEqual(response.status_code, 403)
        self.assertTrue(ProductVariant.objects.filter(pk=self.sold_variant.pk).exists())

    def test_bulk_delete_denied_for_sold_variant(self):
        self.client.post(reverse("admin:catalog_productvariant_changelist"), {
            "action": "delete_selected",
            "_selected_action": [str(self.sold_variant.pk)],
        })
        self.assertTrue(ProductVariant.objects.filter(pk=self.sold_variant.pk).exists())
        order_item = OrderItem.objects.get(order=self.order)
        self.assertEqual(order_item.variant_id, self.sold_variant.pk)

    def test_product_change_inline_cannot_delete_sold_variant(self):
        url = reverse("admin:catalog_product_change", args=[self.product.pk])
        get_resp = self.client.get(url)
        management_form = get_resp.context["inline_admin_formsets"]
        variant_inline = next(f for f in management_form if f.opts.model is ProductVariant)
        prefix = variant_inline.formset.prefix
        data = {
            "name": self.product.name, "slug": self.product.slug, "sku": self.product.sku,
            "category": self.category.pk, "vendor": self.vendor.pk, "price": str(self.product.price),
            "discount_percent": "0", "stock": "0", "status": "active",
            "images-TOTAL_FORMS": "0", "images-INITIAL_FORMS": "0",
            "images-MIN_NUM_FORMS": "0", "images-MAX_NUM_FORMS": "0",
            "specifications-TOTAL_FORMS": "0", "specifications-INITIAL_FORMS": "0",
            "specifications-MIN_NUM_FORMS": "0", "specifications-MAX_NUM_FORMS": "0",
            f"{prefix}-TOTAL_FORMS": "2",
            f"{prefix}-INITIAL_FORMS": "2",
            f"{prefix}-MIN_NUM_FORMS": "0",
            f"{prefix}-MAX_NUM_FORMS": "0",
            f"{prefix}-0-id": str(self.variant.pk),
            f"{prefix}-0-product": str(self.product.pk),
            f"{prefix}-0-attribute": "طول",
            f"{prefix}-0-value": "30",
            f"{prefix}-1-id": str(self.sold_variant.pk),
            f"{prefix}-1-product": str(self.product.pk),
            f"{prefix}-1-attribute": "طول",
            f"{prefix}-1-value": "50",
            f"{prefix}-1-DELETE": "on",
        }
        self.client.post(url, data)
        self.assertTrue(ProductVariant.objects.filter(pk=self.sold_variant.pk).exists())


class SeedShopStillWorksTests(TestCase):
    def test_seed_shop_succeeds_on_fresh_database(self):
        from django.core.management import call_command

        call_command("seed_shop", verbosity=0)
        self.assertTrue(Product.objects.exists())

    def test_products_seeded_with_variants_have_consistent_product_type(self):
        from django.core.management import call_command

        call_command("seed_shop", verbosity=0)
        for product in Product.objects.filter(variants__isnull=False).distinct():
            self.assertEqual(
                product.product_type, Product.ProductType.VARIABLE,
                f"محصول «{product.slug}» تنوع دارد ولی product_type برابر simple است.",
            )
        for product in Product.objects.filter(variants__isnull=True):
            self.assertEqual(product.product_type, Product.ProductType.SIMPLE)
