"""A1 — پوسته صفحه مشترک (Header/Footer) بین Builder Preview و Storefront
عمومی. طبق سند معماری بخش ۸: هر دو مسیر باید از یک partial واحد
(``storefront_builder/partials/page_shell_header.html`` و
``page_shell_footer.html``) استفاده کنند — نه دو تمپلیت مستقل کپی‌شده."""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.conf import settings
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.catalog.models import Category, Product, Vendor
from apps.catalog.services import collection_service
from apps.content.models import Menu, MenuItem, SocialLink
from apps.storefront_builder.services import layout_service as svc
from apps.stores.models import Store, StoreDomain, StoreMembership

User = get_user_model()

ADMIN_HOST = "sfb-shell-test.rastisi.localhost"
PUBLIC_HOST = "sfb-shell-public.example.com"


def _akhlaghi():
    return Store.objects.get(slug="akhlaghi")


@override_settings(ALLOWED_HOSTS=[ADMIN_HOST, PUBLIC_HOST, "testserver"])
class SharedPageShellTests(TestCase):
    """هر دو سناریو (Preview staff-only، Storefront عمومی) روی یک Store واحد."""

    def setUp(self):
        cache.clear()
        self.store = _akhlaghi()
        self.store.admin_subdomain = ADMIN_HOST.split(".")[0]
        self.store.save(update_fields=["admin_subdomain"])
        StoreDomain.objects.create(
            store=self.store, hostname=PUBLIC_HOST, is_primary=True,
            verification_status=StoreDomain.VerificationStatus.VERIFIED, verified_at=timezone.now(),
        )
        self.staff = User.objects.create_user(username="sfb_shell_owner", password="pass12345", is_staff=True)
        StoreMembership.objects.create(
            store=self.store, user=self.staff, role=StoreMembership.Role.OWNER,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )
        self.admin_client = Client(HTTP_HOST=ADMIN_HOST)
        self.admin_client.login(username="sfb_shell_owner", password="pass12345")
        self.public_client = Client(HTTP_HOST=PUBLIC_HOST)

    def _preview(self):
        return self.admin_client.get(reverse("dashboard:storefront-builder-preview"))

    def _storefront(self):
        return self.public_client.get(reverse("catalog:home"))

    # 1. یک partial مشترک برای هدر توسط هر دو مسیر استفاده می‌شود.
    def test_shared_header_partial_used_by_both_preview_and_storefront(self):
        svc.get_or_create_draft(self.store)
        svc.publish(self.store)
        preview_resp = self._preview()
        storefront_resp = self._storefront()
        preview_templates = [t.name for t in preview_resp.templates if t.name]
        storefront_templates = [t.name for t in storefront_resp.templates if t.name]
        self.assertIn("storefront_builder/partials/page_shell_header.html", preview_templates)
        self.assertIn("storefront_builder/partials/page_shell_header.html", storefront_templates)

    # 2. یک partial مشترک برای فوتر توسط هر دو مسیر استفاده می‌شود.
    def test_shared_footer_partial_used_by_both_preview_and_storefront(self):
        svc.get_or_create_draft(self.store)
        svc.publish(self.store)
        preview_resp = self._preview()
        storefront_resp = self._storefront()
        preview_templates = [t.name for t in preview_resp.templates if t.name]
        storefront_templates = [t.name for t in storefront_resp.templates if t.name]
        self.assertIn("storefront_builder/partials/page_shell_footer.html", preview_templates)
        self.assertIn("storefront_builder/partials/page_shell_footer.html", storefront_templates)

    # 3. همان پیکربندی هدر/فوتر، خروجی قابل‌مشاهده یکسان تولید می‌کند.
    def test_same_header_footer_config_produces_equivalent_visible_output(self):
        draft = svc.get_or_create_draft(self.store)
        draft.header_config = {
            "show_search": True, "show_account": False, "show_cart": True,
            "show_wishlist": False, "sticky": True, "announcement_enabled": True,
            "announcement_text": "پیام مشترک آزمایشی",
        }
        draft.footer_config = {
            "show_about": True, "show_contact": False, "show_quick_links": False,
            "show_categories": True, "show_social": False, "show_trust_badges": False,
            "show_payment_logos": False, "show_newsletter": False, "show_copyright": True,
        }
        draft.save(update_fields=["header_config", "footer_config"])
        svc.publish(self.store)

        preview_body = self._preview().content.decode()
        storefront_body = self._storefront().content.decode()

        # پیام نوار اعلان در هر دو سمت دیده می‌شود (announcement_enabled=True).
        self.assertIn("پیام مشترک آزمایشی", preview_body)
        self.assertIn("پیام مشترک آزمایشی", storefront_body)
        # sticky=True در هر دو سمت همان کلاس را تولید می‌کند.
        self.assertIn("sfb-sticky", preview_body)
        self.assertIn("sfb-sticky", storefront_body)
        # show_account=False: دکمه ورود در هیچ‌کدام لینک واقعی حساب کاربری ندارد.
        self.assertNotIn('href="/accounts/', preview_body)
        # show_copyright=True: هر دو کپی‌رایت را نشان می‌دهند.
        self.assertIn('class="copy"', preview_body)
        self.assertIn('class="copy"', storefront_body)
        # show_contact=False: هیچ‌کدام بخش تماس را نشان نمی‌دهند.
        self.assertNotIn("تماس با ما", preview_body)
        self.assertNotIn("تماس با ما", storefront_body)

    # 4. تغییرات Draft در Preview دیده می‌شوند.
    def test_draft_header_changes_appear_in_preview(self):
        draft = svc.get_or_create_draft(self.store)
        draft.header_config = {**(draft.header_config or {}), "announcement_enabled": True, "announcement_text": "DRAFT-ONLY-MARKER"}
        draft.save(update_fields=["header_config"])
        body = self._preview().content.decode()
        self.assertIn("DRAFT-ONLY-MARKER", body)

    # 5. تغییرات Draft پیش از Publish در Storefront عمومی دیده نمی‌شوند.
    def test_draft_header_changes_do_not_appear_publicly_before_publish(self):
        svc.get_or_create_draft(self.store)
        svc.publish(self.store)  # یک published version معتبر می‌سازیم تا صفحه عمومی فعال شود.
        draft = svc.get_or_create_draft(self.store)
        draft.header_config = {**(draft.header_config or {}), "announcement_enabled": True, "announcement_text": "DRAFT-ONLY-MARKER-2"}
        draft.save(update_fields=["header_config"])
        body = self._storefront().content.decode()
        self.assertNotIn("DRAFT-ONLY-MARKER-2", body)

    # 6. پس از Publish، تغییرات در Storefront عمومی دیده می‌شوند.
    def test_published_header_changes_appear_publicly_after_publish(self):
        draft = svc.get_or_create_draft(self.store)
        draft.header_config = {**(draft.header_config or {}), "announcement_enabled": True, "announcement_text": "PUBLISHED-MARKER"}
        draft.save(update_fields=["header_config"])
        svc.publish(self.store)
        body = self._storefront().content.decode()
        self.assertIn("PUBLISHED-MARKER", body)

    # 7. لینک‌های واقعی storefront زنده دست‌نخورده باقی می‌مانند.
    def test_live_storefront_links_remain_real(self):
        svc.get_or_create_draft(self.store)
        svc.publish(self.store)
        body = self._storefront().content.decode()
        self.assertIn(reverse("cart:detail"), body)
        self.assertIn(reverse("customers:wishlist"), body)
        self.assertIn(f'action="{reverse("catalog:product-list")}"', body)

    # 8. تفاوت‌های عمدی preview-safe (غیرواقعی/غیرفعال) حفظ می‌شوند.
    def test_preview_keeps_intentional_non_mutating_placeholders(self):
        svc.get_or_create_draft(self.store)
        body = self._preview().content.decode()
        self.assertNotIn(reverse("cart:detail"), body)
        self.assertNotIn(reverse("customers:wishlist"), body)
        self.assertIn('onsubmit="return false"', body)

    def test_preview_never_shows_real_cart_or_wishlist_count(self):
        svc.get_or_create_draft(self.store)
        body = self._preview().content.decode()
        self.assertNotIn('id="cart-count"', body)
        self.assertNotIn('id="wishlist-count"', body)

    # Phase 4 — الزامِ صریحِ کار: همان هدر/فوترِ همان نسخه‌ی منتشرشده باید
    # روی هر شش نوعِ صفحه‌ی عمومی دیده شود (مشکلِ اصلیِ معماریِ خانواده‌های
    # قدیمی که V2 باید غیرممکنش کند).
    def test_all_six_public_page_types_render_identical_header_footer(self):
        vendor = Vendor.objects.create(store=self.store, name="فروشنده شش‌صفحه", slug="vendor-6page")
        category = Category.objects.create(store=self.store, name="دسته شش‌صفحه", slug="cat-6page", is_active=True)
        product = Product.objects.create(
            store=self.store, vendor=vendor, category=category, name="کالای شش‌صفحه", slug="product-6page",
            sku="SIX-PAGE-1", price=Decimal("10000"), stock=5, status=Product.Status.ACTIVE,
        )
        collection = collection_service.create_collection(self.store, name="کالکشن شش‌صفحه")
        collection_service.add_product(collection, product)

        draft = svc.get_or_create_draft(self.store)
        draft.header_config = svc.validate_header_config({
            "show_cart": True, "announcement_enabled": True,
            "announcement_text": "SIX-PAGE-CONSISTENCY-MARKER",
            "responsive": {"announcement_enabled": {"hide_on_tablet": False, "hide_on_mobile": True}},
        })
        draft.footer_config = svc.validate_footer_config({"show_copyright": True})
        draft.save(update_fields=["header_config", "footer_config"])
        svc.publish(self.store)

        routes = [
            reverse("catalog:home"),
            reverse("catalog:product-detail", args=[product.slug]),
            reverse("catalog:product-list"),
            reverse("catalog:collection-detail", args=[collection.slug]),
            reverse("catalog:product-list") + "?q=کالای",
            reverse("cart:detail"),
        ]
        for url in routes:
            body = self.public_client.get(url).content.decode()
            self.assertIn("SIX-PAGE-CONSISTENCY-MARKER", body, f"missing header marker on {url}")
            self.assertIn("data-shell-hide-mobile", body, f"missing responsive attribute on {url}")
            self.assertIn('class="copy"', body, f"missing footer on {url}")


    # Phase 3.10 — دسترسی مستقیم از صفحه اصلی فروشگاه به پنل مدیریت همان Store.
    def test_homepage_has_store_admin_shortcut_on_correct_admin_host(self):
        svc.get_or_create_draft(self.store)
        svc.publish(self.store)
        body = self._storefront().content.decode()
        expected = (
            f"http://{self.store.admin_subdomain}."
            f"{settings.RASTISI_ADMIN_DOMAIN_SUFFIX}/admin-portal/"
        )
        self.assertIn('class="store-admin-shortcut"', body)
        self.assertIn("پنل مدیریت", body)
        self.assertIn(f'href="{expected}"', body)

    def test_builder_home_preview_has_admin_shortcut(self):
        svc.get_or_create_draft(self.store)
        body = self._preview().content.decode()
        self.assertIn('class="store-admin-shortcut"', body)
        self.assertIn('target="_top"', body)

    def test_admin_shortcut_is_homepage_only(self):
        svc.get_or_create_draft(self.store)
        svc.publish(self.store)
        body = self.public_client.get(reverse("catalog:product-list")).content.decode()
        self.assertNotIn('class="store-admin-shortcut"', body)

    def test_admin_shortcut_preserves_local_non_default_port(self):
        svc.get_or_create_draft(self.store)
        svc.publish(self.store)
        response = self.public_client.get(
            reverse("catalog:home"),
            HTTP_HOST=f"{PUBLIC_HOST}:8765",
        )
        expected = (
            f"http://{self.store.admin_subdomain}."
            f"{settings.RASTISI_ADMIN_DOMAIN_SUFFIX}:8765/admin-portal/"
        )
        self.assertContains(response, f'href="{expected}"')

    # Phase 4 — بندهای ۲۱/۲۲: هر شیءِ ارجاع‌شده در هدر/فوتر (SocialLink،
    # Menu/MenuItem) باید در سطحِ کوئریِ رندر هم store-scoped باشد — این
    # سند در ممیزیِ فاز ۴ فقط با خواندنِ کد تأیید شده بود؛ این تست با دو
    # Store واقعی و دو میزبانِ متفاوت آن را اثبات می‌کند.
    def test_social_link_and_menu_never_leak_across_stores(self):
        other_store = Store.objects.create(
            name="فروشگاه دیگرِ پوسته", slug="sfb-shell-other", status=Store.Status.ACTIVE,
        )
        StoreDomain.objects.create(
            store=other_store, hostname="sfb-shell-other-public.example.com", is_primary=True,
            verification_status=StoreDomain.VerificationStatus.VERIFIED, verified_at=timezone.now(),
        )

        SocialLink.objects.create(
            store=self.store, platform=SocialLink.Platform.INSTAGRAM, title="اینستاگرام فروشگاهِ من",
            url="https://instagram.com/store-a", show_in_footer=True,
        )
        SocialLink.objects.create(
            store=other_store, platform=SocialLink.Platform.TELEGRAM, title="تلگرامِ فروشگاهِ دیگر",
            url="https://t.me/store-b-secret", show_in_footer=True,
        )
        menu_a = Menu.objects.create(store=self.store, title="منوی من", location=Menu.Location.HEADER)
        MenuItem.objects.create(
            menu=menu_a, title="STORE-A-MENU-ITEM",
            destination_type="external", destination_external_url="https://example.com/a",
        )
        menu_b = Menu.objects.create(store=other_store, title="منوی دیگر", location=Menu.Location.HEADER)
        MenuItem.objects.create(
            menu=menu_b, title="STORE-B-SECRET-MENU-ITEM",
            destination_type="external", destination_external_url="https://example.com/b",
        )

        draft = svc.get_or_create_draft(self.store)
        draft.header_config = svc.validate_header_config({"show_cart": True})
        draft.footer_config = svc.validate_footer_config({"show_social": True, "show_copyright": True})
        draft.save(update_fields=["header_config", "footer_config"])
        svc.publish(self.store)

        body = self.public_client.get(reverse("catalog:home")).content.decode()
        self.assertIn("store-a", body)
        self.assertIn("STORE-A-MENU-ITEM", body)
        self.assertNotIn("store-b-secret", body)
        self.assertNotIn("STORE-B-SECRET-MENU-ITEM", body)
