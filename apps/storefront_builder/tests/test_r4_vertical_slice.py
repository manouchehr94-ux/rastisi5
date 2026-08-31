import dataclasses

from unittest.mock import patch

from apps.storefront_builder import section_registry as section_registry_module
from apps.storefront_builder.models import (
    StorefrontCell,
    StorefrontContainer,
    StorefrontLayoutVersion,
    StorefrontPage,
    StorefrontSection,
)
from apps.storefront_builder.services import container_service
from apps.stores.models import Store

from .test_r4_mutation_api import R4MutationApiTestCase


class R4VerticalSliceTestCase(R4MutationApiTestCase):
    """Shared base: R4MutationApiTestCase already gives a gated Draft with
    one bare (unplaced) ``hero_banner`` Section (``self.section``). Task 8
    tests additionally need a real, placed ``rich_text`` Section as the
    generic "safe to add/remove/duplicate/move" candidate."""

    def setUp(self):
        super().setUp()
        self.home_page = self.draft.get_page(StorefrontPage.PageType.HOME)
        # The shared base fixture's Draft is bootstrapped with ~16 default
        # legacy sections (layout_service.get_or_create_draft ->
        # bootstrap_service.apply_bootstrap_content, already migrated into
        # Containers by ensure_version_containers) plus one bare
        # hero_banner (R4MutationApiTestCase.setUp). Task 8's structural
        # tests need a clean, fully predictable Home page instead — each
        # test builds its own minimal, explicit Container/Cell scenario.
        self.home_page.sections.all().delete()
        self.home_page.containers.all().delete()

    def _place_new_section(self, section_key="rich_text", **kwargs):
        order = self.home_page.sections.count()
        section = StorefrontSection.objects.create(
            page=self.home_page, section_key=section_key, order=order, **kwargs,
        )
        container = container_service.create_empty_container(self.home_page, "single")
        cell = container.cells.order_by("order", "id").first()
        container_service.place_section(cell, section)
        return section, container, cell

    def _refresh_revision(self):
        self.draft.refresh_from_db()
        return self.draft.edit_revision


class AddSectionTests(R4VerticalSliceTestCase):
    def test_add_succeeds_and_increments_revision_once(self):
        starting_revision = self.draft.edit_revision
        before_count = self._history_count()
        response = self._post_json({
            "base_revision": starting_revision,
            "mutation": {"type": "section.add", "section_key": "rich_text"},
        })
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIs(body["ok"], True)
        self.assertEqual(body["new_revision"], starting_revision + 1)
        self.assertEqual(self._refresh_revision(), starting_revision + 1)
        self.assertEqual(self._history_count(), before_count + 1)

        new_section = StorefrontSection.objects.exclude(pk=self.section.pk).get(
            page=self.home_page, section_key="rich_text",
        )
        self.assertIsNotNone(new_section.cell_id)
        self.assertEqual(list(container_service.get_cell_blocks(new_section.cell)), [new_section])

    def test_add_preserves_existing_containers_and_cells(self):
        _, existing_container, existing_cell = self._place_new_section("rich_text")
        containers_before = set(StorefrontContainer.objects.filter(page=self.home_page).values_list("pk", flat=True))
        cells_before = set(StorefrontCell.objects.filter(container__page=self.home_page).values_list("pk", flat=True))

        self._post_json({
            "base_revision": self.draft.edit_revision,
            "mutation": {"type": "section.add", "section_key": "faq"},
        })

        containers_after = set(StorefrontContainer.objects.filter(page=self.home_page).values_list("pk", flat=True))
        cells_after = set(StorefrontCell.objects.filter(container__page=self.home_page).values_list("pk", flat=True))
        self.assertTrue(containers_before.issubset(containers_after))
        self.assertTrue(cells_before.issubset(cells_after))
        existing_cell.refresh_from_db()
        self.assertEqual(existing_cell.section_id, existing_container.cells.first().section_id)

    def test_add_rejects_invalid_section_key(self):
        starting_revision = self.draft.edit_revision
        response = self._post_json({
            "base_revision": starting_revision,
            "mutation": {"type": "section.add", "section_key": "does_not_exist"},
        })
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self._refresh_revision(), starting_revision)

    def test_add_rejects_hidden_from_library(self):
        starting_revision = self.draft.edit_revision
        response = self._post_json({
            "base_revision": starting_revision,
            "mutation": {"type": "section.add", "section_key": "announcement_bar"},
        })
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "section_hidden_from_library")
        self.assertEqual(self._refresh_revision(), starting_revision)

    def test_add_rejects_section_not_allowed_on_home(self):
        starting_revision = self.draft.edit_revision
        response = self._post_json({
            "base_revision": starting_revision,
            "mutation": {"type": "section.add", "section_key": "product_main"},
        })
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "section_not_allowed_on_page")
        self.assertEqual(self._refresh_revision(), starting_revision)

    def test_add_rejects_max_instances_exceeded(self):
        self._place_new_section("trust_features")
        starting_revision = self.draft.edit_revision
        before_count = self.home_page.sections.filter(section_key="trust_features").count()
        response = self._post_json({
            "base_revision": starting_revision,
            "mutation": {"type": "section.add", "section_key": "trust_features"},
        })
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "max_instances_exceeded")
        self.assertEqual(self._refresh_revision(), starting_revision)
        self.assertEqual(self.home_page.sections.filter(section_key="trust_features").count(), before_count)

    def test_stale_replay_returns_409_and_no_structural_change(self):
        starting_revision = self.draft.edit_revision
        self._post_json({
            "base_revision": starting_revision,
            "mutation": {"type": "section.add", "section_key": "rich_text"},
        })
        count_after_first = self.home_page.sections.count()
        response = self._post_json({
            "base_revision": starting_revision,
            "mutation": {"type": "section.add", "section_key": "rich_text"},
        })
        self.assertEqual(response.status_code, 409)
        self.assertEqual(self.home_page.sections.count(), count_after_first)


