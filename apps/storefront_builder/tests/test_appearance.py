"""چکپوینتِ نسخه‌بندیِ ظاهر — تنها الزامِ غیرقابلِ‌مذاکره: تغییراتِ ظاهر
باید دقیقاً همان چرخه‌ی Draft/Preview/Publish سکشن‌ها/هدر/فوتر را طی
کنند، نه یک مسیرِ زنده‌ی جدا."""

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.core.models import ShopSettings
from apps.storefront_builder import appearance_registry
from apps.storefront_builder.services import layout_service as svc
from apps.stores.models import Store, StoreDomain, StoreMembership

User = get_user_model()


def _akhlaghi():
    return Store.objects.get(slug="akhlaghi")


class ValidateAppearanceConfigTests(TestCase):
    def test_non_dict_rejected(self):
        with self.assertRaises(svc.AppearanceConfigValidationError):
            svc.validate_appearance_config("not a dict")

    def test_defaults_when_empty(self):
        cleaned = svc.validate_appearance_config({})
        self.assertEqual(cleaned["template_slug"], "modern")
        self.assertIsNone(cleaned["palette_slug"])
        self.assertEqual(cleaned["color_overrides"], {})

    def test_unknown_template_rejected(self):
        with self.assertRaises(svc.AppearanceConfigValidationError):
            svc.validate_appearance_config({"template_slug": "not-a-real-template"})

    def test_unknown_palette_rejected(self):
        with self.assertRaises(svc.AppearanceConfigValidationError):
            svc.validate_appearance_config({"palette_slug": "not-a-real-palette"})

    def test_invalid_hex_color_override_rejected(self):
        with self.assertRaises(svc.AppearanceConfigValidationError):
            svc.validate_appearance_config({"color_overrides": {"primary": "not-a-color"}})

    def test_valid_color_override_accepted(self):
        cleaned = svc.validate_appearance_config({"color_overrides": {"text": "#111111"}})
        self.assertEqual(cleaned["color_overrides"], {"text": "#111111"})

    def test_unknown_color_key_silently_dropped(self):
        cleaned = svc.validate_appearance_config({"color_overrides": {"not_a_real_token": "#111111"}})
        self.assertEqual(cleaned["color_overrides"], {})

    def test_unknown_font_rejected(self):
        with self.assertRaises(svc.AppearanceConfigValidationError):
            svc.validate_appearance_config({"font": "ComicSans"})

    def test_radius_clamped(self):
        cleaned = svc.validate_appearance_config({"radius": 999})
        self.assertEqual(cleaned["radius"], 32)
        cleaned = svc.validate_appearance_config({"radius": -5})
        self.assertEqual(cleaned["radius"], 0)

    def test_invalid_density_rejected(self):
        with self.assertRaises(svc.AppearanceConfigValidationError):
            svc.validate_appearance_config({"density": "super-compact"})

    def test_invalid_motion_rejected(self):
        with self.assertRaises(svc.AppearanceConfigValidationError):
            svc.validate_appearance_config({"motion": "extreme"})


class ResolveColorsTests(TestCase):
    def test_no_palette_uses_default_colors(self):
        colors = appearance_registry.resolve_colors({"palette_slug": None, "color_overrides": {}})
        self.assertEqual(colors, appearance_registry.DEFAULT_COLORS)

    def test_overrides_apply_on_top_of_default(self):
        colors = appearance_registry.resolve_colors({"palette_slug": None, "color_overrides": {"text": "#000000"}})
        self.assertEqual(colors["text"], "#000000")
        self.assertEqual(colors["primary"], appearance_registry.DEFAULT_COLORS["primary"])


class EffectiveAppearanceConfigTests(TestCase):
    def test_fresh_version_has_full_defaults(self):
        store = _akhlaghi()
        draft = svc.get_or_create_draft(store)
        draft.appearance_config = {}
        config = draft.effective_appearance_config()
        self.assertEqual(config["template_slug"], "modern")
        self.assertEqual(config["font"], "Vazirmatn")

    def test_clone_carries_appearance_forward(self):
        """پابلیش → یک Draft جدید (کلون از published) باید همان
        appearance_config را داشته باشد، نه پیش‌فرضِ خالی."""
        store = _akhlaghi()
        draft = svc.get_or_create_draft(store)
        draft.appearance_config = svc.validate_appearance_config({"color_overrides": {"text": "#123456"}})
        draft.save(update_fields=["appearance_config"])
        svc.publish(store)

        new_draft = svc.get_or_create_draft(store)
        self.assertEqual(new_draft.appearance_config.get("color_overrides", {}).get("text"), "#123456")


