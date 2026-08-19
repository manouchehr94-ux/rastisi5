from decimal import Decimal

from django.db import IntegrityError, transaction
from django.test import TestCase, override_settings

from apps.core.models import ShopSettings, ShopSettingsNotProvisionedError
from apps.stores.models import Store
from apps.stores.resolution import CompatibilityFallbackUnavailableError


def _akhlaghi():
    return Store.objects.get(slug="akhlaghi")


class ShopSettingsExplicitStoreTests(TestCase):
    """``ShopSettings.load(store=...)`` — the authoritative, non-compatibility path."""

    def test_load_with_explicit_store_returns_that_stores_row(self):
        akhlaghi = _akhlaghi()
        shop = ShopSettings.load(store=akhlaghi)
        self.assertEqual(shop.store_id, akhlaghi.pk)

    def test_load_with_explicit_store_never_returns_another_stores_row(self):
        store_b = Store.objects.create(name="Store B", slug="store-b", status=Store.Status.ACTIVE)
        ShopSettings.provision_for(store_b)

        akhlaghi = _akhlaghi()
        shop_a = ShopSettings.load(store=akhlaghi)
        shop_b = ShopSettings.load(store=store_b)

        self.assertNotEqual(shop_a.pk, shop_b.pk)
        self.assertEqual(shop_a.store_id, akhlaghi.pk)
        self.assertEqual(shop_b.store_id, store_b.pk)

    def test_load_with_explicit_store_missing_row_raises_domain_error(self):
        store_b = Store.objects.create(name="Store B", slug="store-b", status=Store.Status.ACTIVE)
        with self.assertRaises(ShopSettingsNotProvisionedError):
            ShopSettings.load(store=store_b)

    def test_missing_explicit_store_never_falls_back_to_another_stores_settings(self):
        store_b = Store.objects.create(name="Store B", slug="store-b", status=Store.Status.ACTIVE)
        try:
            ShopSettings.load(store=store_b)
        except ShopSettingsNotProvisionedError:
            pass
        else:
            self.fail("expected ShopSettingsNotProvisionedError")
        # Akhlaghi's row must be completely unaffected/unreturned.
        self.assertFalse(ShopSettings.objects.filter(store=store_b).exists())


class ShopSettingsCompatibilityModeTests(TestCase):
    """``ShopSettings.load()`` with no argument — the temporary, narrow
    single-Store compatibility fallback (see apps.stores.resolution)."""

    def test_load_with_no_store_returns_akhlaghi_when_sole_active_store(self):
        akhlaghi = _akhlaghi()
        shop = ShopSettings.load()
        self.assertEqual(shop.store_id, akhlaghi.pk)

    def test_bootstrapped_from_settings_py_via_the_data_migration(self):
        # The Akhlaghi row was created by the store_scope_settings backfill
        # migration (not lazily by load()), using the same settings.py
        # defaults the old get_or_create(pk=1, defaults=...) used.
        shop = ShopSettings.load()
        self.assertEqual(shop.name, "دیجی‌مارکت")
        self.assertEqual(shop.tax_percent, Decimal("9"))
        self.assertEqual(shop.free_shipping_threshold, Decimal("500000"))

    def test_load_with_no_store_returns_same_row_on_second_call(self):
        first = ShopSettings.load()
        first.name = "فروشگاه ویرایش‌شده"
        first.save()
        second = ShopSettings.load()
        self.assertEqual(second.name, "فروشگاه ویرایش‌شده")
        self.assertEqual(second.pk, first.pk)

    def test_compatibility_mode_fails_closed_when_second_store_exists(self):
        Store.objects.create(name="Store B", slug="store-b", status=Store.Status.ACTIVE)
        with self.assertRaises(CompatibilityFallbackUnavailableError):
            ShopSettings.load()

    def test_compatibility_mode_fails_closed_when_no_store_exists(self):
        Store.objects.all().delete()
        with self.assertRaises(CompatibilityFallbackUnavailableError):
            ShopSettings.load()

    def test_no_pk_equals_one_assumption_remains(self):
        # Historically ShopSettings forced pk=1 on every save(). That
        # override is gone: the singleton boundary is now "one row per
        # Store", not "one row for the whole platform" — a second Store's
        # row is free to have any pk.
        akhlaghi = _akhlaghi()
        store_b = Store.objects.create(name="Store B", slug="store-b", status=Store.Status.ACTIVE)
        shop_a = ShopSettings.load(store=akhlaghi)
        shop_b = ShopSettings.provision_for(store_b)
        self.assertNotEqual(shop_a.pk, shop_b.pk)
        self.assertNotEqual(shop_b.pk, 1)


