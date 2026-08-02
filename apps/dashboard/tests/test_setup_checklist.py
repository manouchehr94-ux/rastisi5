"""تست‌های چک‌لیست راه‌اندازی فروشگاه — apps.dashboard.services.checklist_service."""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.catalog.models import (
    Attribute,
    Brand,
    Category,
    IndustryTemplate,
    Product,
    ProductImage,
    ProductVariant,
    StoreIndustryInstallation,
    Vendor,
)
from apps.core.models import ShopSettings
from apps.dashboard.services.checklist_service import build_setup_checklist
from apps.orders.models import PaymentGatewayConfig, ShippingMethod, TaxClass, TaxRate
from apps.stores.models import Store, StoreDomain, StoreMembership

User = get_user_model()


def _grant_akhlaghi_membership(user):
    StoreMembership.objects.create(
        store=Store.objects.get(slug="akhlaghi"), user=user,
        role=StoreMembership.Role.OWNER, status=StoreMembership.MembershipStatus.ACTIVE,
        accepted_at=timezone.now(),
    )


class BuildSetupChecklistTests(TestCase):
    """هر مرحله باید مستقیماً از داده‌ی واقعی تشخیص داده شود، نه یک پرچمِ ذخیره‌شده."""

    def setUp(self):
        self.store = Store.objects.create(name="New Shop", slug="new-shop", status=Store.Status.ACTIVE)
        self.request = RequestFactory().get("/")

    def test_brand_new_store_has_nothing_complete(self):
        result = build_setup_checklist(self.store, self.request)
        self.assertEqual(result["completed_count"], 0)
        self.assertEqual(result["total_count"], 20)
        self.assertEqual(result["percent"], 0)
        self.assertFalse(result["all_complete"])

    def test_step_order_matches_catalog_dependency_chain(self):
        """اولین کالا هرگز نباید پیش از پیش‌نیازهایش (گروه/دسته/برند/ویژگی) ظاهر شود؛
        زنجیره‌ی اصلیِ ۱۲مرحله‌ای دقیقاً طبقِ ترتیبِ الزامیِ درخواست است."""
        result = build_setup_checklist(self.store, self.request)
        keys = [step["key"] for step in result["steps"]]
        expected_prefix = [
            "industry", "industry_template", "product_groups", "product_categories",
            "brands", "attributes", "first_product", "product_images", "variants",
            "inventory", "shipping", "publish",
        ]
        self.assertEqual(keys[: len(expected_prefix)], expected_prefix)

    def test_first_steps_are_unlocked_but_later_chain_steps_are_locked(self):
        """قفل صرفاً بصری است — همه‌ی مراحل همیشه قابل‌کلیک‌اند، اما مراحلِ
        بعدیِ زنجیره‌ی کاتالوگ تا تکمیل‌نشدنِ پیش‌نیازها «قفل» نشان داده می‌شوند."""
        result = build_setup_checklist(self.store, self.request)
        steps_by_key = {s["key"]: s for s in result["steps"]}
        self.assertTrue(steps_by_key["industry"]["is_unlocked"])
        self.assertFalse(steps_by_key["product_groups"]["is_unlocked"])
        self.assertFalse(steps_by_key["publish"]["is_unlocked"])
        # مراحلِ تکمیلیِ خارج از زنجیره همیشه باز هستند، حتی وقتی زنجیره ناتمام است.
        self.assertTrue(steps_by_key["store_info"]["is_unlocked"])

    def test_chain_step_unlocks_once_its_prerequisites_are_done(self):
        self.store.onboarding_stage = Store.OnboardingStage.BRANDING  # صنف رد/تصمیم‌گیری شده
        self.store.save(update_fields=["onboarding_stage"])
        Category.objects.create(store=self.store, name="گروه", slug="chk-unlock-group")
        result = build_setup_checklist(self.store, self.request)
        steps_by_key = {s["key"]: s for s in result["steps"]}
        self.assertTrue(steps_by_key["product_groups"]["is_complete"])
        self.assertTrue(steps_by_key["product_categories"]["is_unlocked"])

    def test_locked_steps_explain_why_via_locked_reason(self):
        """کاربر باید همیشه بداند «چرا» یک مرحله قفل است، نه فقط اینکه قفل است."""
        result = build_setup_checklist(self.store, self.request)
        steps_by_key = {s["key"]: s for s in result["steps"]}
        self.assertEqual(steps_by_key["industry"]["locked_reason"], "")
        self.assertIn("انتخاب صنف", steps_by_key["product_groups"]["locked_reason"])
        self.assertIn("انتخاب صنف", steps_by_key["publish"]["locked_reason"])

    def test_locked_reason_points_to_the_nearest_unfinished_prerequisite(self):
        """دلیلِ قفل باید نزدیک‌ترین مرحله‌ی ناتمام را نام ببرد، نه همیشه اولین مرحله‌ی زنجیره را."""
        self.store.onboarding_stage = Store.OnboardingStage.BRANDING
        self.store.save(update_fields=["onboarding_stage"])
        Category.objects.create(store=self.store, name="گروه", slug="chk-reason-group")
        result = build_setup_checklist(self.store, self.request)
        steps_by_key = {s["key"]: s for s in result["steps"]}
        self.assertIn("ایجاد دسته‌بندی‌ها", steps_by_key["brands"]["locked_reason"])

    def test_exactly_one_unlocked_incomplete_step_is_marked_next(self):
        """کاربر باید همیشه بداند «قدمِ بعدی» دقیقاً کدام است."""
        result = build_setup_checklist(self.store, self.request)
        next_steps = [s["key"] for s in result["steps"] if s["is_next"]]
        self.assertEqual(next_steps, ["industry"])

    def test_next_step_advances_once_current_step_completes(self):
        self.store.onboarding_stage = Store.OnboardingStage.BRANDING
        self.store.save(update_fields=["onboarding_stage"])
        result = build_setup_checklist(self.store, self.request)
        next_steps = [s["key"] for s in result["steps"] if s["is_next"]]
        self.assertEqual(next_steps, ["product_groups"])

    def test_store_information_step_detects_description(self):
        shop = ShopSettings.objects.create(store=self.store, description="فروشگاهِ لباسِ آنلاین")
        result = build_setup_checklist(self.store, self.request)
        step = next(s for s in result["steps"] if s["key"] == "store_info")
        self.assertTrue(step["is_complete"])

    def test_industry_step_detects_installation(self):
        template = IndustryTemplate.objects.create(
            slug="clothing", name="پوشاک", version=1, readiness=IndustryTemplate.Readiness.PRODUCTION_READY,
        )
        StoreIndustryInstallation.objects.create(
            store=self.store, industry_template=template, installed_version=1,
            status=StoreIndustryInstallation.Status.COMPLETED,
        )
        result = build_setup_checklist(self.store, self.request)
        step = next(s for s in result["steps"] if s["key"] == "industry")
        self.assertTrue(step["is_complete"])

    def test_contact_step_detects_phone_or_email(self):
        ShopSettings.objects.create(store=self.store, contact_phone="09121234567")
        result = build_setup_checklist(self.store, self.request)
        step = next(s for s in result["steps"] if s["key"] == "contact")
        self.assertTrue(step["is_complete"])

    def test_theme_step_false_when_colors_are_default(self):
        ShopSettings.objects.create(store=self.store)
        result = build_setup_checklist(self.store, self.request)
        step = next(s for s in result["steps"] if s["key"] == "theme")
        self.assertFalse(step["is_complete"])

    def test_theme_step_true_once_a_color_changed(self):
        ShopSettings.objects.create(store=self.store, primary_color="#111111")
        result = build_setup_checklist(self.store, self.request)
        step = next(s for s in result["steps"] if s["key"] == "theme")
        self.assertTrue(step["is_complete"])

    def test_product_groups_step_detects_top_level_category(self):
        Category.objects.create(store=self.store, name="پوشاک", slug="clothing-group")
        result = build_setup_checklist(self.store, self.request)
        step = next(s for s in result["steps"] if s["key"] == "product_groups")
        self.assertTrue(step["is_complete"])

    def test_product_categories_step_requires_subcategory_not_just_a_group(self):
        main = Category.objects.create(store=self.store, name="پوشاک", slug="clothing-main")
        result = build_setup_checklist(self.store, self.request)
        step = next(s for s in result["steps"] if s["key"] == "product_categories")
        self.assertFalse(step["is_complete"])

        Category.objects.create(store=self.store, name="تیشرت", slug="clothing-sub", parent=main)
        result = build_setup_checklist(self.store, self.request)
        step = next(s for s in result["steps"] if s["key"] == "product_categories")
        self.assertTrue(step["is_complete"])

    def test_first_category_and_product_steps(self):
        main = Category.objects.create(store=self.store, name="پوشاک", slug="clothing")
        sub = Category.objects.create(store=self.store, name="تیشرت", slug="clothing-sub2", parent=main)
        vendor = Vendor.objects.create(store=self.store, name="فروشگاه", slug="vendor-checklist")
        Product.objects.create(
            store=self.store, vendor=vendor, category=sub, name="تیشرت", slug="tshirt",
            sku="SKU-CHK1", price=Decimal("100000"),
        )
        result = build_setup_checklist(self.store, self.request)
        prod_step = next(s for s in result["steps"] if s["key"] == "first_product")
        self.assertTrue(prod_step["is_complete"])

    def test_industry_template_step_completes_when_industry_skipped(self):
        """رد کردن مرحله‌ی صنف در ویزارد یعنی نصب قالب اساساً منتفی است — نه ناتمام."""
        self.store.onboarding_stage = Store.OnboardingStage.BRANDING
        self.store.save(update_fields=["onboarding_stage"])
        result = build_setup_checklist(self.store, self.request)
        industry_step = next(s for s in result["steps"] if s["key"] == "industry")
        template_step = next(s for s in result["steps"] if s["key"] == "industry_template")
        self.assertTrue(industry_step["is_complete"])
        self.assertTrue(template_step["is_complete"])

    def test_industry_template_step_completes_when_actually_installed(self):
        template = IndustryTemplate.objects.create(
            slug="home", name="خانه و آشپزخانه", version=1, readiness=IndustryTemplate.Readiness.PRODUCTION_READY,
        )
        StoreIndustryInstallation.objects.create(
            store=self.store, industry_template=template, installed_version=1,
            status=StoreIndustryInstallation.Status.COMPLETED,
        )
        result = build_setup_checklist(self.store, self.request)
        step = next(s for s in result["steps"] if s["key"] == "industry_template")
        self.assertTrue(step["is_complete"])

    def test_attributes_and_brands_steps(self):
        result = build_setup_checklist(self.store, self.request)
        attr_step = next(s for s in result["steps"] if s["key"] == "attributes")
        brand_step = next(s for s in result["steps"] if s["key"] == "brands")
        self.assertFalse(attr_step["is_complete"])
        self.assertFalse(brand_step["is_complete"])

        Attribute.objects.create(store=self.store, label="جنس", code="material-chk")
        Brand.objects.create(store=self.store, name="برند تست", slug="brand-chk")
        result = build_setup_checklist(self.store, self.request)
        attr_step = next(s for s in result["steps"] if s["key"] == "attributes")
        brand_step = next(s for s in result["steps"] if s["key"] == "brands")
        self.assertTrue(attr_step["is_complete"])
        self.assertTrue(brand_step["is_complete"])

    def test_images_variants_inventory_and_publish_steps(self):
        main = Category.objects.create(store=self.store, name="پوشاک", slug="clothing-piv")
        sub = Category.objects.create(store=self.store, name="تیشرت", slug="clothing-sub-piv", parent=main)
        vendor = Vendor.objects.create(store=self.store, name="فروشگاه", slug="vendor-piv")
        product = Product.objects.create(
            store=self.store, vendor=vendor, category=sub, name="تیشرت", slug="tshirt-piv",
            sku="SKU-PIV1", price=Decimal("100000"), stock=0, status=Product.Status.DRAFT,
        )
        result = build_setup_checklist(self.store, self.request)
        for key in ("product_images", "variants", "inventory", "product_publish"):
            step = next(s for s in result["steps"] if s["key"] == key)
            self.assertFalse(step["is_complete"], msg=key)

        ProductImage.objects.create(product=product, image="products/tshirt-piv.jpg")
        ProductVariant.objects.create(
            store=self.store, product=product, attribute="رنگ", value="قرمز", sku="SKU-PIV1-RED",
        )
        product.stock = 5
        product.status = Product.Status.ACTIVE
        product.save(update_fields=["stock", "status"])

        result = build_setup_checklist(self.store, self.request)
        for key in ("product_images", "variants", "inventory", "product_publish"):
            step = next(s for s in result["steps"] if s["key"] == key)
            self.assertTrue(step["is_complete"], msg=key)

    def test_shipping_step(self):
        ShippingMethod.objects.create(store=self.store, name="پست پیشتاز", slug="post", cost=Decimal("50000"))
        result = build_setup_checklist(self.store, self.request)
        step = next(s for s in result["steps"] if s["key"] == "shipping")
        self.assertTrue(step["is_complete"])

    def test_payment_gateway_step_requires_active_config(self):
        PaymentGatewayConfig.objects.create(
            store=self.store, gateway_code=PaymentGatewayConfig.GatewayCode.COD, is_active=False,
        )
        result = build_setup_checklist(self.store, self.request)
        step = next(s for s in result["steps"] if s["key"] == "payment_gateway")
        self.assertFalse(step["is_complete"])

        PaymentGatewayConfig.objects.filter(store=self.store).update(is_active=True)
        result = build_setup_checklist(self.store, self.request)
        step = next(s for s in result["steps"] if s["key"] == "payment_gateway")
        self.assertTrue(step["is_complete"])

    def test_tax_step(self):
        tax_class = TaxClass.objects.create(store=self.store, name="عمومی")
        TaxRate.objects.create(store=self.store, tax_class=tax_class, rate_percent=9)
        result = build_setup_checklist(self.store, self.request)
        step = next(s for s in result["steps"] if s["key"] == "tax")
        self.assertTrue(step["is_complete"])

    def test_custom_domain_step_requires_verified_custom_domain(self):
        StoreDomain.objects.create(
            store=self.store, hostname="shop.example.com",
            domain_type=StoreDomain.DomainType.CUSTOM_DOMAIN,
            verification_status=StoreDomain.VerificationStatus.PENDING,
            verification_requested_at=timezone.now(),
            verification_token="test-token-123",
        )
        result = build_setup_checklist(self.store, self.request)
        step = next(s for s in result["steps"] if s["key"] == "custom_domain")
        self.assertFalse(step["is_complete"])

        StoreDomain.objects.filter(store=self.store).update(
            verification_status=StoreDomain.VerificationStatus.VERIFIED, verified_at=timezone.now(),
        )
        result = build_setup_checklist(self.store, self.request)
        step = next(s for s in result["steps"] if s["key"] == "custom_domain")
        self.assertTrue(step["is_complete"])

    def test_publish_step_detects_onboarding_completed_at(self):
        result = build_setup_checklist(self.store, self.request)
        step = next(s for s in result["steps"] if s["key"] == "publish")
        self.assertFalse(step["is_complete"])

        self.store.onboarding_completed_at = timezone.now()
        self.store.save(update_fields=["onboarding_completed_at"])
        result = build_setup_checklist(self.store, self.request)
        step = next(s for s in result["steps"] if s["key"] == "publish")
        self.assertTrue(step["is_complete"])

    def test_step_urls_never_use_admin_subdomain_host(self):
        result = build_setup_checklist(self.store, self.request)
        for step in result["steps"]:
            self.assertNotIn(self.store.admin_subdomain + ".", step["url"])

    def test_all_complete_flag_true_only_when_every_step_done(self):
        result = build_setup_checklist(self.store, self.request)
        self.assertFalse(result["all_complete"])


class DashboardChecklistWidgetTests(TestCase):
    """چک‌لیست باید در صفحه‌ی داشبورد نمایش داده شود و با پیشرفتِ واقعی به‌روز شود."""

    def setUp(self):
        self.store = Store.objects.get(slug="akhlaghi")
        self.staff = User.objects.create_user(username="09121121099", password="pass12345", is_staff=True)
        _grant_akhlaghi_membership(self.staff)
        self.client.login(username="09121121099", password="pass12345")

    def test_dashboard_shows_checklist_widget(self):
        response = self.client.get(reverse("dashboard:dashboard"))
        self.assertContains(response, "چک‌لیست راه‌اندازی فروشگاه")

    def test_dashboard_shows_success_state_when_all_complete(self):
        from unittest import mock

        with mock.patch(
            "apps.dashboard.services.checklist_service.build_setup_checklist",
            return_value={
                "steps": [], "completed_count": 12, "total_count": 12, "percent": 100, "all_complete": True,
            },
        ):
            response = self.client.get(reverse("dashboard:dashboard"))
        self.assertContains(response, "فروشگاه شما آماده است")
        self.assertNotContains(response, "چک‌لیست راه‌اندازی فروشگاه")
