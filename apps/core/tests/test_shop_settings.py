from decimal import Decimal

from django.test import TestCase, override_settings

from apps.core.models import ShopSettings


class ShopSettingsLoadTests(TestCase):
    def test_load_creates_singleton_bootstrapped_from_settings_py(self):
        shop = ShopSettings.load()
        self.assertEqual(shop.pk, 1)
        self.assertEqual(shop.name, "دیجی‌مارکت")
        self.assertEqual(shop.tax_percent, Decimal("9"))
        self.assertEqual(shop.free_shipping_threshold, Decimal("500000"))

    def test_load_returns_same_row_on_second_call(self):
        first = ShopSettings.load()
        first.name = "فروشگاه ویرایش‌شده"
        first.save()
        second = ShopSettings.load()
        self.assertEqual(second.name, "فروشگاه ویرایش‌شده")
        self.assertEqual(ShopSettings.objects.count(), 1)

    def test_bootstrap_defaults_only_apply_on_first_creation(self):
        ShopSettings.load()  # ایجاد رکورد با مقادیر settings.py فعلی
        with override_settings(SHOP_NAME="نام دیگر", SHOP_TAX_PERCENT=7):
            shop = ShopSettings.load()
        self.assertEqual(shop.name, "دیجی‌مارکت")
        self.assertEqual(shop.tax_percent, Decimal("9"))

    def test_save_always_pins_pk_to_one(self):
        shop = ShopSettings.load()
        shop.pk = None
        shop.save()
        self.assertEqual(shop.pk, 1)
        self.assertEqual(ShopSettings.objects.count(), 1)
