from decimal import Decimal

from django.test import TestCase

from apps.catalog.models import Category, Product, ProductImage, ProductVariant, Vendor
from apps.catalog.services.product_image_service import set_image_option_value, set_image_variant
from apps.catalog.services.storefront_variant_service import build_variant_selector_context
from apps.catalog.services.variant_engine_service import add_option_value, add_product_option, generate_variants
from apps.stores.models import Store


def _akhlaghi():
    return Store.objects.get(slug="akhlaghi")


class NoVariantsTests(TestCase):
    def test_simple_product_returns_none_mode(self):
        store = _akhlaghi()
        vendor = Vendor.objects.create(store=store, name="فروشنده", slug="sv-shop")
        category = Category.objects.create(store=store, name="دسته", slug="sv-cat")
        product = Product.objects.create(
            store=store, vendor=vendor, category=category, name="کالای ساده", slug="sv-simple",
            sku="SV-SIMPLE", price=Decimal("100000"),
        )
        ctx = build_variant_selector_context(product)
        self.assertEqual(ctx["mode"], "none")
        self.assertEqual(ctx["axes"], [])
        self.assertEqual(ctx["groups"], [])


class LegacySingleAxisTests(TestCase):
    """قیچیِ ایرانی/ایتالیایی — Part 5 مشخصات."""

    def setUp(self):
        self.store = _akhlaghi()
        self.vendor = Vendor.objects.create(store=self.store, name="فروشنده", slug="sv-scissors-shop")
        self.category = Category.objects.create(store=self.store, name="ابزار", slug="sv-scissors-cat")
        self.product = Product.objects.create(
            store=self.store, vendor=self.vendor, category=self.category, name="قیچی", slug="sv-scissors",
            sku="SV-SCISSORS", price=Decimal("1"), product_type=Product.ProductType.VARIABLE,
        )
        self.iranian = ProductVariant.objects.create(
            product=self.product, attribute="کشور سازنده", value="ایرانی",
            price=Decimal("100000"), stock=10, is_default=True,
        )
        self.italian = ProductVariant.objects.create(
            product=self.product, attribute="کشور سازنده", value="ایتالیایی",
            price=Decimal("800000"), stock=3,
        )

    def test_mode_is_legacy_with_one_group(self):
        ctx = build_variant_selector_context(self.product)
        self.assertEqual(ctx["mode"], "legacy")
        self.assertEqual(len(ctx["groups"]), 1)
        self.assertEqual(ctx["groups"][0]["label"], "کشور سازنده")

    def test_each_value_carries_its_own_absolute_price(self):
        ctx = build_variant_selector_context(self.product)
        values = {v["label"]: v for v in ctx["groups"][0]["values"]}
        self.assertEqual(values["ایرانی"]["price"], 100000)
        self.assertEqual(values["ایتالیایی"]["price"], 800000)
        self.assertEqual(values["ایرانی"]["stock"], 10)
        self.assertEqual(values["ایتالیایی"]["stock"], 3)

    def test_default_key_matches_default_variant(self):
        ctx = build_variant_selector_context(self.product)
        self.assertEqual(ctx["default_key"], str(self.iranian.pk))

    def test_out_of_stock_value_marked_not_purchasable(self):
        self.italian.stock = 0
        self.italian.save(update_fields=["stock"])
        ctx = build_variant_selector_context(self.product)
        values = {v["label"]: v for v in ctx["groups"][0]["values"]}
        self.assertFalse(values["ایتالیایی"]["is_purchasable"])
        self.assertTrue(values["ایرانی"]["is_purchasable"])

    def test_obsolete_and_inactive_variants_excluded(self):
        ProductVariant.objects.create(
            product=self.product, attribute="کشور سازنده", value="آلمانی", is_active=False,
        )
        ctx = build_variant_selector_context(self.product)
        labels = {v["label"] for v in ctx["groups"][0]["values"]}
        self.assertNotIn("آلمانی", labels)


