from decimal import Decimal

from django.db import IntegrityError, transaction
from django.test import TestCase

from apps.catalog.models import Category, Product, ProductVariant, VariantMutationError, Vendor


class VariantQuerySetFixture(TestCase):
    def setUp(self):
        self.vendor = Vendor.objects.create(name="فروشگاه", slug="shop-vqs")
        self.category = Category.objects.create(name="دسته", slug="cat-vqs")
        self.product = Product.objects.create(
            vendor=self.vendor, category=self.category, name="شیلنگ فن‌کویل", slug="hose-vqs",
            sku="SKU-HOSE-VQS", price=Decimal("200000"),
        )


class BulkCreateNormalizationTests(VariantQuerySetFixture):
    def test_bulk_create_populates_normalized_attribute_and_value(self):
        objs = [ProductVariant(product=self.product, attribute="طول", value="30")]
        ProductVariant.objects.bulk_create(objs)
        variant = ProductVariant.objects.get(product=self.product, value="30")
        self.assertEqual(variant.normalized_attribute, "طول")
        self.assertEqual(variant.normalized_value, "30")

    def test_bulk_create_normalizes_persian_digits(self):
        objs = [ProductVariant(product=self.product, attribute="طول", value="۳۰")]
        ProductVariant.objects.bulk_create(objs)
        variant = ProductVariant.objects.get(product=self.product, attribute="طول")
        self.assertEqual(variant.normalized_value, "30")

    def test_bulk_create_normalizes_arabic_indic_digits(self):
        objs = [ProductVariant(product=self.product, attribute="طول", value="٣٠")]
        ProductVariant.objects.bulk_create(objs)
        variant = ProductVariant.objects.get(product=self.product, attribute="طول")
        self.assertEqual(variant.normalized_value, "30")

    def test_bulk_create_normalizes_arabic_yeh_and_kaf(self):
        objs = [ProductVariant(product=self.product, attribute="جنس", value="مشکي")]
        ProductVariant.objects.bulk_create(objs)
        variant = ProductVariant.objects.get(product=self.product, attribute="جنس")
        # مقدار نمایشی دست‌نخورده می‌ماند، ولی کلید نرمال‌شده معادل نگارش فارسی است.
        self.assertEqual(variant.value, "مشکي")
        self.assertEqual(variant.normalized_value, "مشکی")

    def test_bulk_create_triggers_active_duplicate_constraint_after_normalization(self):
        ProductVariant.objects.create(product=self.product, attribute="طول", value="30")
        objs = [ProductVariant(product=self.product, attribute=" طول ", value="۳۰")]
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                ProductVariant.objects.bulk_create(objs)

    def test_bulk_create_distinct_values_do_not_falsely_collide(self):
        objs = [
            ProductVariant(product=self.product, attribute="طول", value="30"),
            ProductVariant(product=self.product, attribute="طول", value="40"),
        ]
        ProductVariant.objects.bulk_create(objs)
        self.assertEqual(self.product.variants.count(), 2)

    def test_bulk_create_preserves_batch_size_argument(self):
        objs = [
            ProductVariant(product=self.product, attribute="طول", value=str(v))
            for v in range(30, 33)
        ]
        ProductVariant.objects.bulk_create(objs, batch_size=1)
        self.assertEqual(self.product.variants.count(), 3)

    def test_bulk_create_normalizes_sku_digits(self):
        objs = [ProductVariant(product=self.product, attribute="طول", value="30", sku="HOSE-۳۰")]
        ProductVariant.objects.bulk_create(objs)
        variant = ProductVariant.objects.get(product=self.product, attribute="طول")
        self.assertEqual(variant.sku, "HOSE-30")


