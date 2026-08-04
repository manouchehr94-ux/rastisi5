"""Regression tests for the mobile-app-style product-entry wizard.

Covers two fixes:

1. The category quick-add modal's step 1/2/3 blocks used to be
   ``<template x-if="qStep === N">``, which fully unmounts a step's DOM (and its
   ``x-ref``) once you move past it. The breadcrumb's ``qGroupLabel``/``qCategoryLabel``
   getters read those refs, so by step 3 they always showed "—" for the group/category
   even though the correct IDs were still stored and submitted. Fixed by switching to
   ``x-show`` so the refs stay mounted. This test only asserts the rendered HTML no
   longer uses the unmounting ``x-if`` variant for these steps.

2. The product-form wizard was restructured: step 1 ("basic") no longer contains the
   category field — it moved into step 2 ("price"/"type"), right after the product-type
   selector, per the new mobile step order (basic info -> type & category -> media -> seo).
"""
from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.catalog.models import Category, Vendor
from apps.stores.models import Store, StoreMembership

User = get_user_model()
HOST = "wizsteps.rastisi.localhost"


@override_settings(ALLOWED_HOSTS=[HOST, "testserver"])
class ProductFormWizardStepsTests(TestCase):
    def setUp(self):
        self.store = Store.objects.create(
            name="فروشگاه تست", slug="wizsteps", status=Store.Status.ACTIVE,
            admin_subdomain="wizsteps", platform_code="WIZSTEP1",
        )
        Vendor.objects.create(store=self.store, name="فروشنده", slug="wizsteps-shop")
        Category.objects.create(store=self.store, name="گروه", slug="wizsteps-group")
        self.staff = User.objects.create_user(username="wizstepsstaff", password="pass12345", is_staff=True)
        StoreMembership.objects.create(
            store=self.store, user=self.staff, role=StoreMembership.Role.OWNER,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )
        self.client = Client(HTTP_HOST=HOST)
        self.client.login(username="wizstepsstaff", password="pass12345")

    def test_quick_add_category_steps_use_x_show_not_x_if(self):
        response = self.client.get(reverse("dashboard:product-add"))
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertNotIn('<template x-if="qStep === 1">', html)
        self.assertNotIn('<template x-if="qStep === 2">', html)
        self.assertNotIn('<template x-if="qStep === 3">', html)
        self.assertIn('x-show="qStep === 1"', html)
        self.assertIn('x-show="qStep === 2"', html)
        self.assertIn('x-show="qStep === 3"', html)

    def test_category_field_lives_in_price_step_not_basic_step(self):
        response = self.client.get(reverse("dashboard:product-add"))
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()

        # The four x-show="tab === '...'" sections keep their original file order
        # (basic, media, price, seo) — only the *step-indicator* array (asserted in
        # test_wizard_step_order_and_labels) controls the visual/navigation order.
        # What matters here is simply: the category field must be inside the 'price'
        # step's section and nowhere else (not in 'basic', not in 'seo').
        basic_start = html.find("x-show=\"tab === 'basic'\"")
        price_start = html.find("x-show=\"tab === 'price'\"")
        seo_start = html.find("x-show=\"tab === 'seo'\"")
        self.assertNotEqual(basic_start, -1)
        self.assertNotEqual(price_start, -1)
        self.assertNotEqual(seo_start, -1)

        category_field_pos = html.find('id="categoryField"')
        self.assertNotEqual(category_field_pos, -1, "category field not found in rendered HTML")
        self.assertGreater(
            category_field_pos, price_start,
            "category field should be inside the 'price' (type) step, not before it",
        )
        self.assertLess(
            category_field_pos, seo_start,
            "category field should come before the 'seo' step section",
        )
        # And it must NOT be inside the 'basic' step's section anymore.
        basic_section_html = html[basic_start:price_start]
        self.assertNotIn('id="categoryField"', basic_section_html)

    def test_wizard_step_order_and_labels(self):
        response = self.client.get(reverse("dashboard:product-add"))
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertIn(
            "tabs: [['basic', 'اطلاعات پایه'], ['price', 'نوعِ کالا'], "
            "['media', 'تصاویر و ویدیو'], ['seo', 'سئو و انتشار']]",
            html,
        )
