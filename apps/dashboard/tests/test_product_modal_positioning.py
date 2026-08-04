"""Regression tests for the nested-modal scroll/positioning bug.

Every modal that opens *from inside* the already-open product-form modal (category
picker, quick-add-category, price modal, variant price/sales-limit modals, bulk
sales-limit modal) must be wrapped in ``<template x-teleport="body">`` so Alpine
re-parents it to <body> at runtime. Without this, the modal's ``position: fixed``
resolves against the outer modal's own box (which has ``backdrop-filter`` and can be
scrolled), not the real viewport, so a scrolled-down outer modal makes the nested
modal open off-screen above the visible area.

These tests only assert the server-rendered HTML still carries the ``x-teleport="body"``
wrapper immediately before each affected overlay's opening tag — they can't exercise
Alpine's runtime DOM relocation itself (that's covered by manual/Playwright browser
verification), but they guard against someone deleting the wrapper in a future edit.
"""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.catalog.models import Category, Product, Vendor
from apps.catalog.services.variant_engine_service import add_product_option, add_option_value, generate_variants
from apps.stores.models import Store, StoreMembership

User = get_user_model()
HOST = "modalpos.rastisi.localhost"


@override_settings(ALLOWED_HOSTS=[HOST, "testserver"])
class NestedModalTeleportTests(TestCase):
    def setUp(self):
        self.store = Store.objects.create(
            name="فروشگاه تست", slug="modalpos", status=Store.Status.ACTIVE,
            admin_subdomain="modalpos", platform_code="MODALP01",
        )
        self.vendor = Vendor.objects.create(store=self.store, name="فروشنده", slug="modalpos-shop")
        self.category_group = Category.objects.create(store=self.store, name="گروه", slug="modalpos-group")
        self.category = Category.objects.create(
            store=self.store, name="دسته", slug="modalpos-cat", parent=self.category_group,
        )
        self.staff = User.objects.create_user(username="modalposstaff", password="pass12345", is_staff=True)
        StoreMembership.objects.create(
            store=self.store, user=self.staff, role=StoreMembership.Role.OWNER,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )
        self.client = Client(HTTP_HOST=HOST)
        self.client.login(username="modalposstaff", password="pass12345")

    def _assert_teleported(self, html, marker, label):
        idx = html.find(marker)
        self.assertNotEqual(idx, -1, f"{label}: marker {marker!r} not found in rendered HTML")
        preceding = html[max(0, idx - 400):idx]
        self.assertIn(
            '<template x-teleport="body">', preceding,
            f"{label}: expected a <template x-teleport=\"body\"> wrapper directly before {marker!r} "
            "so this modal escapes the outer product-form modal's backdrop-filter containing block",
        )

    def test_category_picker_and_quick_add_modals_are_teleported(self):
        response = self.client.get(reverse("dashboard:product-add"))
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self._assert_teleported(html, 'class="overlay" :class="{ open: pickerOpen }"', "category picker modal")
        self._assert_teleported(html, 'class="overlay" :class="{ open: quickAddOpen }"', "quick-add-category modal")

    def test_simple_product_price_modal_is_teleported(self):
        response = self.client.get(reverse("dashboard:product-add"))
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self._assert_teleported(html, 'x-show="priceModalOpen"', "simple-product price modal")

    def test_variant_price_and_sales_limit_modals_are_teleported(self):
        product = Product.objects.create(
            store=self.store, vendor=self.vendor, category=self.category, name="کیف",
            slug="modalpos-bag", sku="MODALP-SKU1", price=Decimal("100000"),
            product_type=Product.ProductType.VARIABLE,
        )
        option = add_product_option(product, label="رنگ")
        add_option_value(option, "قرمز")
        add_option_value(option, "آبی")
        generate_variants(product)

        response = self.client.get(reverse("dashboard:product-edit", args=[product.pk]))
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self._assert_teleported(html, 'x-show="bulkSalesLimitOpen"', "bulk sales-limit modal")
        self._assert_teleported(html, 'x-show="priceOpen"', "per-variant price modal")
        self._assert_teleported(html, 'x-show="salesLimitOpen"', "per-variant sales-limit modal")
