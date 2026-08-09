"""مشکلِ ۳ (تصمیمِ مالک، بازبینیِ محصول/طراحی): تغییرِ Family باید Draft را
با چیدمانِ پیش‌فرضِ *واقعیِ* همان Family بازسازی کند — نه چیدمانِ Familyِ
قبلی را روی آن نگه دارد. این تست‌ها اثبات می‌کنند:

* تغییرِ Family واقعاً Sectionهای Draft را با پیش‌فرضِ Familyِ جدید
  جایگزین می‌کند.
* هیچ Sectionِ سفارشی‌شده‌ی Familyِ قبلی باقی نمی‌ماند.
* محصولات/دسته‌بندی‌ها/اطلاعاتِ فروشگاه هرگز لمس نمی‌شوند.
* نسخه‌ی منتشرشده تا Publishِ دوباره دست‌نخورده می‌ماند.
* Tenantِ دیگر تحتِ‌تأثیر قرار نمی‌گیرد.
* انتخابِ تکراریِ همان Family نتیجه‌ای پایدار و قابل‌پیش‌بینی دارد.
* بدونِ تأییدِ صریح (وقتی چیزی برایِ از دست‌دادن وجود دارد)، هیچ تغییری
  اعمال نمی‌شود.
"""

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.catalog.models import Category
from apps.storefront_builder import family_registry
from apps.storefront_builder.models import StorefrontSection
from apps.storefront_builder.services import bootstrap_service
from apps.storefront_builder.services import layout_service as svc
from apps.stores.models import Store, StoreMembership

User = get_user_model()

HOST = "sfb-family-reset-test.rastisi.localhost"


def _akhlaghi():
    return Store.objects.get(slug="akhlaghi")


