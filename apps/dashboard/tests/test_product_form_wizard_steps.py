"""Regression tests for the mobile-app-style product-entry wizard.

Covers two fixes:

1. The category quick-add modal's step 1/2/3 blocks used to be
   ``<template x-if="qStep === N">``, which fully unmounts a step's DOM (and its
   ``x-ref``) once you move past it. The breadcrumb's ``qGroupLabel``/``qCategoryLabel``
   getters read those refs, so by step 3 they always showed "—" for the group/category
   even though the correct IDs were still stored and submitted. Fixed by switching to
   ``x-show`` so the refs stay mounted. This test only asserts the rendered HTML no
   longer uses the unmounting ``x-if`` variant for these steps.

2. The product-form wizard is now the approved 5-step shape (اطلاعات پایه / دسته‌بندی /
   قیمت و تنوع / تصاویر و فیلم / سئو و انتشار). The category field lives in its own
   ``tab === 'category'`` step, not inside ``basic`` or ``price``.
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

    def test_category_field_lives_in_category_step_not_basic_or_price_step(self):
        response = self.client.get(reverse("dashboard:product-add"))
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()

        basic_start = html.find("x-show=\"tab === 'basic'\"")
        category_start = html.find("x-show=\"tab === 'category'\"")
        media_start = html.find("x-show=\"tab === 'media'\"")
        self.assertNotEqual(basic_start, -1)
        self.assertNotEqual(category_start, -1)
        self.assertNotEqual(media_start, -1)

        category_field_pos = html.find('id="categoryField"')
        self.assertNotEqual(category_field_pos, -1, "category field not found in rendered HTML")
        self.assertGreater(
            category_field_pos, category_start,
            "category field should be inside the 'category' step, not before it",
        )
        self.assertLess(
            category_field_pos, media_start,
            "category field should come before the 'media' step section",
        )
        # And it must NOT be inside the 'basic' step's section anymore.
        basic_section_html = html[basic_start:category_start]
        self.assertNotIn('id="categoryField"', basic_section_html)

    def test_wizard_step_order_and_labels(self):
        response = self.client.get(reverse("dashboard:product-add"))
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertIn(
            "tabs: [['basic', 'اطلاعات پایه'], ['category', 'دسته‌بندی'], "
            "['price', 'قیمت و تنوع'], ['media', 'تصاویر و فیلم'], ['seo', 'سئو و انتشار']]",
            html,
        )

    def test_wizard_step_strip_is_above_form_not_a_sidebar(self):
        """نوارِ پنج‌مرحله‌ای (``.pe-sidebar`` — قدیم: ``.wizard-progress``) باید
        به‌صورتِ یک ردیفِ افقی *بالایِ* بدنه‌ی فرم رندر شود، نه یک ریلِ کناری —
        با بررسیِ اینکه پیش از تبِ اطلاعاتِ پایه در HTML ظاهر می‌شود. طبقِ
        override بعدیِ CSSِ پروتوتایپ، ``.pe-sidebar`` همیشه grid/flexِ افقی
        است، هرگز یک راهروی عمودی."""
        response = self.client.get(reverse("dashboard:product-add"))
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        wizard_progress_pos = html.find('class="pe-sidebar"')
        basic_tab_pos = html.find("x-show=\"tab === 'basic'\"")
        self.assertNotEqual(wizard_progress_pos, -1)
        self.assertNotEqual(basic_tab_pos, -1)
        self.assertLess(
            wizard_progress_pos, basic_tab_pos,
            "the step strip must render above the tab content, not beside/after it",
        )
