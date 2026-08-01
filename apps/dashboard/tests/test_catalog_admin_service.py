from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from apps.catalog.models import Category, Product, Vendor
from apps.dashboard.services.catalog_admin_service import (
    CategoryDeleteError,
    can_delete_category,
    category_chain,
    category_tree_context,
    default_vendor,
    filtered_products,
    generate_unique_slug,
    leaf_categories,
)
from apps.stores.models import Store, StoreMembership
from django.contrib.auth import get_user_model

User = get_user_model()


def _akhlaghi():
    return Store.objects.get(slug="akhlaghi")


class GenerateUniqueSlugTests(TestCase):
    def setUp(self):
        self.store = _akhlaghi()

    def test_generates_slugified_name(self):
        slug = generate_unique_slug(Category, "لوازم جانبی", store=self.store)
        self.assertTrue(slug)

    def test_avoids_collision_with_suffix(self):
        Category.objects.create(store=self.store, name="آشپزخانه", slug="kitchen-t1")
        first = generate_unique_slug(Category, "kitchen-t1", store=self.store)
        self.assertNotEqual(first, "kitchen-t1")

    def test_excludes_current_instance_when_editing(self):
        cat = Category.objects.create(store=self.store, name="آشپزخانه", slug="kitchen-t2")
        slug = generate_unique_slug(Category, "kitchen-t2", store=self.store, instance=cat)
        self.assertEqual(slug, "kitchen-t2")


class LeafCategoriesTests(TestCase):
    def setUp(self):
        self.store = _akhlaghi()

    def test_only_returns_categories_with_parent(self):
        main = Category.objects.create(store=self.store, name="گروه اصلی", slug="main-lc")
        sub = Category.objects.create(store=self.store, name="زیرگروه", slug="sub-lc", parent=main)
        result = list(leaf_categories(self.store))
        self.assertIn(sub, result)
        self.assertNotIn(main, result)


class CategoryChainTests(TestCase):
    def setUp(self):
        self.store = _akhlaghi()

    def test_none_returns_dash(self):
        self.assertEqual(category_chain(None), "—")

    def test_top_level_returns_name_only(self):
        main = Category.objects.create(store=self.store, name="گروه اصلی", slug="main-cc")
        self.assertEqual(category_chain(main), "گروه اصلی")

    def test_sub_returns_parent_and_name(self):
        main = Category.objects.create(store=self.store, name="گروه اصلی", slug="main-cc2")
        sub = Category.objects.create(store=self.store, name="زیرگروه", slug="sub-cc2", parent=main)
        self.assertEqual(category_chain(sub), "گروه اصلی › زیرگروه")


class FilteredProductsTests(TestCase):
    def setUp(self):
        self.store = _akhlaghi()
        vendor = Vendor.objects.create(store=self.store, name="فروشگاه", slug="shop-fp")
        main = Category.objects.create(store=self.store, name="دیجیتال", slug="main-fp")
        self.sub = Category.objects.create(store=self.store, name="موبایل", slug="sub-fp", parent=main)
        self.p1 = Product.objects.create(
            store=self.store, vendor=vendor, category=self.sub, name="گوشی هوشمند", slug="phone-fp",
            sku="SKU-FP1", price=Decimal("1000000"), stock=5, status=Product.Status.ACTIVE,
        )
        self.p2 = Product.objects.create(
            store=self.store, vendor=vendor, category=self.sub, name="کیف چرم", slug="bag-fp",
            sku="SKU-FP2", price=Decimal("200000"), stock=0, status=Product.Status.ACTIVE,
        )
        self.p3 = Product.objects.create(
            store=self.store, vendor=vendor, category=self.sub, name="کفش ورزشی", slug="shoe-fp",
            sku="SKU-FP3", price=Decimal("300000"), stock=10, status=Product.Status.INACTIVE,
        )

    def test_search_by_name(self):
        result = filtered_products(self.store, q="گوشی")
        self.assertEqual(list(result), [self.p1])

    def test_search_by_sku(self):
        result = filtered_products(self.store, q="SKU-FP2")
        self.assertEqual(list(result), [self.p2])

    def test_filter_by_category(self):
        result = filtered_products(self.store, category_id=str(self.sub.id))
        self.assertEqual(set(result), {self.p1, self.p2, self.p3})

    def test_filter_out_of_stock(self):
        result = filtered_products(self.store, status="out")
        self.assertEqual(list(result), [self.p2])

    def test_filter_by_status(self):
        result = filtered_products(self.store, status=Product.Status.INACTIVE)
        self.assertEqual(list(result), [self.p3])


