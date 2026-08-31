"""R4 Task 10 — the ONE shared Resource Picker for Product + Brand.

RED tests written FIRST, proven to fail against HEAD
77f003077fc783bbf038cd3cfbaa5ef4dac288bb (Task 9's accepted state — no
Picker endpoint, no ownership guard) before any Task 10 production code
exists. Three groups, matching the task's own sections:

- endpoint/UI contract (route, gate, shared template, kind allowlist,
  Store-scoped search, ordered/over-cap selected handling, no save form);
- mutation-boundary ownership (bypassing the Picker and POSTing straight to
  the existing R4 mutation endpoint with a foreign-Store resource id);
- shared-UI-contract assertions (one generic open control, no section-key
  literals in the Picker partial, one JS lifecycle for both kinds).
"""

import json
from decimal import Decimal
from pathlib import Path
from urllib.parse import urlencode

from django.urls import reverse

from apps.catalog.models import Brand, Category, MerchantCollection, Product, Vendor
from apps.storefront_builder.models import StorefrontEditHistoryEntry, StorefrontSection
from apps.storefront_builder.services import layout_service as svc
from apps.stores.models import Store

from .test_views import StorefrontBuilderViewsTestCase


def _second_store():
    store, _ = Store.objects.get_or_create(
        slug="r4-picker-store-b", defaults=dict(name="فروشگاه دوم پیکر", status=Store.Status.ACTIVE),
    )
    return store


class R4ResourcePickerTestCase(StorefrontBuilderViewsTestCase):
    """Shared setUp: R4 gate ON, a Draft with one product_section and one
    brand_carousel section — the only two Task 10 UI kinds."""

    def setUp(self):
        super().setUp()
        self.layout = svc.get_or_create_layout(self.store)
        self.layout.r4_editor_enabled = True
        self.layout.save(update_fields=["r4_editor_enabled"])
        self.draft = svc.get_or_create_draft(self.store, user=self.staff)
        self.product_section = StorefrontSection.objects.create(
            version=self.draft, section_key="product_section", order=0,
        )
        self.brand_section = StorefrontSection.objects.create(
            version=self.draft, section_key="brand_carousel", order=1,
        )

    def _make_product(self, *, store=None, name="کالای پیکر", slug="picker-product", sku="SKU-PICKER"):
        store = store or self.store
        vendor = Vendor.objects.create(store=store, name=f"فروشنده {slug}", slug=f"v-{slug}")
        return Product.objects.create(
            store=store, vendor=vendor, name=name, slug=slug, sku=sku,
            price=Decimal("10000"), status=Product.Status.ACTIVE,
        )

    def _make_brand(self, *, store=None, name="برند پیکر", slug="picker-brand"):
        store = store or self.store
        return Brand.objects.create(store=store, name=name, slug=slug)

    def _make_category(self, *, store=None, name="دسته پیکر", slug="picker-category"):
        store = store or self.store
        return Category.objects.create(store=store, name=name, slug=slug)

    def _make_collection(self, *, store=None, name="کالکشن پیکر", slug="picker-collection"):
        store = store or self.store
        return MerchantCollection.objects.create(store=store, name=name, slug=slug)

    def _picker_url(self, **params):
        url = reverse("dashboard:storefront-builder-r4-resource-picker")
        if params:
            url += "?" + urlencode(params, doseq=True)
        return url

    def _post_mutation(self, payload):
        return self.client.post(
            reverse("dashboard:storefront-builder-r4-mutation"),
            data=json.dumps(payload),
            content_type="application/json",
        )

    def _history_count(self):
        return StorefrontEditHistoryEntry.objects.filter(draft_version=self.draft).count()

    def _source_patch(self, **kwargs):
        base = {"kind": None, "mode": None, "auto_rule": None, "auto_parameters": {}, "manual_ids": []}
        base.update(kwargs)
        return {"source": base}


# ---------------------------------------------------------------------------
# Section 24 — endpoint / UI contract
# ---------------------------------------------------------------------------


class EndpointExistsTests(R4ResourcePickerTestCase):
    def test_route_resolves_and_returns_200_for_product(self):
        response = self.client.get(self._picker_url(kind="product"))
        self.assertEqual(response.status_code, 200)

    def test_route_resolves_and_returns_200_for_brand(self):
        response = self.client.get(self._picker_url(kind="brand"))
        self.assertEqual(response.status_code, 200)


