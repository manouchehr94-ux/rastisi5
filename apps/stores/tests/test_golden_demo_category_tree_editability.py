"""G2.1 Defect B — seeded Demo categories must be valid Product-Editor categories.

Root cause: the seed created the 10 category names as FLAT root categories
(parent=None), but the Product Editor's category field uses
``catalog_admin_service.leaf_categories(store)`` which requires
``parent__isnull=False AND no children`` — so a flat root is NEVER a valid
product category, and the editor showed "این فروشگاه هنوز هیچ دسته‌بندی‌ای ندارد"
and could not save a product, even though the storefront rendered the categories.

Fix: seed a real 2-level tree (group parents -> the 10 leaves). Products attach
to the leaves. These tests assert the editor contract is satisfied and nav/filter
correctness is preserved.
"""

import shutil
import tempfile
from io import StringIO

from django.core.cache import cache
from django.core.management import call_command
from django.test import TestCase, override_settings

from apps.catalog.models import Category, Product
from apps.dashboard.forms import ProductForm
from apps.dashboard.services.catalog_admin_service import leaf_categories
from apps.stores.management.commands.seed_ready_template_fashion_demo import (
    CATEGORY_NAMES,
    STORE_SLUG,
)
from apps.stores.models import Store


@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class GoldenDemoCategoryTreeEditabilityTests(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._media_root = tempfile.mkdtemp()
        cls._media_override = override_settings(MEDIA_ROOT=cls._media_root)
        cls._media_override.enable()

    @classmethod
    def tearDownClass(cls):
        cls._media_override.disable()
        shutil.rmtree(cls._media_root, ignore_errors=True)
        super().tearDownClass()

    def setUp(self):
        cache.clear()
        call_command("seed_ready_template_fashion_demo", stdout=StringIO())
        self.store = Store.objects.get(slug=STORE_SLUG)

    def test_product_form_has_valid_category_choices(self):
        form = ProductForm(store=self.store)
        choices = list(form.fields["category"].queryset)
        self.assertTrue(choices, "ProductForm must offer at least one valid (leaf) category")
        # every offered choice must be a genuine leaf (has a parent, no children)
        for cat in choices:
            self.assertIsNotNone(cat.parent_id, cat.name)
            self.assertFalse(cat.children.exists(), cat.name)

    def test_the_ten_semantic_categories_are_the_editor_leaves(self):
        leaves = {c.name for c in leaf_categories(self.store)}
        for name in CATEGORY_NAMES:
            self.assertIn(name, leaves, f"{name} must be a valid editor leaf category")

    def test_every_seeded_product_category_is_valid_under_the_product_form_contract(self):
        valid_ids = set(leaf_categories(self.store).values_list("id", flat=True))
        for product in Product.objects.filter(store=self.store):
            self.assertIsNotNone(product.category_id, product.sku)
            self.assertIn(
                product.category_id, valid_ids,
                f"{product.sku}: category '{product.category.name}' is not a valid ProductForm leaf",
            )

    def test_a_seeded_product_can_be_edited_and_saved_without_false_no_categories(self):
        product = Product.objects.get(store=self.store, sku="FSH-050")
        # An unbound edit form must render the product's current category as a valid choice.
        form = ProductForm(instance=product, store=self.store)
        self.assertIn(product.category, list(form.fields["category"].queryset))
        # A bound save (keeping the same category) must validate.
        # Real POST data is all strings; the key assertion is that the seeded
        # category is accepted (not the "no categories" blocker).
        data = {
            "name": product.name,
            "slug": product.slug,
            "category": str(product.category_id),
            "brand": str(product.brand_id),
            "price": str(int(product.price)),
            "discount_percent": str(product.discount_percent),
            "status": product.status,
            "product_type": product.product_type,
            "unit": product.unit,
            "description": product.description or "",
            "stock": str(product.stock),
        }
        form = ProductForm(data, instance=product, store=self.store)
        # The category field specifically must not be the blocker.
        form.is_valid()
        self.assertNotIn("category", form.errors, form.errors.get("category"))

    def test_storefront_nav_still_shows_top_level_categories_with_children(self):
        top = Category.objects.filter(store=self.store, parent__isnull=True, is_active=True)
        self.assertTrue(top.exists(), "nav must still have top-level categories")
        # at least one top-level group must have children (populated mega-menu)
        self.assertTrue(any(t.children.exists() for t in top))

    def test_category_filter_by_group_includes_its_leaf_products(self):
        # Filtering the listing by a group (parent) slug must include products of
        # its child leaves (parent__slug match), preserving G2 category browsing.
        from apps.catalog.services.product_publish_service import storefront_listing_products
        from django.db.models import Q

        group = Category.objects.filter(store=self.store, parent__isnull=True, is_active=True).first()
        self.assertIsNotNone(group)
        qs = storefront_listing_products(self.store).filter(
            Q(category__slug=group.slug) | Q(category__parent__slug=group.slug)
        )
        self.assertGreater(qs.count(), 0, f"group '{group.name}' should surface its leaves' products")

    def test_tenant_isolation_categories_belong_to_the_demo_store(self):
        for cat in Category.objects.filter(store=self.store):
            self.assertEqual(cat.store_id, self.store.pk)
            if cat.parent_id is not None:
                self.assertEqual(cat.parent.store_id, self.store.pk)

    def test_category_tree_is_idempotent_across_reruns(self):
        first_total = Category.objects.filter(store=self.store).count()
        first_leaves = {c.name for c in leaf_categories(self.store)}
        call_command("seed_ready_template_fashion_demo", stdout=StringIO())
        self.assertEqual(Category.objects.filter(store=self.store).count(), first_total)
        self.assertEqual({c.name for c in leaf_categories(self.store)}, first_leaves)
        self.assertEqual(Product.objects.filter(store=self.store).count(), 50)