class CategoryTreeContextTests(TestCase):
    def setUp(self):
        self.store = _akhlaghi()

    def test_counts_reflect_products_and_subcategories(self):
        vendor = Vendor.objects.create(store=self.store, name="فروشگاه", slug="shop-ctc")
        main = Category.objects.create(store=self.store, name="گروه اصلی", slug="main-ctc")
        sub = Category.objects.create(store=self.store, name="زیرگروه", slug="sub-ctc", parent=main)
        Product.objects.create(
            store=self.store, vendor=vendor, category=sub, name="محصول", slug="prod-ctc",
            sku="SKU-CTC1", price=Decimal("1000"),
        )
        context = category_tree_context(self.store)
        row = next(r for r in context["rows"] if r["category"] == main)
        self.assertEqual(row["product_count"], 1)
        self.assertEqual(len(row["subs"]), 1)


class CanDeleteCategoryTests(TestCase):
    def setUp(self):
        self.store = _akhlaghi()

    def test_category_with_children_cannot_be_deleted(self):
        main = Category.objects.create(store=self.store, name="گروه اصلی", slug="main-cd1")
        Category.objects.create(store=self.store, name="زیرگروه", slug="sub-cd1", parent=main)
        with self.assertRaises(CategoryDeleteError):
            can_delete_category(main)

    def test_category_with_products_cannot_be_deleted(self):
        vendor = Vendor.objects.create(store=self.store, name="فروشگاه", slug="shop-cd2")
        main = Category.objects.create(store=self.store, name="گروه اصلی", slug="main-cd2")
        sub = Category.objects.create(store=self.store, name="زیرگروه", slug="sub-cd2", parent=main)
        Product.objects.create(
            store=self.store, vendor=vendor, category=sub, name="محصول", slug="prod-cd2",
            sku="SKU-CD2", price=Decimal("1000"),
        )
        with self.assertRaises(CategoryDeleteError):
            can_delete_category(sub)

    def test_empty_leaf_category_can_be_deleted(self):
        main = Category.objects.create(store=self.store, name="گروه اصلی", slug="main-cd3")
        sub = Category.objects.create(store=self.store, name="زیرگروه", slug="sub-cd3", parent=main)
        can_delete_category(sub)  # should not raise


class DefaultVendorTests(TestCase):
    """Product creation must never fail because no Vendor exists (RastiSi is
    currently a single-merchant store builder — the Store itself stands in
    as the seller until real multi-vendor mode exists)."""

    def setUp(self):
        self.store = Store.objects.create(name="فروشگاه بدون فروشنده", slug="no-vendor-store", status=Store.Status.ACTIVE)

    def test_creates_default_vendor_when_none_exists(self):
        self.assertFalse(Vendor.objects.filter(store=self.store).exists())
        vendor = default_vendor(self.store)
        self.assertIsNotNone(vendor)
        self.assertEqual(Vendor.objects.filter(store=self.store).count(), 1)
        self.assertEqual(vendor.name, self.store.name)

    def test_second_call_reuses_same_auto_created_vendor(self):
        first = default_vendor(self.store)
        second = default_vendor(self.store)
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(Vendor.objects.filter(store=self.store).count(), 1)

    def test_returns_existing_vendor_without_creating_another(self):
        existing = Vendor.objects.create(store=self.store, name="فروشنده‌ی موجود", slug="existing-vendor")
        vendor = default_vendor(self.store)
        self.assertEqual(vendor.pk, existing.pk)
        self.assertEqual(Vendor.objects.filter(store=self.store).count(), 1)

    def test_auto_created_vendor_owned_by_store_owner(self):
        owner = User.objects.create_user(username="09121166001", password="pass12345")
        StoreMembership.objects.create(
            store=self.store, user=owner, role=StoreMembership.Role.OWNER,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )
        vendor = default_vendor(self.store)
        self.assertEqual(vendor.owner_id, owner.pk)