class FeatureGateTests(R4ResourcePickerTestCase):
    def test_gate_off_returns_404(self):
        self.layout.r4_editor_enabled = False
        self.layout.save(update_fields=["r4_editor_enabled"])
        response = self.client.get(self._picker_url(kind="product"))
        self.assertEqual(response.status_code, 404)

    def test_anonymous_denied(self):
        self.client.logout()
        response = self.client.get(self._picker_url(kind="product"))
        self.assertNotEqual(response.status_code, 200)


class SharedTemplateTests(R4ResourcePickerTestCase):
    def test_product_and_brand_render_the_same_template(self):
        product_resp = self.client.get(self._picker_url(kind="product"))
        brand_resp = self.client.get(self._picker_url(kind="brand"))
        self.assertEqual(product_resp.status_code, 200)
        self.assertEqual(brand_resp.status_code, 200)
        product_templates = [t.name for t in product_resp.templates if t.name]
        brand_templates = [t.name for t in brand_resp.templates if t.name]
        self.assertEqual(product_templates, brand_templates)
        self.assertIn(
            "dashboard/storefront_builder/r4/partials/resource_picker.html", product_templates,
        )


class UnsupportedKindTests(R4ResourcePickerTestCase):
    def test_unknown_kind_is_rejected(self):
        response = self.client.get(self._picker_url(kind="widget"))
        self.assertEqual(response.status_code, 400)

    def test_category_kind_is_not_exposed(self):
        response = self.client.get(self._picker_url(kind="category"))
        self.assertEqual(response.status_code, 400)

    def test_collection_kind_is_not_exposed(self):
        response = self.client.get(self._picker_url(kind="collection"))
        self.assertEqual(response.status_code, 400)

    def test_missing_kind_is_rejected(self):
        response = self.client.get(reverse("dashboard:storefront-builder-r4-resource-picker"))
        self.assertEqual(response.status_code, 400)


class StoreScopedSearchTests(R4ResourcePickerTestCase):
    def test_product_search_excludes_foreign_store_products(self):
        own = self._make_product(name="کالای خودیِ جستجو", slug="own-search-product", sku="SKU-OWN-SEARCH")
        foreign = self._make_product(
            store=_second_store(), name="کالای غریبهِ جستجو", slug="foreign-search-product", sku="SKU-FOREIGN-SEARCH",
        )
        response = self.client.get(self._picker_url(kind="product", q="جستجو"))
        self.assertEqual(response.status_code, 200)
        body = response.content.decode()
        self.assertIn(own.name, body)
        self.assertNotIn(foreign.name, body)

    def test_brand_search_excludes_foreign_store_brands(self):
        own = self._make_brand(name="برند خودیِ جستجو", slug="own-search-brand")
        foreign = self._make_brand(store=_second_store(), name="برند غریبهِ جستجو", slug="foreign-search-brand")
        response = self.client.get(self._picker_url(kind="brand", q="جستجو"))
        self.assertEqual(response.status_code, 200)
        body = response.content.decode()
        self.assertIn(own.name, body)
        self.assertNotIn(foreign.name, body)

    def test_product_search_excludes_draft_placeholders(self):
        placeholder = self._make_product(name="پیش‌نویسِ ناقصِ جستجو", slug="draft-placeholder-search", sku="SKU-DRAFT-SEARCH")
        placeholder.is_draft_placeholder = True
        placeholder.save(update_fields=["is_draft_placeholder"])
        response = self.client.get(self._picker_url(kind="product", q="جستجو"))
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(placeholder.name, response.content.decode())


class SelectedOrderingTests(R4ResourcePickerTestCase):
    def test_selected_items_preserve_requested_order(self):
        p1 = self._make_product(name="کالایِ ترتیبِ یک", slug="order-p-one", sku="SKU-ORDER-ONE")
        p2 = self._make_product(name="کالایِ ترتیبِ دو", slug="order-p-two", sku="SKU-ORDER-TWO")
        p3 = self._make_product(name="کالایِ ترتیبِ سه", slug="order-p-three", sku="SKU-ORDER-THREE")
        response = self.client.get(self._picker_url(
            kind="product", q="no-such-query-xyz", selected=[p3.pk, p1.pk, p2.pk],
        ))
        self.assertEqual(response.status_code, 200)
        body = response.content.decode()
        self.assertIn(p1.name, body)
        self.assertIn(p2.name, body)
        self.assertIn(p3.name, body)
        pos3, pos1, pos2 = body.index(p3.name), body.index(p1.name), body.index(p2.name)
        self.assertLess(pos3, pos1)
        self.assertLess(pos1, pos2)

    def test_selected_ids_deduplicate_preserving_first_seen(self):
        p1 = self._make_product(name="کالایِ تکراریِ یک", slug="dup-p-one", sku="SKU-DUP-ONE")
        response = self.client.get(self._picker_url(
            kind="product", q="no-such-query-xyz", selected=[p1.pk, p1.pk, p1.pk],
        ))
        self.assertEqual(response.status_code, 200)
        body = response.content.decode()
        self.assertEqual(body.count(f'data-r4-picker-item-id="{p1.pk}"'), 1)