HOST = "sfb-appearance-test.rastisi.localhost"


class AppearanceEditorViewTests(TestCase):
    def setUp(self):
        cache.clear()
        self.store = _akhlaghi()
        self.store.admin_subdomain = HOST.split(".")[0]
        self.store.save(update_fields=["admin_subdomain"])
        self.staff = User.objects.create_user(username="appearance_owner", password="pass12345", is_staff=True)
        StoreMembership.objects.create(
            store=self.store, user=self.staff, role=StoreMembership.Role.OWNER,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )
        self.client = Client(HTTP_HOST=HOST)
        self.client.login(username="appearance_owner", password="pass12345")

    def test_get_renders_hub(self):
        resp = self.client.get(reverse("dashboard:storefront-builder-appearance"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "ظاهر سایت")

    def test_post_saves_color_override_to_draft_not_live_shopsettings(self):
        shop_before = ShopSettings.load(store=self.store)
        original_primary = shop_before.primary_color

        resp = self.client.post(reverse("dashboard:storefront-builder-appearance"), {
            "template_slug": "modern", "font": "Vazirmatn", "radius": "18", "button_radius": "12",
            "density": "normal", "motion": "subtle", "color_text": "#0A0A0A",
        })
        self.assertEqual(resp.status_code, 302)

        draft = svc.get_or_create_draft(self.store)
        self.assertEqual(draft.appearance_config["color_overrides"]["text"], "#0A0A0A")

        # ShopSettings زنده دست‌نخورده مانده — این تغییر فقط در Draft است
        shop_after = ShopSettings.load(store=self.store)
        self.assertEqual(shop_after.primary_color, original_primary)

    def test_invalid_color_shows_error_without_saving(self):
        draft_before = svc.get_or_create_draft(self.store)
        original = dict(draft_before.appearance_config or {})
        resp = self.client.post(reverse("dashboard:storefront-builder-appearance"), {
            "template_slug": "not-a-real-template",
        })
        self.assertEqual(resp.status_code, 302)
        draft_after = svc.get_or_create_draft(self.store)
        self.assertEqual(draft_after.appearance_config, original)


@override_settings(ALLOWED_HOSTS=["sfb-appearance-public.example.com", "testserver", HOST])
class AppearanceDraftPublishIsolationTests(TestCase):
    """قلبِ چکپوینت: تغییرِ رنگ در Draft نباید تا Publish روی فروشگاهِ
    عمومی دیده شود — دقیقاً همان الزامِ غیرقابلِ‌مذاکره‌یِ بخشِ ۱۵ کار."""

    def setUp(self):
        cache.clear()
        self.store = _akhlaghi()
        StoreDomain.objects.create(
            store=self.store, hostname="sfb-appearance-public.example.com", is_primary=True,
            verification_status=StoreDomain.VerificationStatus.VERIFIED, verified_at=timezone.now(),
        )
        self.store.admin_subdomain = HOST.split(".")[0]
        self.store.save(update_fields=["admin_subdomain"])
        self.staff = User.objects.create_user(username="isolation_owner", password="pass12345", is_staff=True)
        StoreMembership.objects.create(
            store=self.store, user=self.staff, role=StoreMembership.Role.OWNER,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )
        self.admin_client = Client(HTTP_HOST=HOST)
        self.admin_client.login(username="isolation_owner", password="pass12345")

    def test_draft_color_change_invisible_on_public_page_until_publish(self):
        svc.get_or_create_draft(self.store)
        svc.publish(self.store)

        draft = svc.get_or_create_draft(self.store)
        draft.appearance_config = svc.validate_appearance_config({"color_overrides": {"primary": "#00FF00"}})
        draft.save(update_fields=["appearance_config"])

        public_resp = self.client.get(reverse("catalog:home"), HTTP_HOST="sfb-appearance-public.example.com")
        self.assertNotContains(public_resp, "#00FF00")

        preview_resp = self.admin_client.get(reverse("dashboard:storefront-builder-preview"))
        self.assertContains(preview_resp, "#00FF00")

    def test_published_appearance_reaches_public_page(self):
        svc.get_or_create_draft(self.store)
        svc.publish(self.store)

        draft = svc.get_or_create_draft(self.store)
        draft.appearance_config = svc.validate_appearance_config({"color_overrides": {"primary": "#00FF00"}})
        draft.save(update_fields=["appearance_config"])
        svc.publish(self.store)

        public_resp = self.client.get(reverse("catalog:home"), HTTP_HOST="sfb-appearance-public.example.com")
        self.assertContains(public_resp, "#00FF00")

    def test_other_pages_still_use_live_shopsettings_not_draft(self):
        """صفحاتِ غیرِ Builder-aware (مثلاً checkout/product) نباید هرگز
        appearance_config درگیرشان کند — چون storefront_appearance_version
        روی request آن‌ها اصلاً ست نمی‌شود."""
        draft = svc.get_or_create_draft(self.store)
        draft.appearance_config = svc.validate_appearance_config({"color_overrides": {"primary": "#00FF00"}})
        draft.save(update_fields=["appearance_config"])

        shop = ShopSettings.load(store=self.store)
        live_primary = shop.primary_color
        self.assertNotEqual(live_primary, "#00FF00")

        resp = self.client.get(reverse("catalog:product-list"), HTTP_HOST="sfb-appearance-public.example.com")
        self.assertContains(resp, live_primary.upper())
        self.assertNotContains(resp, "#00FF00")


class PaletteRegistryTests(TestCase):
    def test_at_least_twenty_palettes_registered(self):
        self.assertGreaterEqual(len(appearance_registry.list_palettes()), 20)

    def test_every_palette_has_all_eight_color_keys(self):
        from apps.storefront_builder.models import APPEARANCE_COLOR_KEYS

        for palette in appearance_registry.list_palettes():
            self.assertEqual(set(palette.colors.keys()), set(APPEARANCE_COLOR_KEYS), palette.slug)

    def test_palette_slugs_are_unique(self):
        slugs = [p.slug for p in appearance_registry.list_palettes()]
        self.assertEqual(len(slugs), len(set(slugs)))

    def test_at_least_one_template_registered(self):
        self.assertGreaterEqual(len(appearance_registry.list_templates()), 1)
        self.assertIsNotNone(appearance_registry.get_template("modern"))


class PaletteOverrideWorkflowTests(TestCase):
    """سناریوی دقیقاً همان مثالِ کارِ کاربر: انتخابِ پالت → override فقط
    یک رنگ → بازگردانیِ همان یک رنگ → بازگردانیِ کلِ پالت."""

    def setUp(self):
        cache.clear()
        self.store = _akhlaghi()
        self.store.admin_subdomain = HOST.split(".")[0]
        self.store.save(update_fields=["admin_subdomain"])
        self.staff = User.objects.create_user(username="palette_owner", password="pass12345", is_staff=True)
        StoreMembership.objects.create(
            store=self.store, user=self.staff, role=StoreMembership.Role.OWNER,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )
        self.client = Client(HTTP_HOST=HOST)
        self.client.login(username="palette_owner", password="pass12345")

    def _base_fields(self, draft):
        config = draft.effective_appearance_config()
        return {
            "template_slug": config["template_slug"], "font": config["font"],
            "radius": config["radius"], "button_radius": config["button_radius"],
            "density": config["density"], "motion": config["motion"],
        }

    def test_selecting_palette_sets_all_coordinated_colors(self):
        draft = svc.get_or_create_draft(self.store)
        self.client.post(reverse("dashboard:storefront-builder-appearance"), {
            **self._base_fields(draft), "palette_slug": "ocean",
        })
        draft = svc.get_or_create_draft(self.store)
        self.assertEqual(draft.appearance_config["palette_slug"], "ocean")
        colors = appearance_registry.resolve_colors(draft.appearance_config)
        self.assertEqual(colors, appearance_registry.get_palette("ocean").colors)

    def test_overriding_only_text_preserves_rest_of_palette(self):
        draft = svc.get_or_create_draft(self.store)
        self.client.post(reverse("dashboard:storefront-builder-appearance"), {
            **self._base_fields(draft), "palette_slug": "ocean",
        })
        draft = svc.get_or_create_draft(self.store)
        self.client.post(reverse("dashboard:storefront-builder-appearance"), {
            **self._base_fields(draft), "palette_slug": "ocean", "color_text": "#000000",
        })
        draft = svc.get_or_create_draft(self.store)
        colors = appearance_registry.resolve_colors(draft.appearance_config)
        base = appearance_registry.get_palette("ocean").colors
        self.assertEqual(colors["text"], "#000000")
        for key in ("primary", "secondary", "accent", "background", "surface", "muted", "border"):
            self.assertEqual(colors[key], base[key], key)

    def test_reset_one_color_restores_only_that_key(self):
        draft = svc.get_or_create_draft(self.store)
        self.client.post(reverse("dashboard:storefront-builder-appearance"), {
            **self._base_fields(draft), "palette_slug": "ocean", "color_text": "#000000", "color_primary": "#00FF00",
        })
        draft = svc.get_or_create_draft(self.store)
        self.client.post(reverse("dashboard:storefront-builder-appearance"), {
            **self._base_fields(draft), "palette_slug": "ocean",
            "color_text": "#000000", "color_primary": "#00FF00", "reset_color": "text",
        })
        draft = svc.get_or_create_draft(self.store)
        overrides = draft.appearance_config["color_overrides"]
        self.assertNotIn("text", overrides)
        self.assertEqual(overrides["primary"], "#00FF00")

    def test_reset_all_overrides_clears_everything_but_keeps_palette(self):
        draft = svc.get_or_create_draft(self.store)
        self.client.post(reverse("dashboard:storefront-builder-appearance"), {
            **self._base_fields(draft), "palette_slug": "ocean", "color_text": "#000000", "color_primary": "#00FF00",
        })
        draft = svc.get_or_create_draft(self.store)
        self.client.post(reverse("dashboard:storefront-builder-appearance"), {
            **self._base_fields(draft), "palette_slug": "ocean",
            "color_text": "#000000", "color_primary": "#00FF00", "reset_all_overrides": "1",
        })
        draft = svc.get_or_create_draft(self.store)
        self.assertEqual(draft.appearance_config["color_overrides"], {})
        self.assertEqual(draft.appearance_config["palette_slug"], "ocean")

    def test_switching_palette_clears_previous_overrides(self):
        draft = svc.get_or_create_draft(self.store)
        self.client.post(reverse("dashboard:storefront-builder-appearance"), {
            **self._base_fields(draft), "palette_slug": "ocean", "color_text": "#000000",
        })
        draft = svc.get_or_create_draft(self.store)
        self.assertEqual(draft.appearance_config["color_overrides"], {"text": "#000000"})

        self.client.post(reverse("dashboard:storefront-builder-appearance"), {
            **self._base_fields(draft), "palette_slug": "forest",
        })
        draft = svc.get_or_create_draft(self.store)
        self.assertEqual(draft.appearance_config["palette_slug"], "forest")
        self.assertEqual(draft.appearance_config["color_overrides"], {})


class TemplateRegistryTests(TestCase):
    def test_at_least_ten_templates_registered(self):
        self.assertGreaterEqual(len(appearance_registry.list_templates()), 10)

    def test_templates_are_structurally_distinct_not_just_color(self):
        """الزامِ صریحِ کار: «Template صرفاً رنگ نیست» — این تست تأیید
        می‌کند حداقل چند فیلدِ ساختاریِ واقعی (نه رنگ) بینِ قالب‌ها واقعاً
        فرق دارد، نه این‌که همه یک مقدارِ یکسان را کپی کرده باشند."""
        templates = appearance_registry.list_templates()
        content_widths = {t.content_width for t in templates}
        grid_densities = {t.grid_density for t in templates}
        radii = {t.radius for t in templates}
        hero_styles = {t.hero_style for t in templates}
        card_shadows = {t.card_shadow for t in templates}
        self.assertGreater(len(content_widths), 1)
        self.assertGreater(len(grid_densities), 1)
        self.assertGreater(len(radii), 1)
        self.assertGreater(len(hero_styles), 1)
        self.assertGreater(len(card_shadows), 1)

    def test_modern_template_matches_pre_template_system_defaults(self):
        """قالبِ پیش‌فرض نباید هیچ فروشگاهی را که هنوز به این سیستم دست
        نزده تغییر دهد."""
        modern = appearance_registry.get_template("modern")
        self.assertEqual(modern.radius, 18)
        self.assertEqual(modern.button_radius, 12)
        self.assertEqual(modern.content_width, 1200)


class TemplateSwitchViewTests(TestCase):
    def setUp(self):
        cache.clear()
        self.store = _akhlaghi()
        self.store.admin_subdomain = HOST.split(".")[0]
        self.store.save(update_fields=["admin_subdomain"])
        self.staff = User.objects.create_user(username="template_owner", password="pass12345", is_staff=True)
        StoreMembership.objects.create(
            store=self.store, user=self.staff, role=StoreMembership.Role.OWNER,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )
        self.client = Client(HTTP_HOST=HOST)
        self.client.login(username="template_owner", password="pass12345")

    def test_switching_template_with_no_palette_selected_does_not_crash(self):
        """رگرسیونِ باگِ واقعی: حلقه‌ی فرمِ گالریِ قالب یک‌بار مقدارِ
        Noneِ پایتون را به‌صورتِ رشته‌ی literal «None» در فیلدِ مخفیِ
        palette_slug رندر می‌کرد — این تست دقیقاً همان سناریو (فروشگاهی
        که هنوز هیچ Paletteی انتخاب نکرده) را شبیه‌سازی می‌کند."""
        draft = svc.get_or_create_draft(self.store)
        self.assertIsNone(draft.effective_appearance_config()["palette_slug"])

        resp = self.client.post(reverse("dashboard:storefront-builder-appearance"), {
            "template_slug": "boutique", "font": "Tahoma", "radius": "24",
            "button_radius": "22", "density": "relaxed", "motion": "subtle",
        })
        self.assertEqual(resp.status_code, 302)
        draft = svc.get_or_create_draft(self.store)
        self.assertEqual(draft.appearance_config["template_slug"], "boutique")
        self.assertIsNone(draft.appearance_config.get("palette_slug"))

    def test_switching_template_preserves_color_overrides(self):
        draft = svc.get_or_create_draft(self.store)
        draft.appearance_config = svc.validate_appearance_config({"color_overrides": {"text": "#123123"}})
        draft.save(update_fields=["appearance_config"])

        self.client.post(reverse("dashboard:storefront-builder-appearance"), {
            "template_slug": "tech", "font": "Tahoma", "radius": "14",
            "button_radius": "10", "density": "normal", "motion": "dynamic",
        })
        draft = svc.get_or_create_draft(self.store)
        self.assertEqual(draft.appearance_config["template_slug"], "tech")
        self.assertEqual(draft.appearance_config["color_overrides"], {"text": "#123123"})


@override_settings(ALLOWED_HOSTS=["sfb-template-public.example.com", "testserver", HOST])
class TemplateStructuralChangeReachesPublicPageTests(TestCase):
    """قدمِ Q/R/S/T واکینگِ کاربر: انتخابِ Marketplace → Publish → تغییرِ
    ساختاریِ محسوس؛ سپس تغییر به Boutique بدونِ تغییرِ محصولات/کالکشن‌ها."""

    def setUp(self):
        cache.clear()
        self.store = _akhlaghi()
        StoreDomain.objects.create(
            store=self.store, hostname="sfb-template-public.example.com", is_primary=True,
            verification_status=StoreDomain.VerificationStatus.VERIFIED, verified_at=timezone.now(),
        )

    def _publish_with_template(self, template_slug):
        svc.get_or_create_draft(self.store)
        svc.publish(self.store)
        draft = svc.get_or_create_draft(self.store)
        draft.appearance_config = svc.validate_appearance_config({"template_slug": template_slug})
        draft.save(update_fields=["appearance_config"])
        svc.publish(self.store)

    def test_marketplace_template_changes_content_width_on_public_page(self):
        self._publish_with_template("marketplace")
        resp = self.client.get(reverse("catalog:home"), HTTP_HOST="sfb-template-public.example.com")
        self.assertContains(resp, "data-sfb-template=\"marketplace\"")
        self.assertContains(resp, "--sfb-content-width:1320px")

    def test_switching_to_boutique_does_not_touch_products(self):
        from apps.catalog.models import Product

        product_count_before = Product.objects.filter(store=self.store).count()
        self._publish_with_template("marketplace")
        self._publish_with_template("boutique")
        product_count_after = Product.objects.filter(store=self.store).count()
        self.assertEqual(product_count_before, product_count_after)

        resp = self.client.get(reverse("catalog:home"), HTTP_HOST="sfb-template-public.example.com")
        self.assertContains(resp, "data-sfb-template=\"boutique\"")
        self.assertContains(resp, "data-sfb-hero-style=\"tall\"")
