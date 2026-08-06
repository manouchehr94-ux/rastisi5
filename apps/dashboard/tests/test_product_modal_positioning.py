"""Regression tests for the nested-modal scroll/positioning bug, and for a follow-up
bug the fix itself introduced.

Every modal that opens *from inside* the already-open product-form modal
(quick-add-category, variant price/sales-limit modals, bulk sales-limit modal) must be
wrapped in ``<template x-teleport="body">`` so Alpine re-parents it to <body> at
runtime. Without this, the modal's ``position: fixed`` resolves against the outer
modal's own box (which has ``backdrop-filter`` and can be scrolled), not the real
viewport, so a scrolled-down outer modal makes the nested modal open off-screen above
the visible area.

(The old category tree-picker modal and the product-level "set price" modal this file
used to also cover were both removed in the exact-prototype rewrite — category is now
two plain <select> elements, and simple-product price/discount/stock are inline fields,
neither behind a modal anymore.)

These tests only assert the server-rendered HTML still carries the ``x-teleport="body"``
wrapper immediately before each affected overlay's opening tag — they can't exercise
Alpine's runtime DOM relocation itself (that's covered by manual/Playwright browser
verification), but they guard against someone deleting the wrapper in a future edit.

Second bug (found via live browser testing, not caught by the tests above): htmx only
wires up ``hx-*`` attributes on elements it swaps in itself. An element Alpine's
``x-teleport`` moves into <body> via a raw ``appendChild`` is invisible to htmx's own
processing pipeline, so any ``hx-post``/``hx-get`` button *inside* a teleported modal
silently does nothing when clicked — no request, no error, nothing. This affected the
quick-add-category "افزودن" button and the per-variant price/sales-limit "save" buttons.
Every teleported overlay that contains an ``hx-*`` attribute must call
``htmx.process($el)`` in its own ``x-init`` so htmx notices it once Alpine mounts it.
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

    def test_quick_add_category_modal_is_teleported(self):
        """طبقِ پروتوتایپِ نهایی، مودالِ درختیِ انتخابِ دسته‌بندی (pickerOpen)
        کاملاً حذف شد — دسته‌بندی اکنون دو <select> ساده است (گروهِ اصلی/
        زیرگروه)، بدونِ هیچ مودالی. فقط مودالِ سه‌مرحله‌ایِ «+ ساختِ
        دسته‌بندیِ جدید» (quickAddOpen) باقی مانده و همچنان باید teleport
        شده باشد."""
        response = self.client.get(reverse("dashboard:product-add"), follow=True)
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertNotIn("pickerOpen", html)
        self._assert_teleported(html, 'class="overlay" :class="{ open: quickAddOpen }"', "quick-add-category modal")

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

    def test_quick_add_category_submit_closes_modal_before_its_own_swap(self):
        """The quick-add-category modal's own successful submit does an
        ``hx-swap="outerHTML"`` on ``#categoryField`` — its *own* container. Since the
        modal is teleported to <body> (not a descendant of #categoryField anymore), that
        swap replaces #categoryField without necessarily tearing down the teleported
        clone, leaving an orphaned, still-``open`` copy stuck on screen (looks exactly
        like the "Add button doesn't work" bug: nothing visibly happens because the
        stale modal is still covering everything). The submit button must close the
        modal itself before/alongside the request so the old copy is already hidden
        regardless of what happens to the DOM node.

        This must NOT be done with a plain ``@click`` on the same button that also
        carries ``hx-post``: Alpine's ``@click`` and htmx's own click listener both react
        to the same click event, and if ``@click`` hides the button (via the now-false
        ``quickAddOpen`` driving its ancestor's ``x-show``) before htmx's listener runs,
        htmx silently never sends the request at all (confirmed live: zero network
        requests fired). The state change must instead ride htmx's own
        ``htmx:before-request`` event via ``hx-on::htmx:before-request``, which only
        fires once htmx has already committed to sending the request.
        """
        response = self.client.get(reverse("dashboard:product-add"), follow=True)
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        submit_marker = 'hx-target="#categoryField" hx-swap="outerHTML"'
        idx = html.find(submit_marker)
        self.assertNotEqual(idx, -1, "quick-add-category submit button not found")
        preceding = html[max(0, idx - 200):idx]
        self.assertIn(
            'hx-on::htmx:before-request="quickAddOpen = false"', preceding,
            "quick-add-category's own submit button must close quickAddOpen via the "
            "htmx:before-request hook, not a plain @click (which races with htmx's own "
            "click handling and can suppress the request entirely)",
        )
        self.assertNotIn(
            '@click="quickAddOpen = false"\n                hx-post', html,
            "closing the modal via a plain @click on the hx-post button races with "
            "htmx's click handling and can silently prevent the request from firing",
        )

    def test_teleported_modals_with_hx_attributes_call_htmx_process(self):
        """htmx only wires up ``hx-*`` attributes on elements it swaps in itself.
        Alpine's ``x-teleport`` moves content into <body> via a raw DOM insertion that
        htmx never sees, so any ``hx-post``/``hx-get`` button inside a teleported modal
        is otherwise permanently inert — clicking it does nothing, with no error and no
        network request (confirmed live for the quick-add-category "افزودن" button and
        the per-variant price/sales-limit "save" buttons). Every teleported overlay that
        contains an hx-* attribute must call ``htmx.process($el)`` from its own
        ``x-init`` so htmx notices it once Alpine mounts it.
        """
        response = self.client.get(reverse("dashboard:product-add"), follow=True)
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        idx = html.find('class="overlay" :class="{ open: quickAddOpen }"')
        self.assertNotEqual(idx, -1, "quick-add-category overlay not found")
        line = html[idx:html.find(">", idx)]
        self.assertIn(
            'x-init="htmx.process($el)"', line,
            "quick-add-category overlay contains an hx-post button, so it must call "
            "htmx.process($el) in its own x-init once Alpine teleports it into <body>",
        )

        product = Product.objects.create(
            store=self.store, vendor=self.vendor, category=self.category, name="کیف",
            slug="modalpos-htmxproc-bag", sku="MODALP-HTMXPROC1", price=Decimal("100000"),
            product_type=Product.ProductType.VARIABLE,
        )
        option = add_product_option(product, label="رنگ")
        add_option_value(option, "قرمز")
        generate_variants(product)
        response = self.client.get(reverse("dashboard:product-edit", args=[product.pk]))
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()

        for marker, label in [
            ('x-show="priceOpen"', "per-variant price modal"),
            ('x-show="salesLimitOpen"', "per-variant sales-limit modal"),
        ]:
            idx = html.find(marker)
            self.assertNotEqual(idx, -1, f"{label} not found")
            line = html[idx:html.find(">", idx)]
            self.assertIn(
                'x-init="htmx.process($el)"', line,
                f"{label} contains hx-post button(s), so it must call htmx.process($el) "
                "in its own x-init once Alpine teleports it into <body>",
            )