class OverCapSelectedTests(R4ResourcePickerTestCase):
    def test_brand_over_cap_selected_is_bounded_to_server_max(self):
        brands = [self._make_brand(name=f"برندِ سقف {i}", slug=f"cap-brand-{i}") for i in range(30)]
        ids = [b.pk for b in brands]
        response = self.client.get(self._picker_url(kind="brand", selected=ids, q="no-such-query-xyz"))
        self.assertEqual(response.status_code, 200)
        body = response.content.decode()
        rendered = sum(1 for b in brands if b.name in body)
        self.assertLessEqual(rendered, 24)
        self.assertLess(rendered, len(brands))


class NoSaveFormTests(R4ResourcePickerTestCase):
    def test_picker_html_has_no_save_form_or_action(self):
        response = self.client.get(self._picker_url(kind="product"))
        body = response.content.decode()
        self.assertNotIn("<form", body)
        self.assertNotIn("action=", body)


# ---------------------------------------------------------------------------
# Section 25 — mutation-boundary ownership (bypasses the Picker entirely)
# ---------------------------------------------------------------------------


class ProductManualOwnershipTests(R4ResourcePickerTestCase):
    def test_foreign_product_manual_id_is_rejected(self):
        foreign_product = self._make_product(
            store=_second_store(), name="کالای غریبهِ دستی", slug="foreign-manual-product", sku="SKU-FMP",
        )
        starting_revision = self.draft.edit_revision
        original_settings = dict(self.product_section.settings)
        before_count = self._history_count()

        response = self._post_mutation({
            "base_revision": starting_revision,
            "mutation": {
                "type": "section.update_settings",
                "section_id": self.product_section.pk,
                "patch": self._source_patch(kind="product", mode="manual", manual_ids=[foreign_product.pk]),
            },
        })

        self.assertEqual(response.status_code, 400)
        body = response.json()
        self.assertIs(body["ok"], False)
        self.assertEqual(body["code"], "invalid_resource_ownership")

        self.product_section.refresh_from_db()
        self.assertEqual(self.product_section.settings, original_settings)
        self.draft.refresh_from_db()
        self.assertEqual(self.draft.edit_revision, starting_revision)
        self.assertEqual(self._history_count(), before_count)

    def test_same_store_valid_product_manual_ids_succeed_with_legacy_shape(self):
        p1 = self._make_product(name="کالایِ معتبرِ یک", slug="valid-manual-p1", sku="SKU-VALID1")
        p2 = self._make_product(name="کالایِ معتبرِ دو", slug="valid-manual-p2", sku="SKU-VALID2")
        starting_revision = self.draft.edit_revision
        before_count = self._history_count()

        response = self._post_mutation({
            "base_revision": starting_revision,
            "mutation": {
                "type": "section.update_settings",
                "section_id": self.product_section.pk,
                "patch": self._source_patch(kind="product", mode="manual", manual_ids=[p1.pk, p2.pk]),
            },
        })

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIs(body["ok"], True)
        self.assertEqual(body["new_revision"], starting_revision + 1)

        self.product_section.refresh_from_db()
        self.assertNotIn("source", self.product_section.settings)
        self.assertEqual(self.product_section.settings["data_source"], "manual")
        self.assertEqual(self.product_section.settings["product_ids"], [p1.pk, p2.pk])

        self.draft.refresh_from_db()
        self.assertEqual(self.draft.edit_revision, starting_revision + 1)
        self.assertEqual(self._history_count(), before_count + 1)