class RemoveSectionTests(R4VerticalSliceTestCase):
    def test_remove_succeeds_and_increments_revision_once(self):
        section, container, cell = self._place_new_section("rich_text")
        starting_revision = self.draft.edit_revision
        before_count = self._history_count()
        response = self._post_json({
            "base_revision": starting_revision,
            "mutation": {"type": "section.remove", "section_id": section.pk},
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["new_revision"], starting_revision + 1)
        self.assertEqual(self._refresh_revision(), starting_revision + 1)
        self.assertEqual(self._history_count(), before_count + 1)
        self.assertFalse(StorefrontSection.objects.filter(pk=section.pk).exists())
        self.assertTrue(StorefrontContainer.objects.filter(pk=container.pk).exists())
        self.assertTrue(StorefrontCell.objects.filter(pk=cell.pk).exists())

    def test_remove_multi_block_safety(self):
        section, container, cell = self._place_new_section("rich_text")
        sibling = StorefrontSection.objects.create(
            page=self.home_page, section_key="faq", order=self.home_page.sections.count(),
        )
        container_service.add_block(cell, sibling, at_index=1)
        other_container_count = StorefrontContainer.objects.filter(page=self.home_page).exclude(pk=container.pk).count()

        response = self._post_json({
            "base_revision": self.draft.edit_revision,
            "mutation": {"type": "section.remove", "section_id": section.pk},
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(StorefrontSection.objects.filter(pk=section.pk).exists())
        sibling.refresh_from_db()
        self.assertEqual(sibling.cell_id, cell.pk)
        self.assertEqual(sibling.cell_order, 0)
        self.assertTrue(StorefrontContainer.objects.filter(pk=container.pk).exists())
        self.assertEqual(
            StorefrontContainer.objects.filter(page=self.home_page).exclude(pk=container.pk).count(),
            other_container_count,
        )

    def test_remove_rejects_locked_section(self):
        section, _, _ = self._place_new_section("rich_text", is_locked=True)
        starting_revision = self.draft.edit_revision
        response = self._post_json({
            "base_revision": starting_revision,
            "mutation": {"type": "section.remove", "section_id": section.pk},
        })
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "section_locked")
        self.assertTrue(StorefrontSection.objects.filter(pk=section.pk).exists())
        self.assertEqual(self._refresh_revision(), starting_revision)

    def test_remove_rejects_locked_container(self):
        section, container, _ = self._place_new_section("rich_text")
        container.is_locked = True
        container.save(update_fields=["is_locked"])
        starting_revision = self.draft.edit_revision
        response = self._post_json({
            "base_revision": starting_revision,
            "mutation": {"type": "section.remove", "section_id": section.pk},
        })
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "container_locked")
        self.assertTrue(StorefrontSection.objects.filter(pk=section.pk).exists())
        self.assertEqual(self._refresh_revision(), starting_revision)

    def test_remove_rejects_non_removable_definition(self):
        section, _, _ = self._place_new_section("product_main")
        starting_revision = self.draft.edit_revision
        response = self._post_json({
            "base_revision": starting_revision,
            "mutation": {"type": "section.remove", "section_id": section.pk},
        })
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "section_not_removable")
        self.assertTrue(StorefrontSection.objects.filter(pk=section.pk).exists())
        self.assertEqual(self._refresh_revision(), starting_revision)

    def test_remove_rejects_row_member(self):
        section, _, _ = self._place_new_section("rich_text", row_key="promo-row", row_span=6)
        StorefrontSection.objects.create(
            page=self.home_page, section_key="faq", order=self.home_page.sections.count(),
            row_key="promo-row", row_span=6,
        )
        starting_revision = self.draft.edit_revision
        response = self._post_json({
            "base_revision": starting_revision,
            "mutation": {"type": "section.remove", "section_id": section.pk},
        })
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "row_member")
        self.assertTrue(StorefrontSection.objects.filter(pk=section.pk).exists())
        self.assertEqual(self._refresh_revision(), starting_revision)

    def test_remove_rejects_min_instances_violation(self):
        real_definition = section_registry_module.get_definition("rich_text")
        min_one_definition = dataclasses.replace(real_definition, min_instances=1)
        section, _, _ = self._place_new_section("rich_text")
        starting_revision = self.draft.edit_revision
        with patch(
            "apps.storefront_builder.services.section_structure_service.section_registry.get_definition",
            return_value=min_one_definition,
        ):
            response = self._post_json({
                "base_revision": starting_revision,
                "mutation": {"type": "section.remove", "section_id": section.pk},
            })
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "min_instances_violation")
        self.assertTrue(StorefrontSection.objects.filter(pk=section.pk).exists())
        self.assertEqual(self._refresh_revision(), starting_revision)

    def test_stale_replay_returns_409_and_no_structural_change(self):
        section, _, _ = self._place_new_section("rich_text")
        starting_revision = self.draft.edit_revision
        self._post_json({
            "base_revision": starting_revision,
            "mutation": {"type": "section.remove", "section_id": section.pk},
        })
        response = self._post_json({
            "base_revision": starting_revision,
            "mutation": {"type": "section.remove", "section_id": section.pk},
        })
        self.assertEqual(response.status_code, 409)


