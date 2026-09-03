import copy
from decimal import Decimal

from django.template.loader import render_to_string
from django.test import TestCase
from django.urls import reverse

from apps.catalog.models import Category, Product, Vendor
from apps.catalog.services.product_card_service import build_product_card_data
from apps.storefront_builder.models import StorefrontPage, StorefrontSection
from apps.storefront_builder.section_registry import default_card_settings
from apps.storefront_builder.services import layout_service, render_service
from apps.storefront_builder.storefront_appearance.families import (
    DEFAULT_STORE_APPEARANCE_MANIFEST,
)
from apps.storefront_builder.storefront_appearance.persistence import (
    persist_store_appearance_manifest,
)
from apps.storefront_builder.storefront_appearance.rendering import (
    resolve_store_appearance_render_state,
)
from apps.storefront_builder.storefront_appearance.validation import (
    manifest_to_primitive,
)
from apps.stores.models import Store


def _akhlaghi():
    return Store.objects.get(slug="akhlaghi")


def _manifest_with(**selections):
    raw = copy.deepcopy(manifest_to_primitive(DEFAULT_STORE_APPEARANCE_MANIFEST))
    raw["selections"].update(selections)
    return raw


A8_CARD_PRESENTATIONS = {
    "card.standard.v1": "standard",
    "card.marketplace_price.v1": "marketplace_price",
    "card.editorial_minimal.v1": "editorial_minimal",
    "card.retail_row.v1": "retail_row",
    "card.luxury_dark.v1": "luxury_dark",
    "card.soft_capsule.v1": "soft_capsule",
    "card.beauty_glass.v1": "beauty_glass",
    "card.paper_frame.v1": "paper_frame",
    "card.price_first.v1": "price_first",
    "card.portrait_round.v1": "portrait_round",
    "card.catalog_index.v1": "catalog_index",
    "card.shipping_label.v1": "shipping_label",
    "card.shelf_editorial.v1": "shelf_editorial",
    "card.technical_spec.v1": "technical_spec",
    "card.tech_neon.v1": "tech_neon",
    "card.bold_outline.v1": "bold_outline",
}


class A8ProductCardPresentationTests(TestCase):
    def setUp(self):
        self.store = _akhlaghi()
        self.vendor = Vendor.objects.create(store=self.store, name="فروشگاه", slug="a8-card-shop")
        self.category = Category.objects.create(store=self.store, name="دسته", slug="a8-card-category")
        self.draft = layout_service.get_or_create_draft(self.store)

    def _product(self, **kwargs):
        count = Product.objects.count()
        defaults = {
            "store": self.store,
            "vendor": self.vendor,
            "category": self.category,
            "name": "کالای واقعی",
            "slug": f"a8-card-{count}",
            "sku": f"A8-CARD-{count}",
            "price": Decimal("200000"),
            "stock": 5,
            "status": Product.Status.ACTIVE,
        }
        defaults.update(kwargs)
        return Product.objects.create(**defaults)

    def _state(self, *, card="card.marketplace_price.v1", badge="badge.sale.v1"):
        persist_store_appearance_manifest(
            self.draft,
            _manifest_with(card=card, badge=badge),
        )
        return resolve_store_appearance_render_state(self.draft)

    def test_registered_card_and_badge_overlays_are_pure_presentation_settings(self):
        card_settings_for = getattr(render_service, "card_settings_for", None)
        badge_settings_for = getattr(render_service, "badge_settings_for", None)
        self.assertIsNotNone(card_settings_for)
        self.assertIsNotNone(badge_settings_for)
        state = self._state()

        before = copy.deepcopy(manifest_to_primitive(state.manifest))
        self.assertEqual(card_settings_for(state), {"card_style": "marketplace_price"})
        self.assertEqual(badge_settings_for(state), {"badge_treatment": "sale"})
        self.assertEqual(manifest_to_primitive(state.manifest), before)

    def test_all_sixteen_symbolic_card_selections_render_their_literal_presentation_without_truth_drift(self):
        product = self._product(
            name="کالای تخفیف‌دار",
            price=Decimal("100000"),
            discount_percent=20,
            stock=5,
            product_type=Product.ProductType.SIMPLE,
        )
        expected_truth = build_product_card_data(product)

        for component_key, expected_style in A8_CARD_PRESENTATIONS.items():
            with self.subTest(component_key=component_key):
                state = self._state(card=component_key, badge="badge.none.v1")
                overlay = render_service.card_settings_for(state)
                self.assertEqual(overlay, {"card_style": expected_style})
                settings = default_card_settings()
                settings.update(overlay)
                html = render_to_string(
                    "catalog/partials/product_card.html",
                    {"product": product, "card_settings": settings},
                )
                self.assertIn(f"style-{expected_style}", html)
                self.assertIn(expected_truth.url, html)
                self.assertIn("pill-disc", html)
                self.assertIn(reverse("cart:add", args=[product.slug]), html)
                self.assertEqual(build_product_card_data(product), expected_truth)

    def test_render_service_overlays_product_sections_without_mutating_saved_settings(self):
        page = self.draft.get_page(StorefrontPage.PageType.HOME)
        page.sections.all().delete()
        saved_settings = {
            "source_type": "newest",
            "display_mode": "grid",
            "card": {**default_card_settings(), "card_style": "standard"},
        }
        section = StorefrontSection.objects.create(
            page=page,
            section_key="product_section",
            order=0,
            settings=saved_settings,
        )
        state = self._state(card="card.editorial_minimal.v1", badge="badge.sale.v1")

        item = render_service.build_page_render_items(
            page,
            self.store,
            store_appearance=state,
        )[0]

        self.assertEqual(item["context"]["settings"]["card"]["card_style"], "editorial_minimal")
        self.assertEqual(item["context"]["settings"]["card"]["badge_treatment"], "sale")
        self.assertIsNot(item["section"], section)
        section.refresh_from_db()
        self.assertEqual(section.settings, saved_settings)

    def test_normal_sale_stock_variable_and_quick_add_truth_survives_presentations(self):
        products = {
            "normal": self._product(name="عادی"),
            "sale": self._product(name="تخفیف", price=Decimal("100000"), discount_percent=20),
            "out": self._product(name="ناموجود", stock=0),
            "variable": self._product(
                name="متغیر",
                product_type=Product.ProductType.VARIABLE,
            ),
            "quick": self._product(name="افزودن سریع", product_type=Product.ProductType.SIMPLE),
        }
        expected = {
            "normal": (False, False, True),
            "sale": (True, False, True),
            "out": (False, True, False),
            "variable": (False, False, False),
            "quick": (False, False, True),
        }
        state = self._state(card="card.bold_outline.v1", badge="badge.sale.v1")
        settings = default_card_settings()
        settings.update(render_service.card_settings_for(state))
        settings.update(render_service.badge_settings_for(state))

        for name, product in products.items():
            with self.subTest(name=name):
                truth_before = build_product_card_data(product)
                html = render_to_string(
                    "catalog/partials/product_card.html",
                    {"product": product, "card_settings": settings},
                )
                truth_after = build_product_card_data(product)
                self.assertEqual(truth_after, truth_before)
                self.assertEqual(
                    (truth_after.is_on_sale, truth_after.is_out_of_stock, truth_after.is_quick_add_eligible),
                    expected[name],
                )
                self.assertIn("style-bold_outline", html)
                self.assertIn("badge-treatment-sale", html)
                cart_action = reverse("cart:add", args=[product.slug])
                self.assertEqual(cart_action in html, expected[name][2])
