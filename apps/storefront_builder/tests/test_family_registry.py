"""Family/Preset Registry — چکپوینتِ اول از پیاده‌سازیِ پنج خانواده‌ی
قالب (تصمیمِ مالک Q-01/Q-02، docs/template-references/live-audit/10_OWNER_DECISION_LOG.md).

الزامِ غیرقابلِ‌مذاکره‌یِ این چکپوینت: فروشگاهی که هرگز Family انتخاب
نکرده (``family_slug=None``، پیش‌فرض) باید دقیقاً همان صفحه‌ی اصلیِ
قبلی را ببیند — بدون تغییرِ ظاهری، بدونِ استثنا."""

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.storefront_builder import family_registry, preset_registry
from apps.storefront_builder.services import layout_service as svc
from apps.stores.models import Store, StoreDomain, StoreMembership

User = get_user_model()


def _akhlaghi():
    return Store.objects.get(slug="akhlaghi")


class FamilyRegistryTests(TestCase):
    def test_modern_fashion_registered(self):
        family = family_registry.get_family("modern_fashion")
        self.assertIsNotNone(family)
        self.assertEqual(family.product_card_variant, "catalog/partials/product_cards/fashion_portrait_gallery.html")

    def test_unknown_family_returns_none(self):
        self.assertIsNone(family_registry.get_family("not-a-real-family"))

    def test_none_slug_returns_none(self):
        self.assertIsNone(family_registry.get_family(None))

    def test_list_families_includes_modern_fashion(self):
        slugs = [f.slug for f in family_registry.list_families()]
        self.assertIn("modern_fashion", slugs)

    def test_default_preset_is_registered_and_belongs_to_family(self):
        family = family_registry.get_family("modern_fashion")
        preset = preset_registry.get_preset(family.default_preset_slug)
        self.assertIsNotNone(preset)
        self.assertEqual(preset.family_slug, "modern_fashion")

    def test_default_preset_palette_is_a_real_registered_palette(self):
        from apps.storefront_builder import appearance_registry

        preset = preset_registry.get_preset("modern_fashion_default")
        self.assertIsNotNone(appearance_registry.get_palette(preset.default_palette_slug))


class ValidateAppearanceConfigFamilyTests(TestCase):
    def test_family_slug_none_by_default(self):
        cleaned = svc.validate_appearance_config({})
        self.assertIsNone(cleaned["family_slug"])
        self.assertIsNone(cleaned["preset_slug"])

    def test_unknown_family_rejected(self):
        with self.assertRaises(svc.AppearanceConfigValidationError):
            svc.validate_appearance_config({"family_slug": "not-a-real-family"})

    def test_unknown_preset_rejected(self):
        with self.assertRaises(svc.AppearanceConfigValidationError):
            svc.validate_appearance_config({"family_slug": "modern_fashion", "preset_slug": "not-a-real-preset"})

    def test_preset_from_different_family_rejected(self):
        # هرچند امروز فقط یک Family/Preset ثبت شده، خودِ قانون باید مستقل
        # از تعداد Familyهای فعلی درست کار کند — با ثبت موقتِ یک Family/
        # Preset دومِ آزمایشی، امکانِ کراس-فمیلی را واقعاً تست می‌کنیم.
        family_registry.register_family(family_registry.FamilyDefinition(
            slug="_test_other_family", name_fa="آزمایشی", description_fa="",
            header_variant="x", hero_variant="x", category_variant="x", footer_variant="x",
            product_card_variant="x", product_page_variant="x", default_preset_slug="_test_other_preset",
        ))
        preset_registry.register_preset(preset_registry.PresetDefinition(
            slug="_test_other_preset", family_slug="_test_other_family", name_fa="", description_fa="",
            font="Vazirmatn", radius=10, button_radius=10, button_style="filled", density="normal",
            motion="subtle", type_scale="normal", card_shadow="none", card_hover="none", hero_style="wide",
            default_palette_slug="mono",
        ))
        try:
            with self.assertRaises(svc.AppearanceConfigValidationError):
                svc.validate_appearance_config({
                    "family_slug": "modern_fashion", "preset_slug": "_test_other_preset",
                })
        finally:
            del family_registry.FAMILY_REGISTRY["_test_other_family"]
            del preset_registry.PRESET_REGISTRY["_test_other_preset"]

    def test_preset_without_family_rejected(self):
        with self.assertRaises(svc.AppearanceConfigValidationError):
            svc.validate_appearance_config({"preset_slug": "modern_fashion_default"})

    def test_valid_family_and_matching_preset_accepted(self):
        cleaned = svc.validate_appearance_config({
            "family_slug": "modern_fashion", "preset_slug": "modern_fashion_default",
        })
        self.assertEqual(cleaned["family_slug"], "modern_fashion")
        self.assertEqual(cleaned["preset_slug"], "modern_fashion_default")