class ShopSettingsProvisionForTests(TestCase):
    """``ShopSettings.provision_for(store)`` — the explicit provisioning boundary."""

    def test_provision_for_creates_a_row_for_a_new_store(self):
        store_b = Store.objects.create(name="Store B", slug="store-b", status=Store.Status.ACTIVE)
        self.assertFalse(ShopSettings.objects.filter(store=store_b).exists())
        shop = ShopSettings.provision_for(store_b)
        self.assertEqual(shop.store_id, store_b.pk)

    def test_provision_for_is_idempotent(self):
        store_b = Store.objects.create(name="Store B", slug="store-b", status=Store.Status.ACTIVE)
        first = ShopSettings.provision_for(store_b)
        second = ShopSettings.provision_for(store_b)
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(ShopSettings.objects.filter(store=store_b).count(), 1)

    def test_provision_for_never_overwrites_existing_merchant_values(self):
        store_b = Store.objects.create(name="Store B", slug="store-b", status=Store.Status.ACTIVE)
        shop = ShopSettings.provision_for(store_b)
        shop.name = "نام سفارشی تاجر"
        shop.save()

        reprovisioned = ShopSettings.provision_for(store_b)
        self.assertEqual(reprovisioned.name, "نام سفارشی تاجر")

    def test_provision_for_applies_bootstrap_defaults_only_on_first_creation(self):
        store_b = Store.objects.create(name="Store B", slug="store-b", status=Store.Status.ACTIVE)
        ShopSettings.provision_for(store_b)
        with override_settings(SHOP_NAME="نام دیگر", SHOP_TAX_PERCENT=7):
            shop = ShopSettings.provision_for(store_b)
        # Second call is a no-op get — the overridden settings must not
        # retroactively change an already-provisioned row.
        self.assertNotEqual(shop.name, "نام دیگر")

    def test_provision_for_uses_the_stores_real_name_not_the_generic_platform_default(self):
        """Regression test for Issue 1: ``settings.SHOP_NAME`` ("دیجی‌مارکت")
        is documented as generic *platform* identity, never a real
        merchant's data — ``provision_for`` must never persist it (or the
        matching ``SHOP_TAGLINE``/``SHOP_CONTACT_*`` example content) into a
        brand-new Store's real ShopSettings row."""
        store_b = Store.objects.create(
            name="فروشگاه واقعیِ تاجر", slug="real-merchant-store", status=Store.Status.ACTIVE,
        )
        with override_settings(
            SHOP_NAME="دیجی‌مارکت", SHOP_TAGLINE="فروشگاه اینترنتی چندمنظوره",
            SHOP_CONTACT_PHONE="021-91008877", SHOP_CONTACT_EMAIL="info@digimarket.ir",
            SHOP_CONTACT_ADDRESS="تهران، خیابان ولیعصر",
        ):
            shop = ShopSettings.provision_for(store_b)
        self.assertEqual(shop.name, "فروشگاه واقعیِ تاجر")
        self.assertEqual(shop.tagline, "")
        self.assertEqual(shop.contact_phone, "")
        self.assertEqual(shop.contact_email, "")
        self.assertEqual(shop.contact_address, "")


class ShopSettingsOneToOneConstraintTests(TestCase):
    """The database-level "exactly one ShopSettings per Store" invariant."""

    def test_duplicate_shopsettings_for_same_store_rejected(self):
        akhlaghi = _akhlaghi()
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                ShopSettings.objects.create(store=akhlaghi, name="Duplicate")

    def test_second_store_may_have_its_own_row(self):
        store_b = Store.objects.create(name="Store B", slug="store-b", status=Store.Status.ACTIVE)
        ShopSettings.objects.create(store=store_b, name="Store B Shop")
        self.assertEqual(ShopSettings.objects.count(), 2)


class ShopSettingsTwoStoreIsolationTests(TestCase):
    """Store A and Store B must never see or affect each other's ShopSettings."""

    def setUp(self):
        self.store_a = _akhlaghi()
        self.store_b = Store.objects.create(name="Store B", slug="store-b", status=Store.Status.ACTIVE)
        self.shop_b = ShopSettings.provision_for(self.store_b)

    def test_distinct_names_colors_contact_tax_and_sms_flags(self):
        shop_a = ShopSettings.load(store=self.store_a)
        shop_a.name = "فروشگاه آ"
        shop_a.primary_color = "#111111"
        shop_a.contact_email = "a@example.com"
        shop_a.tax_percent = Decimal("5")
        shop_a.sms_enabled = True
        shop_a.save()

        self.shop_b.name = "فروشگاه ب"
        self.shop_b.primary_color = "#222222"
        self.shop_b.contact_email = "b@example.com"
        self.shop_b.tax_percent = Decimal("12")
        self.shop_b.sms_enabled = False
        self.shop_b.save()

        reloaded_a = ShopSettings.load(store=self.store_a)
        reloaded_b = ShopSettings.load(store=self.store_b)

        self.assertEqual(reloaded_a.name, "فروشگاه آ")
        self.assertEqual(reloaded_b.name, "فروشگاه ب")
        self.assertNotEqual(reloaded_a.primary_color, reloaded_b.primary_color)
        self.assertNotEqual(reloaded_a.contact_email, reloaded_b.contact_email)
        self.assertNotEqual(reloaded_a.tax_percent, reloaded_b.tax_percent)
        self.assertNotEqual(reloaded_a.sms_enabled, reloaded_b.sms_enabled)

    def test_loading_a_never_returns_b(self):
        shop_a = ShopSettings.load(store=self.store_a)
        self.assertNotEqual(shop_a.pk, self.shop_b.pk)

    def test_saving_a_never_changes_b(self):
        original_b_name = self.shop_b.name
        shop_a = ShopSettings.load(store=self.store_a)
        shop_a.name = "تغییر فقط برای آ"
        shop_a.save()

        self.shop_b.refresh_from_db()
        self.assertEqual(self.shop_b.name, original_b_name)

    def test_compatibility_load_fails_once_two_stores_exist(self):
        with self.assertRaises(CompatibilityFallbackUnavailableError):
            ShopSettings.load()
