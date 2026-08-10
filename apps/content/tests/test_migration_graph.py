"""Regression test for StoryRailItem migration dependencies.

This test would FAIL against commits before this fix where
content.0018_storyrailitem declared a nonexistent dependency:
    ("storefront_builder", "0007_subscriptioncreditnote_subscriptionrefund_and_more")

That migration only exists in the billing app, not storefront_builder.
The correct dependency is:
    ("storefront_builder", "0003_storefrontlayoutversion_appearance_config")
"""

import os
import unittest


class StoryRailMigrationDependencyTest(unittest.TestCase):
    """Static verification that content.0018_storyrailitem dependencies resolve."""

    MIGRATION_FILE = os.path.join(
        os.path.dirname(__file__), "..", "migrations", "0018_storyrailitem.py"
    )

    # All migration files that must exist for the dependency graph to be valid
    REQUIRED_DEPENDENCY_FILES = {
        ("content", "0017_scope_hero_slides_and_banners_to_section"):
            "apps/content/migrations/0017_scope_hero_slides_and_banners_to_section.py",
        ("stores", "0001_initial"):
            "apps/stores/migrations/0001_initial.py",
        ("storefront_builder", "0003_storefrontlayoutversion_appearance_config"):
            "apps/storefront_builder/migrations/0003_storefrontlayoutversion_appearance_config.py",
        ("catalog", "0036_merchantcollection_source_legacy_product_tag"):
            "apps/catalog/migrations/0036_merchantcollection_source_legacy_product_tag.py",
    }

    # The invalid dependency that caused the original failure
    INVALID_DEPENDENCY = ("storefront_builder", "0007_subscriptioncreditnote_subscriptionrefund_and_more")

    # Fields that must exist with correct names (not the wrong names from the broken version)
    REQUIRED_FIELD_NAMES = {
        "open_in_new_tab",  # NOT "destination_open_new_tab"
        "destination_type",
        "destination_external_url",
        "destination_category",
        "destination_product",
        "destination_brand",
        "destination_collection",
        "title",
        "image",
        "is_active",
        "display_order",
        "store",
        "section",
    }
    WRONG_FIELD_NAMES = {
        "destination_open_new_tab",  # was wrongly used in the first version
    }

    def _repo_root(self):
        """Find the repository root (contains manage.py)."""
        path = os.path.dirname(os.path.abspath(__file__))
        for _ in range(10):
            if os.path.exists(os.path.join(path, "manage.py")):
                return path
            path = os.path.dirname(path)
        return os.path.dirname(os.path.abspath(__file__))

    def test_migration_file_exists(self):
        """0018_storyrailitem.py exists."""
        path = os.path.normpath(self.MIGRATION_FILE)
        self.assertTrue(os.path.isfile(path), f"Migration file not found: {path}")

    def test_invalid_dependency_not_present(self):
        """The broken dependency must NOT appear in the migration source."""
        path = os.path.normpath(self.MIGRATION_FILE)
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        invalid_name = self.INVALID_DEPENDENCY[1]
        self.assertNotIn(
            invalid_name, content,
            f"Migration still references nonexistent '{invalid_name}'"
        )

    def test_correct_storefront_builder_dependency(self):
        """The migration must depend on storefront_builder.0003 (latest real migration)."""
        path = os.path.normpath(self.MIGRATION_FILE)
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn(
            "0003_storefrontlayoutversion_appearance_config", content,
            "Migration must depend on storefront_builder.0003"
        )

    def test_all_dependency_files_exist(self):
        """Every declared dependency must point to an existing migration file."""
        root = self._repo_root()
        for (app, name), rel_path in self.REQUIRED_DEPENDENCY_FILES.items():
            full_path = os.path.join(root, rel_path)
            self.assertTrue(
                os.path.isfile(full_path),
                f"Dependency ({app}, {name}) file not found: {full_path}"
            )

    def test_content_previous_migration_dependency(self):
        """The migration must depend on content.0017 (its predecessor)."""
        path = os.path.normpath(self.MIGRATION_FILE)
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn(
            "0017_scope_hero_slides_and_banners_to_section", content,
            "Migration must chain from content.0017"
        )

    def test_storyrailitem_in_operations(self):
        """StoryRailItem CreateModel must be present in operations."""
        path = os.path.normpath(self.MIGRATION_FILE)
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("StoryRailItem", content)
        self.assertIn("CreateModel", content)

    def test_no_billing_app_dependency(self):
        """content.0018 must not depend on the billing app."""
        path = os.path.normpath(self.MIGRATION_FILE)
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertNotIn('"billing"', content)

    def test_uses_charfield_for_external_url(self):
        """destination_external_url must be CharField (not URLField) matching DestinationMixin."""
        path = os.path.normpath(self.MIGRATION_FILE)
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        # Must use CharField for destination_external_url (canonical pattern)
        self.assertIn("destination_external_url", content)
        # Must NOT use URLField (which was the broken version)
        lines = content.split("\n")
        for line in lines:
            if "destination_external_url" in line or ("external_url" in line and "models." in line):
                self.assertNotIn("URLField", line,
                                 "destination_external_url must be CharField, not URLField")

    def test_field_name_is_open_in_new_tab(self):
        """Field must be named 'open_in_new_tab' (not 'destination_open_new_tab')."""
        path = os.path.normpath(self.MIGRATION_FILE)
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn('"open_in_new_tab"', content)
        self.assertNotIn('"destination_open_new_tab"', content)

    def test_no_page_destination_type(self):
        """DestinationType does not include 'page' — must not appear in choices."""
        path = os.path.normpath(self.MIGRATION_FILE)
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        # 'page' was incorrectly included in the first version's choices
        self.assertNotIn('("page"', content)

    def test_all_required_fields_present(self):
        """All expected StoryRailItem fields exist in the migration."""
        path = os.path.normpath(self.MIGRATION_FILE)
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        for field_name in self.REQUIRED_FIELD_NAMES:
            self.assertIn(f'"{field_name}"', content,
                          f"Required field '{field_name}' not found in migration")

    def test_no_wrong_field_names(self):
        """Wrong field names must not appear."""
        path = os.path.normpath(self.MIGRATION_FILE)
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        for field_name in self.WRONG_FIELD_NAMES:
            self.assertNotIn(f'"{field_name}"', content,
                             f"Wrong field name '{field_name}' still in migration")

    def test_catalog_dependency_for_destination_fks(self):
        """Migration must depend on catalog app (for Product/Category/Brand/Collection FKs)."""
        path = os.path.normpath(self.MIGRATION_FILE)
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn('"catalog"', content,
                      "Migration must have a catalog dependency for destination FKs")


class CatalogNewMigrationsTest(unittest.TestCase):
    """Verify catalog migrations 0037/0038 have valid dependency chains."""

    def _repo_root(self):
        path = os.path.dirname(os.path.abspath(__file__))
        for _ in range(10):
            if os.path.exists(os.path.join(path, "manage.py")):
                return path
            path = os.path.dirname(path)
        return os.path.dirname(os.path.abspath(__file__))

    def test_0037_depends_on_existing_0036(self):
        root = self._repo_root()
        dep_file = os.path.join(root, "apps/catalog/migrations/0036_merchantcollection_source_legacy_product_tag.py")
        self.assertTrue(os.path.isfile(dep_file))

    def test_0038_depends_on_existing_0037(self):
        root = self._repo_root()
        dep_file = os.path.join(root, "apps/catalog/migrations/0037_category_image.py")
        self.assertTrue(os.path.isfile(dep_file))
