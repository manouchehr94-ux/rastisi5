from decimal import Decimal

from django.test import TestCase

from apps.catalog.models import Category, Product, Vendor
from apps.dashboard.services.catalog_admin_service import (
    CategoryDeleteError,
    can_delete_category,
    category_chain,
    category_tree_context,
    filtered_products,
    generate_unique_slug,
    leaf_categories,
)


class GenerateUniqueSlugTests(TestCase):
    def test_generates_slugified_name(self):
        slug = generate_unique_slug(Category, "لوازم جانبی")
        self.assertTrue(slug)

    def test_avoids_collision_with_suffix(self):
        Category.objects.create(name="آشپزخانه", slug="kitchen-t1")
        first = generate_unique_slug(Category, "kitchen-t1")
        self.assertNotEqual(first, "kitchen-t1")

    def test_excludes_current_instance_when_editing(self):
        cat = Category.objects.create(name="آشپزخانه", slug="kitchen-t2")
        slug = generate_unique_slug(Category, "kitchen-t2", instance=cat)
        self.assertEqual(slug, "kitchen-t2")


class LeafCategoriesTests(TestCase):
    def test_only_returns_categories_with_parent(self):
        main = Category.objects.create(name="گروه اصلی", slug="main-lc")
        sub = Category.objects.create(name="زیرگروه", slug="sub-lc", parent=main)
        result = list(leaf_categories())
        self.assertIn(sub, result)
        self.assertNotIn(main, result)


class CategoryChainTests(TestCase):
    def test_none_returns_dash(self):
        self.assertEqual(category_chain(None), "—")

    def test_top_level_returns_name_only(self):
        main = Category.objects.create(name="گروه اصلی", slug="main-cc")
        self.assertEqual(category_chain(main), "گروه اصلی")

    def test_sub_returns_parent_and_name(self):
        main = Category.objects.create(name="گروه اصلی", slug="main-cc2")
        sub = Category.objects.create(name="زیرگروه", slug="sub-cc2", parent=main)
        self.assertEqual(category_chain(sub), "گروه اصلی › زیرگروه")


class FilteredProductsTests(TestCase):
    def setUp(self):
        vendor = Vendor.objects.create(name="فروشگاه", slug="shop-fp")
        main = Category.objects.create(name="دیجیتال", slug="main-fp")
        self.sub = Category.objects.create(name="موبایل", slug="sub-fp", parent=main)
        self.p1 = Product.objects.create(
            vendor=vendor, category=self.sub, name="گوشی هوشمند", slug="phone-fp",
            sku="SKU-FP1", price=Decimal("1000000"), stock=5, status=Product.Status.ACTIVE,
        )
        self.p2 = Product.objects.create(
            vendor=vendor, category=self.sub, name="کیف چرم", slug="bag-fp",
            sku="SKU-FP2", price=Decimal("200000"), stock=0, status=Product.Status.ACTIVE,
        )
        self.p3 = Product.objects.create(
            vendor=vendor, category=self.sub, name="کفش ورزشی", slug="shoe-fp",
            sku="SKU-FP3", price=Decimal("300000"), stock=10, status=Product.Status.INACTIVE,
        )

    def test_search_by_name(self):
        result = filtered_products(q="گوشی")
        self.assertEqual(list(result), [self.p1])

    def test_search_by_sku(self):
        result = filtered_products(q="SKU-FP2")
        self.assertEqual(list(result), [self.p2])

    def test_filter_by_category(self):
        result = filtered_products(category_id=str(self.sub.id))
        self.assertEqual(set(result), {self.p1, self.p2, self.p3})

    def test_filter_out_of_stock(self):
        result = filtered_products(status="out")
        self.assertEqual(list(result), [self.p2])

    def test_filter_by_status(self):
        result = filtered_products(status=Product.Status.INACTIVE)
        self.assertEqual(list(result), [self.p3])


class CategoryTreeContextTests(TestCase):
    def test_counts_reflect_products_and_subcategories(self):
        vendor = Vendor.objects.create(name="فروشگاه", slug="shop-ctc")
        main = Category.objects.create(name="گروه اصلی", slug="main-ctc")
        sub = Category.objects.create(name="زیرگروه", slug="sub-ctc", parent=main)
        Product.objects.create(
            vendor=vendor, category=sub, name="محصول", slug="prod-ctc",
            sku="SKU-CTC1", price=Decimal("1000"),
        )
        context = category_tree_context()
        row = next(r for r in context["rows"] if r["category"] == main)
        self.assertEqual(row["product_count"], 1)
        self.assertEqual(len(row["subs"]), 1)


class CanDeleteCategoryTests(TestCase):
    def test_category_with_children_cannot_be_deleted(self):
        main = Category.objects.create(name="گروه اصلی", slug="main-cd1")
        Category.objects.create(name="زیرگروه", slug="sub-cd1", parent=main)
        with self.assertRaises(CategoryDeleteError):
            can_delete_category(main)

    def test_category_with_products_cannot_be_deleted(self):
        vendor = Vendor.objects.create(name="فروشگاه", slug="shop-cd2")
        main = Category.objects.create(name="گروه اصلی", slug="main-cd2")
        sub = Category.objects.create(name="زیرگروه", slug="sub-cd2", parent=main)
        Product.objects.create(
            vendor=vendor, category=sub, name="محصول", slug="prod-cd2",
            sku="SKU-CD2", price=Decimal("1000"),
        )
        with self.assertRaises(CategoryDeleteError):
            can_delete_category(sub)

    def test_empty_leaf_category_can_be_deleted(self):
        main = Category.objects.create(name="گروه اصلی", slug="main-cd3")
        sub = Category.objects.create(name="زیرگروه", slug="sub-cd3", parent=main)
        can_delete_category(sub)  # should not raise