class DuplicateSectionTests(R4VerticalSliceTestCase):
    def test_duplicate_succeeds_with_independent_settings_and_same_cell_placement(self):
        section, container, cell = self._place_new_section(
            "rich_text", settings={"body_html": "<p>اصل</p>", "nested": {"level": 1}},
        )
        starting_revision = self.draft.edit_revision
        before_count = self._history_count()
        response = self._post_json({
            "base_revision": starting_revision,
            "mutation": {"type": "section.duplicate", "section_id": section.pk},
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["new_revision"], starting_revision + 1)
        self.assertEqual(self._refresh_revision(), starting_revision + 1)
        self.assertEqual(self._history_count(), before_count + 1)

        duplicate = StorefrontSection.objects.exclude(pk=section.pk).get(
            page=self.home_page, section_key="rich_text",
        )
        self.assertNotEqual(duplicate.pk, section.pk)
        self.assertNotEqual(duplicate.stable_id, section.stable_id)
        self.assertEqual(duplicate.settings, section.settings)

        duplicate.settings["nested"]["level"] = 999
        duplicate.save(update_fields=["settings"])
        section.refresh_from_db()
        self.assertEqual(section.settings["nested"]["level"], 1)

        blocks = container_service.get_cell_blocks(cell)
        self.assertEqual([b.pk for b in blocks], [section.pk, duplicate.pk])

    def test_duplicate_adopts_legacy_only_cell_pointer_without_losing_source(self):
        section, container, cell = self._place_new_section("rich_text")
        # Simulate a genuinely legacy-only placement: detach the new FK,
        # leaving only the OneToOne pointer — the exact compatibility case
        # instruction Section 12 calls out.
        StorefrontSection.objects.filter(pk=section.pk).update(cell=None, cell_order=0)
        section.refresh_from_db()
        cell.refresh_from_db()
        self.assertIsNone(section.cell_id)
        self.assertEqual(cell.section_id, section.pk)

        response = self._post_json({
            "base_revision": self.draft.edit_revision,
            "mutation": {"type": "section.duplicate", "section_id": section.pk},
        })
        self.assertEqual(response.status_code, 200)
        blocks = container_service.get_cell_blocks(cell)
        block_ids = [b.pk for b in blocks]
        self.assertIn(section.pk, block_ids)
        duplicate = StorefrontSection.objects.exclude(pk=section.pk).get(
            page=self.home_page, section_key="rich_text",
        )
        self.assertIn(duplicate.pk, block_ids)
        self.assertEqual(block_ids, [section.pk, duplicate.pk])

    def test_duplicate_clones_section_scoped_media_without_duplicating_asset_bytes(self):
        section, _, _ = self._place_new_section("hero_banner")
        import io

        from django.core.files.uploadedfile import SimpleUploadedFile
        from PIL import Image

        from apps.content.models import HeroSlide, MediaAsset

        buf = io.BytesIO()
        Image.new("RGB", (800, 400), (10, 20, 30)).save(buf, "PNG")
        png_bytes = buf.getvalue()
        asset = MediaAsset.objects.create(
            store=self.store,
            image=SimpleUploadedFile("qa.png", png_bytes, content_type="image/png"),
        )
        HeroSlide.objects.create(
            store=self.store, section=section, title="اسلاید اصلی",
            desktop_asset=asset,
            desktop_image=SimpleUploadedFile("qa.png", png_bytes, content_type="image/png"),
        )
        response = self._post_json({
            "base_revision": self.draft.edit_revision,
            "mutation": {"type": "section.duplicate", "section_id": section.pk},
        })
        self.assertEqual(response.status_code, 200)
        duplicate = StorefrontSection.objects.exclude(pk=section.pk).get(
            page=self.home_page, section_key="hero_banner",
        )
        duplicate_slide = HeroSlide.objects.get(section=duplicate)
        self.assertEqual(duplicate_slide.desktop_asset_id, asset.pk)
        self.assertNotEqual(duplicate_slide.pk, HeroSlide.objects.get(section=section).pk)
        self.assertEqual(MediaAsset.objects.filter(store=self.store).count(), 1)

    def test_duplicate_rejects_non_duplicable_definition(self):
        section, _, _ = self._place_new_section("trust_features")
        starting_revision = self.draft.edit_revision
        response = self._post_json({
            "base_revision": starting_revision,
            "mutation": {"type": "section.duplicate", "section_id": section.pk},
        })
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "section_not_duplicable")
        self.assertEqual(self._refresh_revision(), starting_revision)

    def test_duplicate_rejects_max_instances_exceeded(self):
        section, _, _ = self._place_new_section("trust_features")
        # trust_features has duplicable=False already; use a mocked
        # duplicable-but-max-instances=1 definition to isolate this check.
        real_definition = section_registry_module.get_definition("trust_features")
        mocked = dataclasses.replace(real_definition, duplicable=True, max_instances=1)
        starting_revision = self.draft.edit_revision
        with patch(
            "apps.storefront_builder.services.section_structure_service.section_registry.get_definition",
            return_value=mocked,
        ):
            response = self._post_json({
                "base_revision": starting_revision,
                "mutation": {"type": "section.duplicate", "section_id": section.pk},
            })
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "max_instances_exceeded")
        self.assertEqual(self._refresh_revision(), starting_revision)

    def test_duplicate_rejects_locked_container(self):
        section, container, _ = self._place_new_section("rich_text")
        container.is_locked = True
        container.save(update_fields=["is_locked"])
        starting_revision = self.draft.edit_revision
        response = self._post_json({
            "base_revision": starting_revision,
            "mutation": {"type": "section.duplicate", "section_id": section.pk},
        })
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "container_locked")
        self.assertEqual(self._refresh_revision(), starting_revision)

    def test_stale_replay_returns_409_and_no_structural_change(self):
        section, _, _ = self._place_new_section("rich_text")
        starting_revision = self.draft.edit_revision
        self._post_json({
            "base_revision": starting_revision,
            "mutation": {"type": "section.duplicate", "section_id": section.pk},
        })
        count_after_first = self.home_page.sections.count()
        response = self._post_json({
            "base_revision": starting_revision,
            "mutation": {"type": "section.duplicate", "section_id": section.pk},
        })
        self.assertEqual(response.status_code, 409)
        self.assertEqual(self.home_page.sections.count(), count_after_first)