class QuerySetUpdateRestrictionTests(VariantQuerySetFixture):
    def setUp(self):
        super().setUp()
        self.variant = ProductVariant.objects.create(product=self.product, attribute="طول", value="30")

    def test_update_attribute_rejected(self):
        with self.assertRaises(VariantMutationError):
            ProductVariant.objects.filter(pk=self.variant.pk).update(attribute="عرض")

    def test_update_value_rejected(self):
        with self.assertRaises(VariantMutationError):
            ProductVariant.objects.filter(pk=self.variant.pk).update(value="40")

    def test_update_sku_rejected(self):
        with self.assertRaises(VariantMutationError):
            ProductVariant.objects.filter(pk=self.variant.pk).update(sku="NEW-SKU")

    def test_update_normalized_attribute_rejected(self):
        with self.assertRaises(VariantMutationError):
            ProductVariant.objects.filter(pk=self.variant.pk).update(normalized_attribute="x")

    def test_update_normalized_value_rejected(self):
        with self.assertRaises(VariantMutationError):
            ProductVariant.objects.filter(pk=self.variant.pk).update(normalized_value="x")

    def test_update_stock_still_allowed(self):
        ProductVariant.objects.filter(pk=self.variant.pk).update(stock=25)
        self.variant.refresh_from_db()
        self.assertEqual(self.variant.stock, 25)

    def test_update_display_order_still_allowed(self):
        ProductVariant.objects.filter(pk=self.variant.pk).update(display_order=5)
        self.variant.refresh_from_db()
        self.assertEqual(self.variant.display_order, 5)

    def test_update_extra_price_still_allowed(self):
        ProductVariant.objects.filter(pk=self.variant.pk).update(extra_price=Decimal("15000"))
        self.variant.refresh_from_db()
        self.assertEqual(self.variant.extra_price, Decimal("15000"))

    def test_update_is_active_still_allowed(self):
        ProductVariant.objects.filter(pk=self.variant.pk).update(is_active=False)
        self.variant.refresh_from_db()
        self.assertFalse(self.variant.is_active)

    def test_update_rejects_when_mixing_blocked_and_allowed_fields(self):
        with self.assertRaises(VariantMutationError):
            ProductVariant.objects.filter(pk=self.variant.pk).update(stock=10, value="40")

    def test_rejected_update_does_not_partially_apply(self):
        with self.assertRaises(VariantMutationError):
            ProductVariant.objects.filter(pk=self.variant.pk).update(stock=99, attribute="عرض")
        self.variant.refresh_from_db()
        self.assertEqual(self.variant.stock, 0)
        self.assertEqual(self.variant.attribute, "طول")


class BulkUpdateRestrictionTests(VariantQuerySetFixture):
    def setUp(self):
        super().setUp()
        self.v1 = ProductVariant.objects.create(product=self.product, attribute="طول", value="30")
        self.v2 = ProductVariant.objects.create(product=self.product, attribute="طول", value="40")

    def test_bulk_update_display_order_still_works(self):
        self.v1.display_order = 5
        self.v2.display_order = 6
        ProductVariant.objects.bulk_update([self.v1, self.v2], ["display_order"])
        self.v1.refresh_from_db()
        self.v2.refresh_from_db()
        self.assertEqual(self.v1.display_order, 5)
        self.assertEqual(self.v2.display_order, 6)

    def test_bulk_update_stock_and_active_still_works(self):
        self.v1.stock = 12
        self.v1.is_active = False
        ProductVariant.objects.bulk_update([self.v1], ["stock", "is_active"])
        self.v1.refresh_from_db()
        self.assertEqual(self.v1.stock, 12)
        self.assertFalse(self.v1.is_active)

    def test_bulk_update_value_rejected(self):
        self.v1.value = "50"
        with self.assertRaises(VariantMutationError):
            ProductVariant.objects.bulk_update([self.v1], ["value"])

    def test_bulk_update_attribute_rejected(self):
        self.v1.attribute = "عرض"
        with self.assertRaises(VariantMutationError):
            ProductVariant.objects.bulk_update([self.v1], ["attribute"])

    def test_bulk_update_sku_rejected(self):
        self.v1.sku = "NEW-SKU"
        with self.assertRaises(VariantMutationError):
            ProductVariant.objects.bulk_update([self.v1], ["sku"])

    def test_bulk_update_normalized_fields_rejected(self):
        self.v1.normalized_value = "x"
        with self.assertRaises(VariantMutationError):
            ProductVariant.objects.bulk_update([self.v1], ["normalized_value"])

    def test_bulk_update_cannot_create_stale_normalized_fields(self):
        """اگر bulk_update برای فیلدهای غیرحساس صدا زده شود، فیلدهای normalized_* دست‌نخورده و درست باقی می‌مانند."""
        original_normalized_value = self.v1.normalized_value
        self.v1.value = "این تغییر در دیتابیس ذخیره نمی‌شود چون فقط stock ارسال شده"
        self.v1.stock = 7
        ProductVariant.objects.bulk_update([self.v1], ["stock"])
        refreshed = ProductVariant.objects.get(pk=self.v1.pk)
        self.assertEqual(refreshed.stock, 7)
        self.assertEqual(refreshed.value, "30")
        self.assertEqual(refreshed.normalized_value, original_normalized_value)


class ReorderVariantsServiceStillWorksTests(VariantQuerySetFixture):
    def test_reorder_variants_service_bulk_update_path_unaffected(self):
        from apps.catalog.services.variant_service import reorder_variants

        v1 = ProductVariant.objects.create(product=self.product, attribute="طول", value="30")
        v2 = ProductVariant.objects.create(product=self.product, attribute="طول", value="40")
        reorder_variants(self.product, [v2.pk, v1.pk])
        v1.refresh_from_db()
        v2.refresh_from_db()
        self.assertEqual(v2.display_order, 0)
        self.assertEqual(v1.display_order, 1)