class BrandManualOwnershipTests(R4ResourcePickerTestCase):
    def test_foreign_brand_manual_id_is_rejected(self):
        foreign_brand = self._make_brand(store=_second_store(), name="برندِ غریبهِ دستی", slug="foreign-manual-brand")
        starting_revision = self.draft.edit_revision
        original_settings = dict(self.brand_section.settings)
        before_count = self._history_count()

        response = self._post_mutation({
            "base_revision": starting_revision,
            "mutation": {
                "type": "section.update_settings",
                "section_id": self.brand_section.pk,
                "patch": self._source_patch(kind="brand", mode="manual", manual_ids=[foreign_brand.pk]),
            },
        })

        self.assertEqual(response.status_code, 400)
        body = response.json()
        self.assertEqual(body["code"], "invalid_resource_ownership")

        self.brand_section.refresh_from_db()
        self.assertEqual(self.brand_section.settings, original_settings)
        self.draft.refresh_from_db()
        self.assertEqual(self.draft.edit_revision, starting_revision)
        self.assertEqual(self._history_count(), before_count)

    def test_same_store_valid_brand_manual_ids_succeed_with_legacy_shape(self):
        b1 = self._make_brand(name="برندِ معتبرِ یک", slug="valid-manual-b1")
        b2 = self._make_brand(name="برندِ معتبرِ دو", slug="valid-manual-b2")
        starting_revision = self.draft.edit_revision
        before_count = self._history_count()

        response = self._post_mutation({
            "base_revision": starting_revision,
            "mutation": {
                "type": "section.update_settings",
                "section_id": self.brand_section.pk,
                "patch": self._source_patch(kind="brand", mode="manual", manual_ids=[b1.pk, b2.pk]),
            },
        })

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIs(body["ok"], True)
        self.assertEqual(body["new_revision"], starting_revision + 1)

        self.brand_section.refresh_from_db()
        self.assertNotIn("source", self.brand_section.settings)
        self.assertEqual(self.brand_section.settings["brand_ids"], [b1.pk, b2.pk])

        self.draft.refresh_from_db()
        self.assertEqual(self.draft.edit_revision, starting_revision + 1)
        self.assertEqual(self._history_count(), before_count + 1)


class ProductAutoOwnershipTests(R4ResourcePickerTestCase):
    def test_foreign_category_source_id_via_by_category_is_rejected(self):
        foreign_category = self._make_category(store=_second_store(), name="دستهِ غریبه", slug="foreign-category")
        starting_revision = self.draft.edit_revision
        original_settings = dict(self.product_section.settings)
        before_count = self._history_count()

        response = self._post_mutation({
            "base_revision": starting_revision,
            "mutation": {
                "type": "section.update_settings",
                "section_id": self.product_section.pk,
                "patch": self._source_patch(
                    kind="product", mode="auto", auto_rule="by_category",
                    auto_parameters={"source_id": foreign_category.pk},
                ),
            },
        })

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "invalid_resource_ownership")
        self.product_section.refresh_from_db()
        self.assertEqual(self.product_section.settings, original_settings)
        self.draft.refresh_from_db()
        self.assertEqual(self.draft.edit_revision, starting_revision)
        self.assertEqual(self._history_count(), before_count)

    def test_foreign_brand_source_id_via_by_brand_is_rejected(self):
        foreign_brand = self._make_brand(store=_second_store(), name="برندِ غریبهِ منبع", slug="foreign-source-brand")
        starting_revision = self.draft.edit_revision
        original_settings = dict(self.product_section.settings)
        before_count = self._history_count()

        response = self._post_mutation({
            "base_revision": starting_revision,
            "mutation": {
                "type": "section.update_settings",
                "section_id": self.product_section.pk,
                "patch": self._source_patch(
                    kind="product", mode="auto", auto_rule="by_brand",
                    auto_parameters={"source_id": foreign_brand.pk},
                ),
            },
        })

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "invalid_resource_ownership")
        self.product_section.refresh_from_db()
        self.assertEqual(self.product_section.settings, original_settings)
        self.draft.refresh_from_db()
        self.assertEqual(self.draft.edit_revision, starting_revision)
        self.assertEqual(self._history_count(), before_count)

    def test_foreign_collection_source_id_via_by_collection_is_rejected(self):
        foreign_collection = self._make_collection(store=_second_store(), name="کالکشنِ غریبه", slug="foreign-collection")
        starting_revision = self.draft.edit_revision
        original_settings = dict(self.product_section.settings)
        before_count = self._history_count()

        response = self._post_mutation({
            "base_revision": starting_revision,
            "mutation": {
                "type": "section.update_settings",
                "section_id": self.product_section.pk,
                "patch": self._source_patch(
                    kind="product", mode="auto", auto_rule="by_collection",
                    auto_parameters={"source_id": foreign_collection.pk},
                ),
            },
        })

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "invalid_resource_ownership")
        self.product_section.refresh_from_db()
        self.assertEqual(self.product_section.settings, original_settings)
        self.draft.refresh_from_db()
        self.assertEqual(self.draft.edit_revision, starting_revision)
        self.assertEqual(self._history_count(), before_count)

    def test_same_store_by_category_succeeds(self):
        category = self._make_category(name="دستهِ معتبر", slug="valid-category")
        starting_revision = self.draft.edit_revision
        response = self._post_mutation({
            "base_revision": starting_revision,
            "mutation": {
                "type": "section.update_settings",
                "section_id": self.product_section.pk,
                "patch": self._source_patch(
                    kind="product", mode="auto", auto_rule="by_category",
                    auto_parameters={"source_id": category.pk},
                ),
            },
        })
        self.assertEqual(response.status_code, 200)
        self.product_section.refresh_from_db()
        self.assertNotIn("source", self.product_section.settings)
        self.assertEqual(self.product_section.settings["data_source"], "category")
        self.assertEqual(self.product_section.settings["source_id"], category.pk)

    def test_ownerless_auto_rule_requires_no_lookup_and_succeeds(self):
        starting_revision = self.draft.edit_revision
        response = self._post_mutation({
            "base_revision": starting_revision,
            "mutation": {
                "type": "section.update_settings",
                "section_id": self.product_section.pk,
                "patch": self._source_patch(kind="product", mode="auto", auto_rule="newest"),
            },
        })
        self.assertEqual(response.status_code, 200)
        self.product_section.refresh_from_db()
        self.assertEqual(self.product_section.settings["data_source"], "newest")


