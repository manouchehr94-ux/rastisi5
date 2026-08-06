"""A4 — رفع بدهیِ اتمیک‌بودنِ شناسایی‌شده در ممیزی: reorder_brands قبلاً
بدون ``@transaction.atomic`` بود (اگرچه bulk_update تک‌فراخوانی بود، هیچ
تضمین صریحی برای اتمیک‌بودن کل عملیات وجود نداشت)."""

from django.test import TestCase

from apps.catalog.models import Brand
from apps.catalog.services.brand_service import (
    BrandReorderError,
    create_brand,
    reorder_brands,
)
from apps.stores.models import Store


def _akhlaghi():
    return Store.objects.get(slug="akhlaghi")


def _other_store():
    return Store.objects.create(name="فروشگاه دوم برند", slug="brand-reorder-second-store", admin_subdomain="brand-reorder-second-store")


class ReorderBrandsTests(TestCase):
    def setUp(self):
        self.store = _akhlaghi()
        self.b1 = create_brand(self.store, name="اول")
        self.b2 = create_brand(self.store, name="دوم")
        self.b3 = create_brand(self.store, name="سوم")

    def test_reorders_by_posted_id_sequence(self):
        reorder_brands(self.store, [self.b3.pk, self.b1.pk, self.b2.pk])
        self.b1.refresh_from_db()
        self.b2.refresh_from_db()
        self.b3.refresh_from_db()
        self.assertEqual(self.b3.sort_order, 0)
        self.assertEqual(self.b1.sort_order, 1)
        self.assertEqual(self.b2.sort_order, 2)

    def test_duplicate_ids_rejected_no_rows_changed(self):
        original = {b.pk: b.sort_order for b in [self.b1, self.b2, self.b3]}
        with self.assertRaises(BrandReorderError):
            reorder_brands(self.store, [self.b1.pk, self.b1.pk, self.b2.pk])
        for brand in [self.b1, self.b2, self.b3]:
            brand.refresh_from_db()
            self.assertEqual(brand.sort_order, original[brand.pk])

    def test_cross_store_ids_are_ignored(self):
        other_store = _other_store()
        other_brand = create_brand(other_store, name="برند فروشگاه دیگر")
        other_original_order = other_brand.sort_order

        reorder_brands(self.store, [self.b2.pk, other_brand.pk, self.b1.pk])
        other_brand.refresh_from_db()
        self.assertEqual(other_brand.sort_order, other_original_order)

    def test_unknown_ids_are_silently_ignored(self):
        reorder_brands(self.store, [self.b2.pk, 999999, self.b1.pk])
        self.b1.refresh_from_db()
        self.b2.refresh_from_db()
        self.assertEqual(self.b2.sort_order, 0)
        self.assertEqual(self.b1.sort_order, 1)

    def test_mid_operation_failure_rolls_back_completely(self):
        from unittest.mock import patch

        from django.db.models.query import QuerySet

        original_order = {b.pk: b.sort_order for b in [self.b1, self.b2, self.b3]}
        original_update = QuerySet.update
        call_count = {"n": 0}

        def flaky_update(self_qs, *args, **kwargs):
            call_count["n"] += 1
            if call_count["n"] == 2:
                raise RuntimeError("simulated mid-operation failure")
            return original_update(self_qs, *args, **kwargs)

        with patch.object(QuerySet, "update", flaky_update):
            with self.assertRaises(RuntimeError):
                reorder_brands(self.store, [self.b3.pk, self.b1.pk, self.b2.pk])

        for brand in [self.b1, self.b2, self.b3]:
            brand.refresh_from_db()
            self.assertEqual(brand.sort_order, original_order[brand.pk])