class MultiAxisTests(TestCase):
    """رنگ × سایز — Part 6/7 مشخصات: محورهایِ مستقل."""

    def setUp(self):
        self.store = _akhlaghi()
        self.vendor = Vendor.objects.create(store=self.store, name="فروشنده", slug="sv-shirt-shop")
        self.category = Category.objects.create(store=self.store, name="پوشاک", slug="sv-shirt-cat")
        self.product = Product.objects.create(
            store=self.store, vendor=self.vendor, category=self.category, name="تی‌شرت", slug="sv-shirt",
            sku="SV-SHIRT", price=Decimal("300000"), product_type=Product.ProductType.VARIABLE,
        )
        self.color = add_product_option(self.product, label="رنگ", values=["قرمز", "آبی"])
        self.size = add_product_option(self.product, label="سایز", values=["S", "M"])
        generate_variants(self.product)

    def _variant(self, color_label, size_label):
        return ProductVariant.objects.get(
            product=self.product, value=f"{color_label} / {size_label}",
        )

    def test_mode_is_multi_axis_with_two_independent_axes(self):
        ctx = build_variant_selector_context(self.product)
        self.assertEqual(ctx["mode"], "multi_axis")
        self.assertEqual(len(ctx["axes"]), 2)
        self.assertEqual(ctx["axes"][0]["label"], "رنگ")
        self.assertEqual(ctx["axes"][1]["label"], "سایز")
        self.assertEqual({v["label"] for v in ctx["axes"][0]["values"]}, {"قرمز", "آبی"})
        self.assertEqual({v["label"] for v in ctx["axes"][1]["values"]}, {"S", "M"})

    def test_matrix_has_one_entry_per_real_combination(self):
        ctx = build_variant_selector_context(self.product)
        self.assertEqual(len(ctx["matrix"]), 4)

    def test_selecting_one_value_per_axis_resolves_to_exact_variant(self):
        ctx = build_variant_selector_context(self.product)
        red_id = next(v["id"] for v in ctx["axes"][0]["values"] if v["label"] == "قرمز")
        m_id = next(v["id"] for v in ctx["axes"][1]["values"] if v["label"] == "M")
        key = f"{red_id}|{m_id}"
        entry = ctx["matrix"][key]
        expected = self._variant("قرمز", "M")
        self.assertEqual(entry["variant_id"], expected.pk)

    def test_setting_price_and_stock_per_combination_reflected_independently(self):
        red_s = self._variant("قرمز", "S")
        red_s.price = Decimal("250000")
        red_s.stock = 7
        red_s.save(update_fields=["price", "stock"])
        blue_m = self._variant("آبی", "M")
        blue_m.stock = 0
        blue_m.save(update_fields=["stock"])

        ctx = build_variant_selector_context(self.product)
        red_id = next(v["id"] for v in ctx["axes"][0]["values"] if v["label"] == "قرمز")
        blue_id = next(v["id"] for v in ctx["axes"][0]["values"] if v["label"] == "آبی")
        s_id = next(v["id"] for v in ctx["axes"][1]["values"] if v["label"] == "S")
        m_id = next(v["id"] for v in ctx["axes"][1]["values"] if v["label"] == "M")

        self.assertEqual(ctx["matrix"][f"{red_id}|{s_id}"]["price"], 250000)
        self.assertEqual(ctx["matrix"][f"{red_id}|{s_id}"]["stock"], 7)
        self.assertFalse(ctx["matrix"][f"{blue_id}|{m_id}"]["is_purchasable"])

    def test_image_priority_exact_variant_wins(self):
        red_m = self._variant("قرمز", "M")
        image = ProductImage.objects.create(product=self.product, image="products/gallery/a.jpg")
        set_image_variant(image, red_m)

        ctx = build_variant_selector_context(self.product)
        red_id = next(v["id"] for v in ctx["axes"][0]["values"] if v["label"] == "قرمز")
        m_id = next(v["id"] for v in ctx["axes"][1]["values"] if v["label"] == "M")
        self.assertIn(image.image.url, ctx["matrix"][f"{red_id}|{m_id}"]["image_url"])

    def test_image_priority_falls_back_to_image_driving_attribute_value(self):
        """رنگ = قرمز → یک تصویر، بدونِ تصویرِ اختصاصیِ ترکیبِ دقیق —
        ترکیبِ قرمز/S و قرمز/M هر دو باید همین تصویر را نشان دهند."""
        self.color.attribute = None  # ensure attribute link doesn't interfere
        red_value = self.color.values.get(label="قرمز")
        image = ProductImage.objects.create(product=self.product, image="products/gallery/red.jpg")
        set_image_option_value(image, red_value)

        ctx = build_variant_selector_context(self.product)
        red_id = next(v["id"] for v in ctx["axes"][0]["values"] if v["label"] == "قرمز")
        s_id = next(v["id"] for v in ctx["axes"][1]["values"] if v["label"] == "S")
        m_id = next(v["id"] for v in ctx["axes"][1]["values"] if v["label"] == "M")
        self.assertIn(image.image.url, ctx["matrix"][f"{red_id}|{s_id}"]["image_url"])
        self.assertIn(image.image.url, ctx["matrix"][f"{red_id}|{m_id}"]["image_url"])

    def test_image_falls_back_to_cover_when_nothing_assigned(self):
        cover = ProductImage.objects.create(
            product=self.product, image="products/gallery/cover.jpg", is_cover=True,
        )
        ctx = build_variant_selector_context(self.product)
        red_id = next(v["id"] for v in ctx["axes"][0]["values"] if v["label"] == "قرمز")
        s_id = next(v["id"] for v in ctx["axes"][1]["values"] if v["label"] == "S")
        self.assertIn(cover.image.url, ctx["matrix"][f"{red_id}|{s_id}"]["image_url"])

    def test_deactivated_axis_variants_omitted_from_matrix(self):
        from apps.catalog.services.variant_engine_service import deactivate_product_option

        deactivate_product_option(self.size)
        generate_variants(self.product)
        ctx = build_variant_selector_context(self.product)
        self.assertEqual(len(ctx["axes"]), 1)
        self.assertEqual(len(ctx["matrix"]), 2)
