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
    }

    # The invalid dependency that caused the original failure
    INVALID_DEPENDENCY = ("storefront_builder", "0007_subscriptioncreditnote_subscriptionrefund_and_more")

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