class MoveSectionSameCellTests(R4VerticalSliceTestCase):
    def test_move_up_swaps_adjacent_blocks_in_same_cell(self):
        _, container, cell = self._place_new_section("rich_text")
        a = StorefrontSection.objects.get(page=self.home_page, section_key="rich_text")
        b = StorefrontSection.objects.create(
            page=self.home_page, section_key="faq", order=self.home_page.sections.count(),
        )
        container_service.add_block(cell, b, at_index=1)
        c = StorefrontSection.objects.create(
            page=self.home_page, section_key="faq", order=self.home_page.sections.count(),
        )
        container_service.add_block(cell, c, at_index=2)

        starting_revision = self.draft.edit_revision
        response = self._post_json({
            "base_revision": starting_revision,
            "mutation": {"type": "section.move", "section_id": b.pk, "direction": "up"},
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self._refresh_revision(), starting_revision + 1)
        blocks = container_service.get_cell_blocks(cell)
        self.assertEqual([blk.pk for blk in blocks], [b.pk, a.pk, c.pk])
        self.assertTrue(StorefrontContainer.objects.filter(pk=container.pk).exists())
        self.assertTrue(StorefrontCell.objects.filter(pk=cell.pk).exists())

    def test_move_boundary_is_rejected_not_a_silent_noop(self):
        section, _, _ = self._place_new_section("rich_text")
        starting_revision = self.draft.edit_revision
        response = self._post_json({
            "base_revision": starting_revision,
            "mutation": {"type": "section.move", "section_id": section.pk, "direction": "up"},
        })
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "move_boundary")
        self.assertEqual(self._refresh_revision(), starting_revision)

    def test_move_rejects_invalid_direction(self):
        section, _, _ = self._place_new_section("rich_text")
        starting_revision = self.draft.edit_revision
        response = self._post_json({
            "base_revision": starting_revision,
            "mutation": {"type": "section.move", "section_id": section.pk, "direction": "sideways"},
        })
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "invalid_direction")
        self.assertEqual(self._refresh_revision(), starting_revision)