class UnrelatedFieldEditDoesNotTriggerOwnershipCheckTests(R4ResourcePickerTestCase):
    def test_editing_title_with_stale_legacy_source_reference_does_not_fail(self):
        # A historical/deleted product_ids reference must not retroactively
        # break an unrelated field edit — ownership validation only runs
        # when THIS mutation's patch actually contains "source".
        self.product_section.settings = {
            **self.product_section.settings,
            "data_source": "manual",
            "product_ids": [999999],
        }
        self.product_section.save(update_fields=["settings"])
        starting_revision = self.draft.edit_revision

        response = self._post_mutation({
            "base_revision": starting_revision,
            "mutation": {
                "type": "section.update_settings",
                "section_id": self.product_section.pk,
                "patch": {"title": "عنوان جدید"},
            },
        })
        self.assertEqual(response.status_code, 200)
        self.product_section.refresh_from_db()
        self.assertEqual(self.product_section.settings["title"], "عنوان جدید")
        self.assertEqual(self.product_section.settings["product_ids"], [999999])


# ---------------------------------------------------------------------------
# Section 26 — shared UI contract
# ---------------------------------------------------------------------------


class SharedUiContractTests(R4ResourcePickerTestCase):
    def test_settings_field_has_generic_resource_picker_open_control(self):
        response = self.client.get(
            reverse("dashboard:storefront-builder-r4-section-inspector", args=[self.product_section.pk])
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "data-r4-resource-picker-open")

    def test_resource_picker_template_has_no_section_key_literals(self):
        response = self.client.get(self._picker_url(kind="product"))
        body = response.content.decode()
        self.assertNotIn("product_section", body)
        self.assertNotIn("brand_carousel", body)

    def test_product_and_brand_are_both_a_dialog(self):
        product_resp = self.client.get(self._picker_url(kind="product"))
        brand_resp = self.client.get(self._picker_url(kind="brand"))
        self.assertIn('role="dialog"', product_resp.content.decode())
        self.assertIn('role="dialog"', brand_resp.content.decode())
        self.assertIn('aria-modal="true"', product_resp.content.decode())
        self.assertIn('aria-modal="true"', brand_resp.content.decode())

    def test_no_r3_modal_markup_in_picker(self):
        response = self.client.get(self._picker_url(kind="product"))
        body = response.content.decode()
        self.assertNotIn("universal-selection-picker", body)
        self.assertNotIn("modal fade", body)

    def test_no_iframe_inside_picker(self):
        response = self.client.get(self._picker_url(kind="product"))
        self.assertNotIn("<iframe", response.content.decode())

    def test_editor_js_has_one_shared_lifecycle_not_kind_specific(self):
        js_path = Path(__file__).resolve().parents[1] / "static" / "storefront_builder" / "r4_editor.js"
        content = js_path.read_text(encoding="utf-8")
        self.assertNotIn("productPicker(", content)
        self.assertNotIn("brandPicker(", content)
        self.assertIn("resourcePicker", content)

    def test_editor_js_sends_source_through_enqueue_mutation(self):
        js_path = Path(__file__).resolve().parents[1] / "static" / "storefront_builder" / "r4_editor.js"
        content = js_path.read_text(encoding="utf-8")
        self.assertIn("R4.enqueueMutation", content)
        # the resource-source apply path must reuse the SAME queue helper —
        # never a second endpoint/save path of its own.
        self.assertNotIn("picker/apply", content)
        self.assertNotIn("picker/save", content)