HOST = "sfb-family-test.rastisi.localhost"


class FamilySwitchViewTests(TestCase):
    """رفتارِ POSTِ سوییچِ Family/Template — انحصارِ متقابل (تصمیمِ مالک):
    انتخابِ صریحِ یکی، دیگری را به‌طور خودکار پیش‌فرض می‌کند."""

    def setUp(self):
        cache.clear()
        self.store = _akhlaghi()
        self.store.admin_subdomain = HOST.split(".")[0]
        self.store.save(update_fields=["admin_subdomain"])
        self.staff = User.objects.create_user(username="family_owner", password="pass12345", is_staff=True)
        StoreMembership.objects.create(
            store=self.store, user=self.staff, role=StoreMembership.Role.OWNER,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )
        self.client = Client(HTTP_HOST=HOST)
        self.client.login(username="family_owner", password="pass12345")

    def test_selecting_family_resets_template_and_applies_preset_defaults(self):
        resp = self.client.post(reverse("dashboard:storefront-builder-appearance"), {
            "family_slug": "modern_fashion",
        })
        self.assertEqual(resp.status_code, 302)
        draft = svc.get_or_create_draft(self.store)
        config = draft.effective_appearance_config()
        self.assertEqual(config["family_slug"], "modern_fashion")
        self.assertEqual(config["preset_slug"], "modern_fashion_default")
        self.assertEqual(config["template_slug"], "modern")  # پیش‌فرض/بدون‌اثر — Family فعال است
        self.assertEqual(config["radius"], 16)  # از Preset، نه از Templateِ «modern» (18)
        self.assertEqual(config["palette_slug"], "amber")

    def test_selecting_legacy_template_after_family_clears_family(self):
        self.client.post(reverse("dashboard:storefront-builder-appearance"), {"family_slug": "modern_fashion"})
        resp = self.client.post(reverse("dashboard:storefront-builder-appearance"), {
            "template_slug": "boutique", "font": "Tahoma", "radius": "24", "button_radius": "22",
            "density": "relaxed", "motion": "subtle",
        })
        self.assertEqual(resp.status_code, 302)
        draft = svc.get_or_create_draft(self.store)
        config = draft.effective_appearance_config()
        self.assertEqual(config["template_slug"], "boutique")
        self.assertIsNone(config["family_slug"])
        self.assertIsNone(config["preset_slug"])

    def test_explicit_palette_wins_over_preset_default_in_same_submission(self):
        resp = self.client.post(reverse("dashboard:storefront-builder-appearance"), {
            "family_slug": "modern_fashion", "palette_slug": "ocean",
        })
        self.assertEqual(resp.status_code, 302)
        draft = svc.get_or_create_draft(self.store)
        self.assertEqual(draft.effective_appearance_config()["palette_slug"], "ocean")

    def test_preview_family_param_shows_candidate_without_saving(self):
        draft_before = svc.get_or_create_draft(self.store)
        original = dict(draft_before.appearance_config or {})
        resp = self.client.get(reverse("dashboard:storefront-builder-preview"), {"preview_family": "modern_fashion"})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "mf-header")
        draft_after = svc.get_or_create_draft(self.store)
        self.assertEqual(draft_after.appearance_config, original)


@override_settings(ALLOWED_HOSTS=["sfb-family-public.example.com", "testserver", HOST])
class FamilyPublicRenderingTests(TestCase):
    """رندرِ واقعیِ صفحه‌ی اصلیِ عمومی — الزامِ اصلیِ Gate 3: فروشگاهِ
    بدونِ Family باید دقیقاً بدون تغییر بماند؛ فروشگاهِ با Family باید
    واقعاً DOMِ اختصاصی ببیند."""

    def setUp(self):
        cache.clear()
        self.store = _akhlaghi()
        StoreDomain.objects.create(
            store=self.store, hostname="sfb-family-public.example.com", is_primary=True,
            verification_status=StoreDomain.VerificationStatus.VERIFIED, verified_at=timezone.now(),
        )

    def test_no_family_selected_renders_legacy_header_unchanged(self):
        svc.get_or_create_draft(self.store)
        svc.publish(self.store)
        resp = self.client.get(reverse("catalog:home"), HTTP_HOST="sfb-family-public.example.com")
        self.assertEqual(resp.status_code, 200)
        self.assertNotContains(resp, "mf-header")

    def test_family_selected_renders_family_header_and_card(self):
        draft = svc.get_or_create_draft(self.store)
        draft.appearance_config = svc.validate_appearance_config({
            "family_slug": "modern_fashion", "preset_slug": "modern_fashion_default",
        })
        draft.save(update_fields=["appearance_config"])
        svc.publish(self.store)
        resp = self.client.get(reverse("catalog:home"), HTTP_HOST="sfb-family-public.example.com")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "mf-header")
        self.assertContains(resp, 'data-sfb-family="modern_fashion"')