class MoveSectionCrossCellTests(R4VerticalSliceTestCase):
    def test_move_down_swaps_across_two_single_cell_containers(self):
        section_a, container_a, cell_a = self._place_new_section("rich_text")
        section_b, container_b, cell_b = self._place_new_section("faq")

        starting_revision = self.draft.edit_revision
        response = self._post_json({
            "base_revision": starting_revision,
            "mutation": {"type": "section.move", "section_id": section_a.pk, "direction": "down"},
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self._refresh_revision(), starting_revision + 1)

        self.assertEqual(self.home_page.sections.count(), 2)
        self.assertTrue(StorefrontContainer.objects.filter(pk=container_a.pk).exists())
        self.assertTrue(StorefrontContainer.objects.filter(pk=container_b.pk).exists())
        self.assertTrue(StorefrontCell.objects.filter(pk=cell_a.pk).exists())
        self.assertTrue(StorefrontCell.objects.filter(pk=cell_b.pk).exists())

        cell_a.refresh_from_db()
        cell_b.refresh_from_db()
        self.assertEqual([blk.pk for blk in container_service.get_cell_blocks(cell_a)], [section_b.pk])
        self.assertEqual([blk.pk for blk in container_service.get_cell_blocks(cell_b)], [section_a.pk])

    def test_move_with_sibling_in_source_cell(self):
        section_a, container_a, cell_a = self._place_new_section("rich_text")
        sibling = StorefrontSection.objects.create(
            page=self.home_page, section_key="faq", order=self.home_page.sections.count(),
        )
        container_service.add_block(cell_a, sibling, at_index=0)  # sibling, then section_a
        section_target, container_target, cell_target = self._place_new_section("faq")

        response = self._post_json({
            "base_revision": self.draft.edit_revision,
            "mutation": {"type": "section.move", "section_id": section_a.pk, "direction": "down"},
        })
        self.assertEqual(response.status_code, 200)
        cell_a.refresh_from_db()
        cell_target.refresh_from_db()
        self.assertEqual(
            [blk.pk for blk in container_service.get_cell_blocks(cell_a)],
            [sibling.pk, section_target.pk],
        )
        self.assertEqual(
            [blk.pk for blk in container_service.get_cell_blocks(cell_target)],
            [section_a.pk],
        )

    def test_move_rejects_locked_source_container(self):
        section_a, container_a, _ = self._place_new_section("rich_text")
        self._place_new_section("faq")
        container_a.is_locked = True
        container_a.save(update_fields=["is_locked"])
        starting_revision = self.draft.edit_revision
        response = self._post_json({
            "base_revision": starting_revision,
            "mutation": {"type": "section.move", "section_id": section_a.pk, "direction": "down"},
        })
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "container_locked")
        self.assertEqual(self._refresh_revision(), starting_revision)

    def test_move_rejects_locked_target_container(self):
        section_a, _, _ = self._place_new_section("rich_text")
        _, container_target, _ = self._place_new_section("faq")
        container_target.is_locked = True
        container_target.save(update_fields=["is_locked"])
        starting_revision = self.draft.edit_revision
        response = self._post_json({
            "base_revision": starting_revision,
            "mutation": {"type": "section.move", "section_id": section_a.pk, "direction": "down"},
        })
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "target_container_locked")
        self.assertEqual(self._refresh_revision(), starting_revision)

    def test_move_rejects_locked_source_section(self):
        section_a, _, _ = self._place_new_section("rich_text", is_locked=True)
        self._place_new_section("faq")
        starting_revision = self.draft.edit_revision
        response = self._post_json({
            "base_revision": starting_revision,
            "mutation": {"type": "section.move", "section_id": section_a.pk, "direction": "down"},
        })
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "section_locked")
        self.assertEqual(self._refresh_revision(), starting_revision)

    def test_move_rejects_locked_adjacent_target_section(self):
        section_a, _, _ = self._place_new_section("rich_text")
        self._place_new_section("faq", is_locked=True)
        starting_revision = self.draft.edit_revision
        response = self._post_json({
            "base_revision": starting_revision,
            "mutation": {"type": "section.move", "section_id": section_a.pk, "direction": "down"},
        })
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "target_locked")
        self.assertEqual(self._refresh_revision(), starting_revision)

    def test_move_rejects_row_layout_invalid(self):
        # a (no row_key) sits immediately before a valid, contiguous
        # 2-member "promo-row" (b, c). Moving a down would swap its
        # page-level order with b's, sandwiching a between b and c in the
        # simulated page order — breaking the row's contiguity.
        section_a, _, _ = self._place_new_section("rich_text")
        self._place_new_section("faq", row_key="promo-row", row_span=6)
        self._place_new_section("faq", row_key="promo-row", row_span=6)
        starting_revision = self.draft.edit_revision
        response = self._post_json({
            "base_revision": starting_revision,
            "mutation": {"type": "section.move", "section_id": section_a.pk, "direction": "down"},
        })
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "row_layout_invalid")
        self.assertEqual(self._refresh_revision(), starting_revision)

    def test_stale_replay_returns_409_and_no_structural_change(self):
        section_a, _, cell_a = self._place_new_section("rich_text")
        self._place_new_section("faq")
        starting_revision = self.draft.edit_revision
        self._post_json({
            "base_revision": starting_revision,
            "mutation": {"type": "section.move", "section_id": section_a.pk, "direction": "down"},
        })
        cell_a.refresh_from_db()
        state_after_first = [blk.pk for blk in container_service.get_cell_blocks(cell_a)]
        response = self._post_json({
            "base_revision": starting_revision,
            "mutation": {"type": "section.move", "section_id": section_a.pk, "direction": "down"},
        })
        self.assertEqual(response.status_code, 409)
        cell_a.refresh_from_db()
        self.assertEqual([blk.pk for blk in container_service.get_cell_blocks(cell_a)], state_after_first)


