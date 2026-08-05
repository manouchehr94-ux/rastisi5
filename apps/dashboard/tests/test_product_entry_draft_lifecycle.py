"""تست‌های معماریِ پیش‌نویسِ داخلیِ «افزودنِ کالا» (Product Entry full-page
rebuild) — نگاه کنید به docs/reports/PRODUCT_ENTRY_FULL_PAGE_ROOT_CAUSE.md.

پوشش: مسیرِ تمام‌صفحه‌ی Create (بدونِ مودال)، ساخت/ازسرگیریِ پیش‌نویس،
ایزوله‌سازیِ چندمستأجری، دسترسیِ غیرمجاز، افزودنِ فوریِ ویژگی/تنوع پیش از
تکمیلِ نام/دسته‌بندی، لغوِ صریحِ پیش‌نویس، و پاک‌سازیِ خودکارِ پیش‌نویسِ رهاشده."""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.catalog.models import Category, Product, ProductVariant, Vendor
from apps.catalog.services.product_draft_service import (
    cleanup_stale_product_drafts,
    discard_product_draft,
    get_or_create_product_draft,
)
from apps.stores.models import Store, StoreMembership

User = get_user_model()
HOST = "draftflow.rastisi.localhost"


@override_settings(ALLOWED_HOSTS=[HOST, "testserver"])
class ProductDraftFullPageFlowTests(TestCase):
    def setUp(self):
        self.store = Store.objects.create(
            name="فروشگاه پیش‌نویس", slug="draftflow", status=Store.Status.ACTIVE,
            admin_subdomain="draftflow", platform_code="DRAFTFL1",
        )
        self.vendor = Vendor.objects.create(store=self.store, name="فروشنده", slug="draftflow-shop")
        self.main = Category.objects.create(store=self.store, name="گروه", slug="draftflow-group")
        self.sub = Category.objects.create(store=self.store, name="زیرگروه", slug="draftflow-sub", parent=self.main)
        self.staff = User.objects.create_user(username="draftflowstaff", password="pass12345", is_staff=True)
        StoreMembership.objects.create(
            store=self.store, user=self.staff, role=StoreMembership.Role.OWNER,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )
        self.client = Client(HTTP_HOST=HOST)
        self.client.login(username="draftflowstaff", password="pass12345")

    def test_add_product_navigates_to_a_real_full_page_url_not_a_modal_fragment(self):
        """GETِ «افزودنِ کالا» یک ریدایرکتِ واقعیِ 302 به یک URLِ
        /products/<pk>/edit/ واقعی است — نه رندرِ درجایِ یک فرگمنت."""
        response = self.client.get(reverse("dashboard:product-add"))
        self.assertEqual(response.status_code, 302)
        draft = Product.objects.get(store=self.store, is_draft_placeholder=True)
        self.assertEqual(response.url, reverse("dashboard:product-edit", args=[draft.pk]))

        page = self.client.get(response.url)
        self.assertEqual(page.status_code, 200)
        content = page.content.decode()
        # صفحه‌ی کامل (نه فرگمنتِ مودال) — چیدمانِ استانداردِ پنل هم هست.
        self.assertIn("<html", content)
        self.assertIn('id="productSaveForm"', content)

    def test_draft_is_created_transparently_and_is_resumable(self):
        """دو بارِ پشتِ سرِ هم «افزودنِ کالا» — بدونِ لمسِ فرم — باید دقیقاً
        یک پیش‌نویس بسازد، نه دو تا (ازسرگیری، نه ساختِ تکراری)."""
        first = self.client.get(reverse("dashboard:product-add"))
        second = self.client.get(reverse("dashboard:product-add"))
        self.assertEqual(first.url, second.url)
        self.assertEqual(Product.objects.filter(store=self.store, is_draft_placeholder=True).count(), 1)

    def test_draft_never_appears_in_product_list_or_stats(self):
        self.client.get(reverse("dashboard:product-add"))
        response = self.client.get(reverse("dashboard:product-list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, ">۰<")  # کل کالاها هنوز صفر است
        self.assertNotContains(response, "🛍️")  # آیکنِ پیش‌فرضِ کالای واقعی نه پیش‌نویس

    def test_tabs_and_variant_editor_are_available_before_name_or_category_is_set(self):
        """ریشه‌یِ اصلیِ باگ: تبِ «قیمت و تنوع» باید همان اولین بار قابلِ
        استفاده باشد، حتی وقتی هنوز هیچ فیلدی پر نشده — نه پیامِ «ابتدا
        اطلاعاتِ پایه را تکمیل کنید»."""
        response = self.client.get(reverse("dashboard:product-add"), follow=True)
        content = response.content.decode()
        self.assertIn('id="productOptionsBody"', content)
        self.assertNotIn("ابتدا نام و کدِ کالا را در تبِ", content)
        self.assertNotIn("ابتدا کالا را ذخیره کنید", content)

    def test_attributes_and_variants_can_be_created_immediately_on_a_fresh_draft(self):
        """سناریوی دقیقِ بخشِ ۷: ویژگی/مقدار/تنوع پیش از تکمیلِ نام یا
        دسته‌بندی، مستقیماً رویِ pkِ پیش‌نویس ذخیره می‌شوند."""
        self.client.get(reverse("dashboard:product-add"))
        draft = Product.objects.get(store=self.store, is_draft_placeholder=True)
        self.assertIsNone(draft.category_id)
        self.assertEqual(draft.name, "")

        # سوییچ به «کالای دارای تنوع» یک AJAXِ سبک است (نه ذخیره‌ی کاملِ فرم)
        # — نگاه کنید به ``product_set_type``؛ بدونِ آن، ``product_type`` تا
        # اولین ذخیره‌ی کاملِ فرم «ساده» می‌ماند و ساختِ ترکیب‌ها رد می‌شود.
        response = self.client.post(
            reverse("dashboard:product-set-type", args=[draft.pk]), {"product_type": "variable"},
        )
        self.assertEqual(response.status_code, 200)
        draft.refresh_from_db()
        self.assertEqual(draft.product_type, Product.ProductType.VARIABLE)

        response = self.client.post(
            reverse("dashboard:product-option-add", args=[draft.pk]),
            {"label": "طول", "raw_values": "۱۰۰، ۱۵۰، ۲۰۰"},
        )
        self.assertEqual(response.status_code, 200)
        response = self.client.post(
            reverse("dashboard:product-option-add", args=[draft.pk]),
            {"label": "جنس", "raw_values": "استیل، آلومینیوم"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(draft.options.count(), 2)

        response = self.client.post(reverse("dashboard:product-variants-generate", args=[draft.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            ProductVariant.objects.filter(product=draft).exclude(combination_key="").count(), 6,
        )

    def test_finalizing_a_draft_requires_the_normal_required_fields(self):
        """ذخیره‌ی نهایی همچنان نام/کد/دسته‌بندی/قیمتِ واقعی می‌خواهد —
        شُلی فقط برایِ حالتِ پیش‌نویسِ *داخلی* است، نه برایِ ذخیره‌ی واقعی."""
        self.client.get(reverse("dashboard:product-add"))
        draft = Product.objects.get(store=self.store, is_draft_placeholder=True)
        response = self.client.post(reverse("dashboard:product-edit", args=[draft.pk]), {
            "name": "", "sku": "", "category": "", "price": "", "discount_percent": "0", "stock": "0",
            "status": "active", "icon": "", "description": "",
        })
        self.assertEqual(response.status_code, 200)
        draft.refresh_from_db()
        self.assertTrue(draft.is_draft_placeholder)  # هنوز پیش‌نویس است

        response = self.client.post(reverse("dashboard:product-edit", args=[draft.pk]), {
            "name": "کالای نهایی", "sku": "DRAFT-SKU1", "category": self.sub.id,
            "price": "150000", "discount_percent": "0", "stock": "5",
            "status": "active", "icon": "", "description": "",
        })
        self.assertEqual(response.status_code, 200)
        draft.refresh_from_db()
        self.assertFalse(draft.is_draft_placeholder)
        self.assertEqual(draft.name, "کالای نهایی")

    def test_discard_draft_deletes_it_after_confirmation_action(self):
        self.client.get(reverse("dashboard:product-add"))
        draft = Product.objects.get(store=self.store, is_draft_placeholder=True)
        response = self.client.post(reverse("dashboard:product-discard-draft", args=[draft.pk]))
        self.assertRedirects(response, reverse("dashboard:product-list"))
        self.assertFalse(Product.objects.filter(pk=draft.pk).exists())

    def test_discard_draft_requires_post(self):
        self.client.get(reverse("dashboard:product-add"))
        draft = Product.objects.get(store=self.store, is_draft_placeholder=True)
        response = self.client.get(reverse("dashboard:product-discard-draft", args=[draft.pk]))
        self.assertEqual(response.status_code, 405)
        self.assertTrue(Product.objects.filter(pk=draft.pk).exists())

    def test_discard_draft_cannot_target_a_real_finalized_product(self):
        """اکشنِ لغو فقط برایِ پیش‌نویسِ داخلی است — یک کالایِ واقعیِ ذخیره‌شده
        هرگز نباید از این مسیر حذف شود."""
        product = Product.objects.create(
            store=self.store, vendor=self.vendor, category=self.sub, name="کالای واقعی",
            slug="draftflow-real", sku="DRAFTFLOW-REAL1", price=Decimal("10000"),
        )
        response = self.client.post(reverse("dashboard:product-discard-draft", args=[product.pk]))
        self.assertEqual(response.status_code, 404)
        self.assertTrue(Product.objects.filter(pk=product.pk).exists())

    def test_no_hx_get_product_modal_triggers_left_in_list_templates(self):
        response = self.client.get(reverse("dashboard:product-list"))
        content = response.content.decode()
        self.assertNotIn(f"""hx-get="{reverse('dashboard:product-add')}\"""", content)


@override_settings(ALLOWED_HOSTS=["draft-a.rastisi.localhost", "draft-b.rastisi.localhost", "testserver"])
class ProductDraftTenantIsolationTests(TestCase):
    """دو Store مستقل — پیش‌نویسِ یکی هرگز نباید از/برایِ دیگری قابلِ دسترسی باشد."""

    def setUp(self):
        self.store_a = Store.objects.create(
            name="فروشگاه آ", slug="draft-a", status=Store.Status.ACTIVE,
            admin_subdomain="draft-a", platform_code="DRAFTA001",
        )
        self.store_b = Store.objects.create(
            name="فروشگاه ب", slug="draft-b", status=Store.Status.ACTIVE,
            admin_subdomain="draft-b", platform_code="DRAFTB001",
        )
        Vendor.objects.create(store=self.store_a, name="فروشنده آ", slug="draft-a-shop")
        Vendor.objects.create(store=self.store_b, name="فروشنده ب", slug="draft-b-shop")
        self.staff_a = User.objects.create_user(username="drafta-staff", password="pass12345", is_staff=True)
        self.staff_b = User.objects.create_user(username="draftb-staff", password="pass12345", is_staff=True)
        StoreMembership.objects.create(
            store=self.store_a, user=self.staff_a, role=StoreMembership.Role.OWNER,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )
        StoreMembership.objects.create(
            store=self.store_b, user=self.staff_b, role=StoreMembership.Role.OWNER,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )

    def test_store_b_staff_cannot_open_store_a_draft_by_guessing_its_pk(self):
        client_a = Client(HTTP_HOST="draft-a.rastisi.localhost")
        client_a.login(username="drafta-staff", password="pass12345")
        client_a.get(reverse("dashboard:product-add"))
        draft_a = Product.objects.get(store=self.store_a, is_draft_placeholder=True)

        client_b = Client(HTTP_HOST="draft-b.rastisi.localhost")
        client_b.login(username="draftb-staff", password="pass12345")
        response = client_b.get(reverse("dashboard:product-edit", args=[draft_a.pk]))
        self.assertEqual(response.status_code, 404)

    def test_store_b_staff_cannot_discard_store_a_draft(self):
        client_a = Client(HTTP_HOST="draft-a.rastisi.localhost")
        client_a.login(username="drafta-staff", password="pass12345")
        client_a.get(reverse("dashboard:product-add"))
        draft_a = Product.objects.get(store=self.store_a, is_draft_placeholder=True)

        client_b = Client(HTTP_HOST="draft-b.rastisi.localhost")
        client_b.login(username="draftb-staff", password="pass12345")
        response = client_b.post(reverse("dashboard:product-discard-draft", args=[draft_a.pk]))
        self.assertEqual(response.status_code, 404)
        self.assertTrue(Product.objects.filter(pk=draft_a.pk).exists())

    def test_each_store_gets_its_own_independent_draft(self):
        client_a = Client(HTTP_HOST="draft-a.rastisi.localhost")
        client_a.login(username="drafta-staff", password="pass12345")
        client_a.get(reverse("dashboard:product-add"))

        client_b = Client(HTTP_HOST="draft-b.rastisi.localhost")
        client_b.login(username="draftb-staff", password="pass12345")
        client_b.get(reverse("dashboard:product-add"))

        self.assertEqual(Product.objects.filter(store=self.store_a, is_draft_placeholder=True).count(), 1)
        self.assertEqual(Product.objects.filter(store=self.store_b, is_draft_placeholder=True).count(), 1)


class ProductDraftServiceTests(TestCase):
    """آزمونِ مستقیمِ سرویسِ چرخه‌یِ عمرِ پیش‌نویس — بدونِ HTTP."""

    def setUp(self):
        self.store = Store.objects.create(
            name="فروشگاه سرویس", slug="draftsvc", admin_subdomain="draftsvc",
        )
        self.vendor = Vendor.objects.create(store=self.store, name="فروشنده", slug="draftsvc-shop")
        self.user = User.objects.create_user(username="draftsvc-user", password="pass12345")

    def test_get_or_create_resumes_existing_draft(self):
        first = get_or_create_product_draft(self.store, self.user)
        second = get_or_create_product_draft(self.store, self.user)
        self.assertEqual(first.pk, second.pk)

    def test_discard_deletes_the_row(self):
        draft = get_or_create_product_draft(self.store, self.user)
        discard_product_draft(draft)
        self.assertFalse(Product.objects.filter(pk=draft.pk).exists())

    def test_cleanup_removes_only_stale_drafts_not_recent_ones(self):
        # sku/slug باید متفاوت باشند — دو پیش‌نویسِ هم‌زمان با sku="" در یک
        # Store به قیدِ یکتاییِ (store, sku) برخورد می‌کنند (به‌عمد؛ نگاه کنید
        # به مستندِ ``get_or_create_product_draft``)؛ این‌جا صراحتاً دو
        # پیش‌نویسِ نیمه‌پرشده‌ی متفاوت شبیه‌سازی می‌شود، نه دو پیش‌نویسِ کاملاً خالی.
        stale = Product.objects.create(
            store=self.store, vendor=self.vendor, category=None, price=Decimal("0"),
            sku="STALE-DRAFT-1", slug="stale-draft-1", is_draft_placeholder=True,
        )
        Product.objects.filter(pk=stale.pk).update(
            updated_at=timezone.now() - timezone.timedelta(hours=100),
        )
        fresh = Product.objects.create(
            store=self.store, vendor=self.vendor, category=None, price=Decimal("0"),
            sku="FRESH-DRAFT-1", slug="fresh-draft-1", is_draft_placeholder=True,
        )

        result = cleanup_stale_product_drafts(older_than_hours=48)

        self.assertEqual(result.deleted_count, 1)
        self.assertIn(stale.pk, result.deleted_ids)
        self.assertFalse(Product.objects.filter(pk=stale.pk).exists())
        self.assertTrue(Product.objects.filter(pk=fresh.pk).exists())

    def test_cleanup_is_idempotent(self):
        stale = Product.objects.create(
            store=self.store, vendor=self.vendor, category=None, price=Decimal("0"),
            is_draft_placeholder=True,
        )
        Product.objects.filter(pk=stale.pk).update(
            updated_at=timezone.now() - timezone.timedelta(hours=100),
        )
        first = cleanup_stale_product_drafts(older_than_hours=48)
        second = cleanup_stale_product_drafts(older_than_hours=48)
        self.assertEqual(first.deleted_count, 1)
        self.assertEqual(second.deleted_count, 0)

    def test_cleanup_does_not_touch_real_finalized_products(self):
        category = Category.objects.create(store=self.store, name="c", slug="draftsvc-cat")
        real = Product.objects.create(
            store=self.store, vendor=self.vendor, category=category, name="واقعی",
            slug="draftsvc-real", sku="DRAFTSVC-REAL1", price=Decimal("1000"),
        )
        Product.objects.filter(pk=real.pk).update(
            updated_at=timezone.now() - timezone.timedelta(hours=1000),
        )
        result = cleanup_stale_product_drafts(older_than_hours=48)
        self.assertEqual(result.deleted_count, 0)
        self.assertTrue(Product.objects.filter(pk=real.pk).exists())


class ProductDraftEntitlementGateTests(TestCase):
    """گیتِ سقفِ اشتراک باید هنوز هم فقط یک‌بار — هنگامِ ساختِ *تازه‌ی* پیش‌نویس —
    اجرا شود، نه هنگامِ هر ازسرگیری، و نه دوباره هنگامِ ذخیره‌ی نهایی."""

    def setUp(self):
        from apps.subscriptions import entitlements as ekeys
        from apps.subscriptions.models import EntitlementDefinition, Plan, PlanEntitlement, PlanVersion
        from apps.subscriptions.services import entitlement_service as ent
        from apps.subscriptions.services import subscription_service as svc

        ent.clear_entitlement_cache()
        self.store = Store.objects.create(
            name="فروشگاه محدود", slug="draftlimit", admin_subdomain="draftlimit",
            status=Store.Status.ACTIVE,
        )
        self.vendor = Vendor.objects.create(store=self.store, name="فروشنده", slug="draftlimit-shop")
        plan = Plan.objects.create(code="plan-draftlimit", name="draftlimit")
        version = PlanVersion.objects.create(plan=plan, version_number=1, status=PlanVersion.Status.PUBLISHED)
        definition = EntitlementDefinition.objects.get(key=ekeys.CATALOG_PRODUCTS)
        PlanEntitlement.objects.create(
            plan_version=version, entitlement=definition, is_enabled=True, integer_limit=0,
        )
        sub = svc.create_subscription(self.store, version)
        svc.activate_subscription(sub)
        ent.clear_entitlement_cache()
        self.user = User.objects.create_user(username="draftlimit-user", password="pass12345", is_staff=True)

    def test_draft_creation_blocked_at_plan_limit(self):
        from apps.subscriptions.services.enforcement import UsageLimitExceeded

        with self.assertRaises(UsageLimitExceeded):
            get_or_create_product_draft(self.store, self.user)
        self.assertEqual(Product.objects.filter(store=self.store).count(), 0)

    def test_add_product_view_redirects_to_list_with_error_when_blocked(self):
        StoreMembership.objects.create(
            store=self.store, user=self.user, role=StoreMembership.Role.OWNER,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )
        with override_settings(ALLOWED_HOSTS=["draftlimit.rastisi.localhost", "testserver"]):
            client = Client(HTTP_HOST="draftlimit.rastisi.localhost")
            client.login(username="draftlimit-user", password="pass12345")
            response = client.get(reverse("dashboard:product-add"), follow=True)
            self.assertRedirects(response, reverse("dashboard:product-list"))
            self.assertEqual(Product.objects.filter(store=self.store).count(), 0)


class ResolveCategorySchemaNoneSafetyTests(TestCase):
    """اثرِ جانبیِ لازمِ nullableشدنِ ``Product.category``: توابعِ مشترکی که
    قبلاً هرگز ``category=None`` نمی‌دیدند اکنون باید آن را با ظرافت
    مدیریت کنند — نگاه کنید به بخشِ ۸ گزارشِ ریشه‌ای."""

    def setUp(self):
        self.store = Store.objects.create(name="فروشگاه", slug="schema-none", admin_subdomain="schema-none")
        self.vendor = Vendor.objects.create(store=self.store, name="فروشنده", slug="schema-none-shop")

    def test_resolve_category_schema_returns_empty_list_for_none(self):
        from apps.catalog.services.category_schema_service import resolve_category_schema

        self.assertEqual(resolve_category_schema(None), [])

    def test_orphaned_product_attribute_values_safe_for_categoryless_draft(self):
        from apps.catalog.services.category_schema_service import orphaned_product_attribute_values

        draft = Product.objects.create(
            store=self.store, vendor=self.vendor, category=None, price=Decimal("0"),
            is_draft_placeholder=True,
        )
        self.assertEqual(orphaned_product_attribute_values(draft).count(), 0)


class DraftExcludedFromStorefrontTests(TestCase):
    """دفاعِ لایه‌ی دوم: حتی اگر status پیش‌نویس به هر دلیلی ACTIVE باشد (مقدارِ
    پیش‌فرضِ مدل)، is_draft_placeholder=True نباید هرگز در فروشگاه ظاهر شود."""

    def setUp(self):
        self.store = Store.objects.create(name="فروشگاه", slug="draft-storefront", admin_subdomain="draft-storefront")
        self.vendor = Vendor.objects.create(store=self.store, name="فروشنده", slug="draft-storefront-shop")
        self.category = Category.objects.create(store=self.store, name="دسته", slug="draft-storefront-cat")

    def test_storefront_visible_products_excludes_draft_even_with_active_status(self):
        from apps.catalog.services.product_publish_service import storefront_visible_products

        draft = Product.objects.create(
            store=self.store, vendor=self.vendor, category=self.category, name="پیش‌نویس",
            slug="draft-storefront-item", sku="DRAFT-SF-1", price=Decimal("1000"),
            status=Product.Status.ACTIVE, is_draft_placeholder=True,
        )
        self.assertNotIn(draft, storefront_visible_products(self.store))