class FamilyDefaultSectionResetTests(TestCase):
    def setUp(self):
        cache.clear()
        self.store = _akhlaghi()
        self.store.admin_subdomain = HOST.split(".")[0]
        self.store.save(update_fields=["admin_subdomain"])
        self.staff = User.objects.create_user(username="family_reset_owner", password="pass12345", is_staff=True)
        StoreMembership.objects.create(
            store=self.store, user=self.staff, role=StoreMembership.Role.OWNER,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )
        self.client = Client(HTTP_HOST=HOST)
        self.client.login(username="family_reset_owner", password="pass12345")

    def _switch_family(self, slug, confirm=True):
        data = {"family_slug": slug}
        if confirm:
            data["confirm_family_switch"] = "1"
        return self.client.post(reverse("dashboard:storefront-builder-appearance"), data)

    def test_selecting_family_rebuilds_section_composition_to_its_own_defaults(self):
        resp = self._switch_family("nordic_living")
        self.assertEqual(resp.status_code, 302)
        draft = svc.get_or_create_draft(self.store)
        keys = list(draft.sections.order_by("order").values_list("section_key", flat=True))
        nordic = family_registry.get_family("nordic_living")
        self.assertEqual(keys, list(nordic.default_section_keys))
        # طبقِ خودِ Familyِ nordic_living: category_grid به‌طور پیش‌فرض نیست.
        self.assertNotIn("category_grid", keys)

    def test_previous_family_customization_does_not_leak_into_new_family(self):
        self._switch_family("modern_fashion")
        draft = svc.get_or_create_draft(self.store)
        custom = draft.sections.first()
        custom.settings = {**(custom.settings or {}), "title": "عنوانِ سفارشیِ من"}
        custom.is_active = False
        custom.save(update_fields=["settings", "is_active"])

        self._switch_family("artisan_editorial")
        draft.refresh_from_db()
        artisan = family_registry.get_family("artisan_editorial")
        keys = list(draft.sections.order_by("order").values_list("section_key", flat=True))
        self.assertEqual(keys, list(artisan.default_section_keys))
        for section in draft.sections.all():
            self.assertTrue(section.is_active)
            self.assertNotIn("عنوانِ سفارشیِ من", str(section.settings))

    def test_store_catalog_and_identity_are_never_touched(self):
        category_count_before = Category.objects.filter(store=self.store).count()
        store_name_before = self.store.name
        self._switch_family("heritage_premium")
        self.assertEqual(Category.objects.filter(store=self.store).count(), category_count_before)
        self.store.refresh_from_db()
        self.assertEqual(self.store.name, store_name_before)

    def test_published_version_untouched_until_republish(self):
        svc.get_or_create_draft(self.store)
        svc.publish(self.store)
        layout = svc.get_or_create_layout(self.store)
        published_keys_before = list(
            layout.published_version.sections.order_by("order").values_list("section_key", flat=True)
        )

        self._switch_family("vibrant_catalog")

        layout.refresh_from_db()
        published_keys_after = list(
            layout.published_version.sections.order_by("order").values_list("section_key", flat=True)
        )
        self.assertEqual(published_keys_before, published_keys_after)

    def test_another_tenant_is_never_affected(self):
        other_store = Store.objects.create(name="فروشگاهِ دیگر", slug="sfb-family-reset-other", admin_subdomain="sfb-family-reset-other")
        other_draft = svc.get_or_create_draft(other_store)
        other_keys_before = list(other_draft.sections.order_by("order").values_list("section_key", flat=True))

        self._switch_family("modern_fashion")

        other_draft.refresh_from_db()
        other_keys_after = list(other_draft.sections.order_by("order").values_list("section_key", flat=True))
        self.assertEqual(other_keys_before, other_keys_after)

    def test_leaving_and_reselecting_same_family_yields_the_same_stable_default(self):
        """تصمیمِ مالک #۹: «اگر کاربر از یک Family خارج شد و دوباره آن را
        انتخاب کرد، باید همان Default معتبر و پایدار آن Family را ببیند؛
        نه ترکیبی از تنظیماتِ Familyهای قبلی»."""
        self._switch_family("heritage_premium")
        draft = svc.get_or_create_draft(self.store)
        first = list(draft.sections.order_by("order").values_list("section_key", "settings"))

        # خارج‌شدن به یک Familyِ دیگر و سفارشی‌کردنِ آن...
        self._switch_family("modern_fashion")
        draft.refresh_from_db()
        draft.sections.filter(section_key="trust_features").update(is_active=False)
        custom = draft.sections.first()
        custom.settings = {**(custom.settings or {}), "title": "دستکاریِ موقت"}
        custom.save(update_fields=["settings"])

        # ...سپس بازگشت به heritage_premium — باید همان Defaultِ پایدارِ
        # اولیه باشد، نه ترکیبی از modern_fashion.
        self._switch_family("heritage_premium")
        draft.refresh_from_db()
        second = list(draft.sections.order_by("order").values_list("section_key", "settings"))
        self.assertEqual(first, second)
        self.assertTrue(all(s.is_active for s in draft.sections.all()))
        self.assertNotIn("دستکاریِ موقت", str(list(draft.sections.values_list("settings", flat=True))))

    def test_family_switch_rejected_without_confirmation_when_sections_exist(self):
        draft = svc.get_or_create_draft(self.store)
        self.assertTrue(draft.sections.exists())
        keys_before = list(draft.sections.order_by("order").values_list("section_key", flat=True))

        resp = self._switch_family("modern_fashion", confirm=False)

        self.assertEqual(resp.status_code, 302)
        draft.refresh_from_db()
        self.assertEqual(
            list(draft.sections.order_by("order").values_list("section_key", flat=True)), keys_before,
        )
        self.assertIsNone(draft.appearance_config.get("family_slug") if draft.appearance_config else None)

    def test_family_switch_allowed_without_confirmation_when_draft_has_no_sections(self):
        draft = svc.get_or_create_draft(self.store)
        draft.sections.all().delete()

        resp = self._switch_family("modern_fashion", confirm=False)

        self.assertEqual(resp.status_code, 302)
        draft.refresh_from_db()
        self.assertEqual(draft.effective_appearance_config()["family_slug"], "modern_fashion")
        self.assertTrue(draft.sections.exists())

    def test_apply_family_default_sections_service_replaces_existing_sections(self):
        draft = svc.get_or_create_draft(self.store)
        StorefrontSection.objects.create(version=draft, section_key="rich_text", order=99)
        family = family_registry.get_family("vibrant_catalog")

        bootstrap_service.apply_family_default_sections(draft, family)

        keys = list(draft.sections.order_by("order").values_list("section_key", flat=True))
        self.assertEqual(keys, list(family.default_section_keys))
        self.assertNotIn("rich_text", keys)