class TenantAndScopeSecurityTests(R4VerticalSliceTestCase):
    def test_gate_off_makes_mutation_endpoint_unavailable(self):
        self.layout.r4_editor_enabled = False
        self.layout.save(update_fields=["r4_editor_enabled"])
        response = self._post_json({
            "base_revision": self.draft.edit_revision,
            "mutation": {"type": "section.add", "section_key": "rich_text"},
        })
        self.assertEqual(response.status_code, 404)

    def test_foreign_store_section_cannot_be_removed(self):
        other_store = Store.objects.create(
            name="فروشگاه دیگر", slug="r4-vslice-other-store",
            admin_subdomain="r4-vslice-other-store",
        )
        from apps.storefront_builder.services import layout_service as svc
        other_draft = svc.get_or_create_draft(other_store)
        other_page = other_draft.get_page(StorefrontPage.PageType.HOME)
        other_section = StorefrontSection.objects.create(
            page=other_page, section_key="rich_text", order=0,
        )
        starting_revision = self.draft.edit_revision
        response = self._post_json({
            "base_revision": starting_revision,
            "mutation": {"type": "section.remove", "section_id": other_section.pk},
        })
        self.assertEqual(response.status_code, 400)
        self.assertTrue(StorefrontSection.objects.filter(pk=other_section.pk).exists())
        self.assertEqual(self._refresh_revision(), starting_revision)

    def test_published_version_section_cannot_be_mutated(self):
        published = StorefrontLayoutVersion.objects.create(
            layout=self.layout, version_number=999,
            status=StorefrontLayoutVersion.Status.PUBLISHED,
        )
        StorefrontPage.ensure_version_pages(published)
        published_page = published.get_page(StorefrontPage.PageType.HOME)
        published_section = StorefrontSection.objects.create(
            page=published_page, section_key="rich_text", order=0,
        )
        starting_revision = self.draft.edit_revision
        response = self._post_json({
            "base_revision": starting_revision,
            "mutation": {"type": "section.remove", "section_id": published_section.pk},
        })
        self.assertEqual(response.status_code, 400)
        self.assertTrue(StorefrontSection.objects.filter(pk=published_section.pk).exists())
        self.assertEqual(self._refresh_revision(), starting_revision)

    def test_other_page_section_cannot_be_structurally_changed_via_crafted_id(self):
        product_page = self.draft.get_page(StorefrontPage.PageType.PRODUCT_DETAIL)
        product_section = StorefrontSection.objects.create(
            page=product_page, section_key="product_main", order=0,
        )
        starting_revision = self.draft.edit_revision
        response = self._post_json({
            "base_revision": starting_revision,
            "mutation": {"type": "section.remove", "section_id": product_section.pk},
        })
        self.assertEqual(response.status_code, 400)
        self.assertTrue(StorefrontSection.objects.filter(pk=product_section.pk).exists())
        self.assertEqual(self._refresh_revision(), starting_revision)
