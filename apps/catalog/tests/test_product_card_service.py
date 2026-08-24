"""U3 — Universal Product Card business-data resolver tests.

Covers ``apps.catalog.services.product_card_service.build_product_card_data``
(pure unit tests) and the ``product_card.html`` rendering paths that consume
it, proving centralization did not change existing visible behavior and that
new capabilities (out-of-stock, quick-add eligibility) render safely."""

from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from apps.catalog.models import Category, Product, Vendor
from apps.catalog.services.product_card_service import build_product_card_data
from apps.stores.models import Store


def _akhlaghi():
    return Store.objects.get(slug="akhlaghi")


class ProductCardServiceTestCase(TestCase):
    def setUp(self):
        self.store = _akhlaghi()
        self.vendor = Vendor.objects.create(store=self.store, name="فروشگاه", slug="shop-pcard")
        self.category = Category.objects.create(store=self.store, name="دسته", slug="cat-pcard")

    def _product(self, **kwargs):
        defaults = dict(
            store=self.store, vendor=self.vendor, category=self.category,
            name="کالای تست", slug=f"pcard-{Product.objects.count()}",
            sku=f"SKU-PCARD-{Product.objects.count()}", price=Decimal("200000"),
            status=Product.Status.ACTIVE,
        )
        defaults.update(kwargs)
        return Product.objects.create(**defaults)


class BusinessDataResolverTests(ProductCardServiceTestCase):
    def test_no_discount_has_no_compare_at_price(self):
        product = self._product(discount_percent=0)
        card = build_product_card_data(product)
        self.assertFalse(card.is_on_sale)
        self.assertIsNone(card.compare_at_price)
        self.assertEqual(card.price, product.final_price)

    def test_discount_sets_compare_at_price_to_base_price(self):
        product = self._product(price=Decimal("100000"), discount_percent=20)
        card = build_product_card_data(product)
        self.assertTrue(card.is_on_sale)
        self.assertEqual(card.discount_percent, 20)
        self.assertEqual(card.compare_at_price, Decimal("100000"))
        self.assertEqual(card.price, Decimal("80000"))

    def test_tag_new_produces_new_badge(self):
        product = self._product(tag=Product.Tag.NEW)
        card = build_product_card_data(product)
        self.assertEqual(len(card.badges), 1)
        self.assertEqual(card.badges[0].key, "new")
        self.assertEqual(card.badges[0].label_fa, product.get_tag_display())

    def test_tag_hot_produces_hot_badge(self):
        product = self._product(tag=Product.Tag.HOT)
        card = build_product_card_data(product)
        self.assertEqual(card.badges[0].key, "hot")

    def test_tag_sale_reuses_new_visual_treatment(self):
        """Preserves the pre-U3 template's exact (if arguably quirky) CSS
        class choice for the ``sale`` tag — not a new design decision."""
        product = self._product(tag=Product.Tag.SALE)
        card = build_product_card_data(product)
        self.assertEqual(card.badges[0].key, "new")
        self.assertEqual(card.badges[0].label_fa, "حراج")

    def test_no_tag_no_badges(self):
        product = self._product(discount_percent=0, tag="")
        card = build_product_card_data(product)
        self.assertEqual(card.badges, ())

    def test_out_of_stock_when_zero_stock(self):
        product = self._product(stock=0)
        card = build_product_card_data(product)
        self.assertTrue(card.is_out_of_stock)
        self.assertFalse(card.is_quick_add_eligible)

    def test_in_stock_simple_product_is_quick_add_eligible(self):
        product = self._product(stock=5, product_type=Product.ProductType.SIMPLE)
        card = build_product_card_data(product)
        self.assertFalse(card.is_out_of_stock)
        self.assertTrue(card.is_quick_add_eligible)

    def test_variable_product_is_never_quick_add_eligible(self):
        """A grid card cannot let the shopper pick a variant — quick-add
        must route through the product page instead, even when stock > 0."""
        product = self._product(stock=5, product_type=Product.ProductType.VARIABLE)
        card = build_product_card_data(product)
        self.assertFalse(card.is_quick_add_eligible)

    def test_low_stock_is_always_false_today(self):
        """Capability boundary (see module docstring): no product-level
        low-stock threshold field exists yet."""
        product = self._product(stock=1)
        card = build_product_card_data(product)
        self.assertFalse(card.is_low_stock)

    def test_wishlist_always_eligible_today(self):
        product = self._product()
        card = build_product_card_data(product)
        self.assertTrue(card.is_wishlist_eligible)

    def test_no_images_returns_none_urls(self):
        product = self._product()
        card = build_product_card_data(product)
        self.assertIsNone(card.image_url)
        self.assertIsNone(card.secondary_image_url)

    def test_brand_name_empty_when_no_brand(self):
        product = self._product()
        card = build_product_card_data(product)
        self.assertEqual(card.brand_name, "")

    def test_url_matches_product_detail_route(self):
        product = self._product()
        card = build_product_card_data(product)
        self.assertEqual(card.url, reverse("catalog:product-detail", args=[product.slug]))


class ProductCardRenderRegressionTests(ProductCardServiceTestCase):
    """End-to-end rendering, proving centralization preserved existing
    visible output and that new capabilities render safely."""

    def test_discount_and_price_render_unchanged(self):
        self._product(name="کفش راحتی", price=Decimal("100000"), discount_percent=20)
        response = self.client.get(reverse("catalog:product-list"), {"q": "راحتی"})
        self.assertContains(response, "pill-disc")
        self.assertContains(response, "class=\"old\"")

    def test_out_of_stock_badge_and_hidden_quick_add(self):
        self._product(name="کیف چرمی خاص", stock=0)
        response = self.client.get(reverse("catalog:product-list"), {"q": "خاص"})
        self.assertContains(response, "pill-outofstock")
        self.assertNotContains(response, "addbar")

    def test_in_stock_simple_product_shows_quick_add(self):
        self._product(name="عینک آفتابی ویژه", stock=5)
        response = self.client.get(reverse("catalog:product-list"), {"q": "ویژه"})
        self.assertContains(response, "addbar")

    def test_variable_product_hides_quick_add_even_in_stock(self):
        self._product(name="پیراهن رنگی متنوع", stock=5, product_type=Product.ProductType.VARIABLE)
        response = self.client.get(reverse("catalog:product-list"), {"q": "متنوع"})
        self.assertNotContains(response, "addbar")
