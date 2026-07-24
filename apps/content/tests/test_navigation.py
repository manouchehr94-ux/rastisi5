"""تست‌های مدیریت منوهای ناوبری — مدل، داشبورد، فروشگاه."""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.db.models import ProtectedError
from django.test import TestCase
from django.urls import reverse

from apps.catalog.models import Category, Product, Vendor
from apps.content.models import DestinationType, Menu, MenuItem

User = get_user_model()


# ============================================================ MENU MODEL TESTS


class MenuModelTests(TestCase):
    def test_valid_creation(self):
        menu = Menu.objects.create(title="منوی اصلی", location="header")
        self.assertTrue(menu.pk)

    def test_unique_location(self):
        Menu.objects.create(title="M1", location="header")
        with self.assertRaises(IntegrityError):
            Menu.objects.create(title="M2", location="header")

    def test_required_title(self):
        menu = Menu(title="", location="footer_1")
        with self.assertRaises(ValidationError):
            menu.full_clean()

    def test_active_default(self):
        menu = Menu.objects.create(title="T", location="mobile")
        self.assertTrue(menu.is_active)

    def test_ordering_by_location(self):
        Menu.objects.create(title="Footer", location="footer_1")
        Menu.objects.create(title="Header", location="header")
        locations = list(Menu.objects.values_list("location", flat=True))
        self.assertEqual(locations[0], "footer_1")  # f < h alphabetically

    def test_persian_labels(self):
        menu = Menu(title="T", location="header")
        self.assertEqual(menu.get_location_display(), "منوی اصلی")

    def test_str_representation(self):
        menu = Menu(title="فوتر ۱", location="footer_1")
        self.assertIn("فوتر ۱", str(menu))


# ============================================================ MENU ITEM MODEL TESTS


class MenuItemModelTests(TestCase):
    def setUp(self):
        self.menu = Menu.objects.create(title="Header", location="header")
        self.vendor = Vendor.objects.create(name="V", slug="v-nav")
        self.category = Category.objects.create(name="Cat", slug="cat-nav")

    def test_valid_top_level_item(self):
        item = MenuItem.objects.create(
            menu=self.menu, title="Home",
            destination_type="category", destination_category=self.category,
        )
        self.assertTrue(item.pk)
        self.assertIsNone(item.parent)

    def test_valid_child_item(self):
        parent = MenuItem.objects.create(
            menu=self.menu, title="Parent",
            destination_type="category", destination_category=self.category,
        )
        child = MenuItem.objects.create(
            menu=self.menu, title="Child", parent=parent,
            destination_type="external", destination_external_url="https://example.com",
        )
        self.assertEqual(child.parent, parent)

    def test_same_menu_parent_required(self):
        other_menu = Menu.objects.create(title="Other", location="footer_1")
        parent = MenuItem.objects.create(
            menu=other_menu, title="Other Parent",
            destination_type="none",
        )
        item = MenuItem(
            menu=self.menu, title="Child", parent=parent,
            destination_type="none",
        )
        with self.assertRaises(ValidationError) as ctx:
            item.full_clean()
        self.assertIn("parent", ctx.exception.message_dict)

    def test_self_parent_rejected(self):
        item = MenuItem.objects.create(
            menu=self.menu, title="Self",
            destination_type="none",
        )
        item.parent = item
        with self.assertRaises(ValidationError) as ctx:
            item.full_clean()
        self.assertIn("parent", ctx.exception.message_dict)

    def test_grandchild_rejected(self):
        parent = MenuItem.objects.create(
            menu=self.menu, title="P", destination_type="none",
        )
        child = MenuItem.objects.create(
            menu=self.menu, title="C", parent=parent, destination_type="none",
        )
        grandchild = MenuItem(
            menu=self.menu, title="GC", parent=child, destination_type="none",
        )
        with self.assertRaises(ValidationError) as ctx:
            grandchild.full_clean()
        self.assertIn("parent", ctx.exception.message_dict)

    def test_item_with_children_cannot_become_child(self):
        parent = MenuItem.objects.create(
            menu=self.menu, title="P", destination_type="none",
        )
        MenuItem.objects.create(
            menu=self.menu, title="C", parent=parent, destination_type="none",
        )
        other_top = MenuItem.objects.create(
            menu=self.menu, title="OT", destination_type="none",
        )
        parent.parent = other_top
        with self.assertRaises(ValidationError) as ctx:
            parent.full_clean()
        self.assertIn("parent", ctx.exception.message_dict)

    def test_required_title(self):
        item = MenuItem(menu=self.menu, title="", destination_type="none")
        with self.assertRaises(ValidationError):
            item.full_clean()

    def test_stable_ordering(self):
        MenuItem.objects.create(menu=self.menu, title="B", destination_type="none", display_order=2)
        MenuItem.objects.create(menu=self.menu, title="A", destination_type="none", display_order=1)
        titles = list(MenuItem.objects.values_list("title", flat=True))
        self.assertEqual(titles, ["A", "B"])

    def test_destination_validation_reused(self):
        """DestinationMixin validation fires — category required when type=category."""
        item = MenuItem(
            menu=self.menu, title="X", destination_type="category",
        )
        with self.assertRaises(ValidationError):
            item.full_clean()

    def test_external_url_security(self):
        item = MenuItem(
            menu=self.menu, title="X",
            destination_type="external",
            destination_external_url="javascript:alert(1)",
        )
        with self.assertRaises(ValidationError):
            item.full_clean()

    def test_open_in_new_tab(self):
        item = MenuItem.objects.create(
            menu=self.menu, title="Ext",
            destination_type="external",
            destination_external_url="https://example.com",
            open_in_new_tab=True,
        )
        self.assertTrue(item.open_in_new_tab)

    def test_parent_protection_on_delete(self):
        parent = MenuItem.objects.create(
            menu=self.menu, title="P", destination_type="none",
        )
        MenuItem.objects.create(
            menu=self.menu, title="C", parent=parent, destination_type="none",
        )
        with self.assertRaises(ProtectedError):
            parent.delete()


# ============================================================ DASHBOARD ACCESS TESTS


class MenuDashboardAccessTests(TestCase):
    def setUp(self):
        self.staff = User.objects.create_user(username="staff_nav", password="p!", is_staff=True)
        self.non_staff = User.objects.create_user(username="user_nav", password="p!", is_staff=False)

    def test_anonymous_redirected(self):
        response = self.client.get(reverse("dashboard:menu-list"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin-panel/login/", response.url)

    def test_non_staff_rejected(self):
        self.client.login(username="user_nav", password="p!")
        response = self.client.get(reverse("dashboard:menu-list"))
        self.assertEqual(response.status_code, 302)

    def test_staff_allowed(self):
        self.client.login(username="staff_nav", password="p!")
        response = self.client.get(reverse("dashboard:menu-list"))
        self.assertEqual(response.status_code, 200)

    def test_menu_create_accessible(self):
        self.client.login(username="staff_nav", password="p!")
        response = self.client.get(reverse("dashboard:menu-add"))
        self.assertEqual(response.status_code, 200)

    def test_menu_edit_accessible(self):
        self.client.login(username="staff_nav", password="p!")
        menu = Menu.objects.create(title="T", location="header")
        response = self.client.get(reverse("dashboard:menu-edit", args=[menu.pk]))
        self.assertEqual(response.status_code, 200)

    def test_item_management_accessible(self):
        self.client.login(username="staff_nav", password="p!")
        menu = Menu.objects.create(title="T", location="header")
        response = self.client.get(reverse("dashboard:menu-item-list", args=[menu.pk]))
        self.assertEqual(response.status_code, 200)

    def test_delete_requires_post(self):
        self.client.login(username="staff_nav", password="p!")
        menu = Menu.objects.create(title="T", location="header")
        response = self.client.get(reverse("dashboard:menu-delete", args=[menu.pk]))
        self.assertEqual(response.status_code, 405)

    def test_toggle_requires_post(self):
        self.client.login(username="staff_nav", password="p!")
        menu = Menu.objects.create(title="T", location="header")
        response = self.client.get(reverse("dashboard:menu-toggle", args=[menu.pk]))
        self.assertEqual(response.status_code, 405)

    def test_item_delete_requires_post(self):
        self.client.login(username="staff_nav", password="p!")
        menu = Menu.objects.create(title="T", location="header")
        item = MenuItem.objects.create(menu=menu, title="I", destination_type="none")
        response = self.client.get(reverse("dashboard:menu-item-delete", args=[item.pk]))
        self.assertEqual(response.status_code, 405)

    def test_item_toggle_requires_post(self):
        self.client.login(username="staff_nav", password="p!")
        menu = Menu.objects.create(title="T", location="header")
        item = MenuItem.objects.create(menu=menu, title="I", destination_type="none")
        response = self.client.get(reverse("dashboard:menu-item-toggle", args=[item.pk]))
        self.assertEqual(response.status_code, 405)


# ============================================================ DASHBOARD CRUD TESTS


class MenuDashboardCRUDTests(TestCase):
    def setUp(self):
        self.staff = User.objects.create_user(username="staff_mc", password="p!", is_staff=True)
        self.client.login(username="staff_mc", password="p!")

    def test_create_menu(self):
        response = self.client.post(reverse("dashboard:menu-add"), {
            "title": "منوی هدر", "location": "header", "is_active": "on",
        })
        self.assertRedirects(response, reverse("dashboard:menu-list"))
        self.assertTrue(Menu.objects.filter(title="منوی هدر").exists())

    def test_edit_menu(self):
        menu = Menu.objects.create(title="Old", location="footer_1")
        self.client.post(reverse("dashboard:menu-edit", args=[menu.pk]), {
            "title": "New Title", "location": "footer_1", "is_active": "on",
        })
        menu.refresh_from_db()
        self.assertEqual(menu.title, "New Title")

    def test_delete_empty_menu(self):
        menu = Menu.objects.create(title="Empty", location="footer_2")
        self.client.post(reverse("dashboard:menu-delete", args=[menu.pk]))
        self.assertFalse(Menu.objects.filter(pk=menu.pk).exists())

    def test_prevent_deleting_populated_menu(self):
        menu = Menu.objects.create(title="Full", location="footer_3")
        MenuItem.objects.create(menu=menu, title="I", destination_type="none")
        self.client.post(reverse("dashboard:menu-delete", args=[menu.pk]))
        self.assertTrue(Menu.objects.filter(pk=menu.pk).exists())

    def test_toggle_menu(self):
        menu = Menu.objects.create(title="T", location="header", is_active=True)
        self.client.post(reverse("dashboard:menu-toggle", args=[menu.pk]))
        menu.refresh_from_db()
        self.assertFalse(menu.is_active)

    def test_create_item(self):
        menu = Menu.objects.create(title="M", location="header")
        cat = Category.objects.create(name="C", slug="c-nav-crud")
        response = self.client.post(reverse("dashboard:menu-item-add", args=[menu.pk]), {
            "title": "New Item", "display_order": "0", "is_active": "on",
            "destination_type": "category", "destination_category": str(cat.pk),
            "destination_external_url": "", "destination_product": "", "destination_brand": "",
        })
        self.assertRedirects(response, reverse("dashboard:menu-item-list", args=[menu.pk]))
        self.assertTrue(MenuItem.objects.filter(title="New Item").exists())

    def test_edit_item(self):
        menu = Menu.objects.create(title="M", location="header")
        cat = Category.objects.create(name="EC", slug="ec-edit")
        item = MenuItem.objects.create(
            menu=menu, title="Old", destination_type="category",
            destination_category=cat,
        )
        self.client.post(reverse("dashboard:menu-item-edit", args=[item.pk]), {
            "title": "Updated", "display_order": "5", "is_active": "on",
            "destination_type": "category", "destination_category": str(cat.pk),
            "destination_external_url": "",
            "destination_product": "", "destination_brand": "",
            "parent": "",
        })
        item.refresh_from_db()
        self.assertEqual(item.title, "Updated")
        self.assertEqual(item.display_order, 5)

    def test_delete_leaf_item(self):
        menu = Menu.objects.create(title="M", location="header")
        item = MenuItem.objects.create(menu=menu, title="Leaf", destination_type="none")
        self.client.post(reverse("dashboard:menu-item-delete", args=[item.pk]))
        self.assertFalse(MenuItem.objects.filter(pk=item.pk).exists())

    def test_prevent_deleting_parent_with_children(self):
        menu = Menu.objects.create(title="M", location="header")
        parent = MenuItem.objects.create(menu=menu, title="P", destination_type="none")
        MenuItem.objects.create(menu=menu, title="C", parent=parent, destination_type="none")
        self.client.post(reverse("dashboard:menu-item-delete", args=[parent.pk]))
        # Parent should still exist
        self.assertTrue(MenuItem.objects.filter(pk=parent.pk).exists())

    def test_toggle_item(self):
        menu = Menu.objects.create(title="M", location="header")
        item = MenuItem.objects.create(menu=menu, title="I", destination_type="none", is_active=True)
        self.client.post(reverse("dashboard:menu-item-toggle", args=[item.pk]))
        item.refresh_from_db()
        self.assertFalse(item.is_active)

    def test_invalid_parent_rejected(self):
        menu = Menu.objects.create(title="M", location="header")
        other_menu = Menu.objects.create(title="O", location="footer_1")
        other_parent = MenuItem.objects.create(menu=other_menu, title="OP", destination_type="none")
        response = self.client.post(reverse("dashboard:menu-item-add", args=[menu.pk]), {
            "title": "Bad", "display_order": "0", "is_active": "on",
            "destination_type": "none", "destination_external_url": "",
            "destination_category": "", "destination_product": "", "destination_brand": "",
            "parent": str(other_parent.pk),
        })
        # Should not create — stays on form with error
        self.assertFalse(MenuItem.objects.filter(title="Bad").exists())

    def test_invalid_destination_rejected(self):
        menu = Menu.objects.create(title="M", location="header")
        response = self.client.post(reverse("dashboard:menu-item-add", args=[menu.pk]), {
            "title": "Bad", "display_order": "0", "is_active": "on",
            "destination_type": "external",
            "destination_external_url": "javascript:alert(1)",
            "destination_category": "", "destination_product": "", "destination_brand": "",
        })
        self.assertFalse(MenuItem.objects.filter(title="Bad").exists())

    def test_duplicate_location_rejected(self):
        Menu.objects.create(title="M1", location="header")
        response = self.client.post(reverse("dashboard:menu-add"), {
            "title": "M2", "location": "header", "is_active": "on",
        })
        # Should stay on form with error — only 1 header menu
        self.assertEqual(Menu.objects.filter(location="header").count(), 1)


# ============================================================ STOREFRONT TESTS


class NavigationStorefrontTests(TestCase):
    def setUp(self):
        self.category = Category.objects.create(name="Electronics", slug="electronics-nav")

    def test_header_menu_renders(self):
        menu = Menu.objects.create(title="Header", location="header", is_active=True)
        MenuItem.objects.create(
            menu=menu, title="فروشگاه",
            destination_type="category", destination_category=self.category,
            is_active=True, display_order=0,
        )
        response = self.client.get("/")
        self.assertContains(response, "فروشگاه")
        self.assertContains(response, "category=electronics-nav")

    def test_footer_menu_renders(self):
        menu = Menu.objects.create(title="Quick", location="footer_1", is_active=True)
        MenuItem.objects.create(
            menu=menu, title="درباره ما",
            destination_type="external",
            destination_external_url="https://example.com/about",
            is_active=True,
        )
        response = self.client.get("/")
        self.assertContains(response, "درباره ما")
        self.assertContains(response, "https://example.com/about")

    def test_inactive_menu_hidden(self):
        menu = Menu.objects.create(title="Hidden", location="header", is_active=False)
        MenuItem.objects.create(
            menu=menu, title="ShouldNotShow",
            destination_type="external",
            destination_external_url="https://hidden.com",
            is_active=True,
        )
        response = self.client.get("/")
        self.assertNotContains(response, "ShouldNotShow")

    def test_inactive_item_hidden(self):
        menu = Menu.objects.create(title="H", location="header", is_active=True)
        MenuItem.objects.create(
            menu=menu, title="ActiveItem",
            destination_type="category", destination_category=self.category,
            is_active=True,
        )
        MenuItem.objects.create(
            menu=menu, title="InactiveItem",
            destination_type="external",
            destination_external_url="https://hidden.com",
            is_active=False,
        )
        response = self.client.get("/")
        self.assertContains(response, "ActiveItem")
        self.assertNotContains(response, "InactiveItem")

    def test_inactive_parent_hides_child(self):
        menu = Menu.objects.create(title="H", location="header", is_active=True)
        parent = MenuItem.objects.create(
            menu=menu, title="Parent",
            destination_type="category", destination_category=self.category,
            is_active=False,
        )
        MenuItem.objects.create(
            menu=menu, title="ChildOfInactive", parent=parent,
            destination_type="external",
            destination_external_url="https://child.com",
            is_active=True,
        )
        response = self.client.get("/")
        self.assertNotContains(response, "ChildOfInactive")

    def test_top_level_ordering(self):
        menu = Menu.objects.create(title="H", location="header", is_active=True)
        MenuItem.objects.create(
            menu=menu, title="Second",
            destination_type="external", destination_external_url="https://b.com",
            is_active=True, display_order=2,
        )
        MenuItem.objects.create(
            menu=menu, title="First",
            destination_type="external", destination_external_url="https://a.com",
            is_active=True, display_order=1,
        )
        response = self.client.get("/")
        content = response.content.decode()
        self.assertLess(content.find("First"), content.find("Second"))

    def test_external_target_rel_safe(self):
        menu = Menu.objects.create(title="H", location="header", is_active=True)
        MenuItem.objects.create(
            menu=menu, title="Ext",
            destination_type="external",
            destination_external_url="https://example.com",
            open_in_new_tab=True, is_active=True,
        )
        response = self.client.get("/")
        self.assertContains(response, 'target="_blank"')
        self.assertContains(response, 'rel="noopener noreferrer"')

    def test_internal_no_new_tab(self):
        menu = Menu.objects.create(title="H", location="header", is_active=True)
        MenuItem.objects.create(
            menu=menu, title="Internal",
            destination_type="category", destination_category=self.category,
            open_in_new_tab=False, is_active=True,
        )
        response = self.client.get("/")
        # Should NOT have target="_blank" for this internal link
        content = response.content.decode()
        idx = content.find("Internal")
        # Get the link around it
        link_start = content.rfind("<a", 0, idx)
        link_end = content.find(">", idx)
        link_tag = content[link_start:link_end]
        self.assertNotIn('target="_blank"', link_tag)

    def test_escaped_item_title(self):
        menu = Menu.objects.create(title="H", location="header", is_active=True)
        MenuItem.objects.create(
            menu=menu, title='<script>xss</script>',
            destination_type="external",
            destination_external_url="https://example.com",
            is_active=True,
        )
        response = self.client.get("/")
        self.assertNotContains(response, '<script>xss</script>')
        self.assertContains(response, "&lt;script&gt;")

    def test_empty_header_no_managed_links(self):
        """No header menu → no nav links in nav-links-scroll (no hardcoded fallback)."""
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        # The nav-links-scroll should not contain any <a class="nl" links
        import re
        nav_match = re.search(r'<div class="nav-links-scroll">(.*?)</div>', content, re.DOTALL)
        if nav_match:
            inner = nav_match.group(1)
            self.assertNotIn('class="nl"', inner)

    def test_no_hardcoded_when_managed_header(self):
        """When managed header exists, no fallback links appear."""
        menu = Menu.objects.create(title="H", location="header", is_active=True)
        MenuItem.objects.create(
            menu=menu, title="ManagedLink",
            destination_type="external",
            destination_external_url="https://managed.com",
            is_active=True,
        )
        response = self.client.get("/")
        self.assertContains(response, "ManagedLink")
        content = response.content.decode()
        # Should not have the old hardcoded "برندها" link in nav area
        import re
        nav_match = re.search(r'<div class="nav-links-scroll">(.*?)</div>', content, re.DOTALL)
        if nav_match:
            self.assertNotIn("برندها", nav_match.group(1))

    def test_invalid_destination_does_not_crash(self):
        """Item with deleted category → skipped, page doesn't crash."""
        menu = Menu.objects.create(title="H", location="header", is_active=True)
        MenuItem.objects.create(
            menu=menu, title="Stale",
            destination_type="category",
            destination_category=None,  # Simulates SET_NULL
            is_active=True,
        )
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Stale")

    def test_footer_locations_independent(self):
        """Footer menus render independently."""
        menu1 = Menu.objects.create(title="F1", location="footer_1", is_active=True)
        menu2 = Menu.objects.create(title="F2", location="footer_2", is_active=True)
        cat = self.category
        MenuItem.objects.create(menu=menu1, title="Link1", destination_type="category", destination_category=cat, is_active=True)
        MenuItem.objects.create(menu=menu2, title="Link2", destination_type="external", destination_external_url="https://f2.com", is_active=True)
        response = self.client.get("/")
        self.assertContains(response, "Link1")
        self.assertContains(response, "Link2")
        self.assertContains(response, "F1")
        self.assertContains(response, "F2")




# ============================================================ FALLBACK REMOVAL TESTS


class NavigationFallbackRemovalTests(TestCase):
    """تست‌های حذف fallback — مدیر کنترل کامل دارد."""

    def test_inactive_header_menu_no_fallback(self):
        """Inactive header menu → no nav links at all."""
        menu = Menu.objects.create(title="H", location="header", is_active=False)
        MenuItem.objects.create(
            menu=menu, title="Should Not Show",
            destination_type="external", destination_external_url="https://x.com",
            is_active=True,
        )
        response = self.client.get("/")
        self.assertNotContains(response, "Should Not Show")
        content = response.content.decode()
        import re
        nav_match = re.search(r'<div class="nav-links-scroll">(.*?)</div>', content, re.DOTALL)
        if nav_match:
            self.assertNotIn('class="nl"', nav_match.group(1))

    def test_empty_active_header_no_wrapper(self):
        """Active header menu with no items → no nav links rendered."""
        Menu.objects.create(title="Empty", location="header", is_active=True)
        response = self.client.get("/")
        content = response.content.decode()
        import re
        nav_match = re.search(r'<div class="nav-links-scroll">(.*?)</div>', content, re.DOTALL)
        if nav_match:
            self.assertNotIn('class="nl"', nav_match.group(1))

    def test_no_footer_menu_no_column(self):
        """No footer_1 menu → no column rendered for that location."""
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        # No "دسترسی سریع" default heading should appear (removed)
        self.assertNotContains(response, "دسترسی سریع")

    def test_inactive_footer_menu_no_column(self):
        """Inactive footer menu → column not rendered."""
        menu = Menu.objects.create(title="F1", location="footer_1", is_active=False)
        MenuItem.objects.create(
            menu=menu, title="Hidden",
            destination_type="external", destination_external_url="https://x.com",
            is_active=True,
        )
        response = self.client.get("/")
        self.assertNotContains(response, "Hidden")

    def test_footer_menu_only_inactive_items_no_column(self):
        """Footer menu with only inactive/unresolvable items → column not rendered."""
        cat = Category.objects.create(name="FC", slug="fc-fr")
        menu = Menu.objects.create(title="F1", location="footer_1", is_active=True)
        MenuItem.objects.create(
            menu=menu, title="Inactive",
            destination_type="category", destination_category=cat,
            is_active=False,
        )
        response = self.client.get("/")
        # Menu title should not appear since no renderable items
        self.assertNotContains(response, "F1")

    def test_other_non_navigation_content_remains(self):
        """Non-navigation elements (newsletter, branding) remain."""
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "عضویت در خبرنامه")
        self.assertContains(response, "تماس با ما")


# ============================================================ DESTINATION POLICY TESTS


class DestinationPolicyTests(TestCase):
    """تست‌های سیاست مقصد آیتم‌های منو."""

    def setUp(self):
        self.menu = Menu.objects.create(title="T", location="header")
        self.category = Category.objects.create(name="DC", slug="dc-dp")

    def test_leaf_with_no_destination_rejected(self):
        """Leaf item (no parent, no children) with destination=none → rejected."""
        item = MenuItem(menu=self.menu, title="Leaf", destination_type="none")
        with self.assertRaises(ValidationError) as ctx:
            item.full_clean()
        self.assertIn("destination_type", ctx.exception.message_dict)

    def test_child_with_no_destination_rejected(self):
        """Child item with destination=none → rejected."""
        parent = MenuItem.objects.create(
            menu=self.menu, title="P",
            destination_type="category", destination_category=self.category,
        )
        child = MenuItem(
            menu=self.menu, title="C", parent=parent, destination_type="none",
        )
        with self.assertRaises(ValidationError) as ctx:
            child.full_clean()
        self.assertIn("destination_type", ctx.exception.message_dict)

    def test_parent_without_destination_with_children_allowed(self):
        """Parent (with children) and destination=none → allowed."""
        parent = MenuItem.objects.create(
            menu=self.menu, title="Heading", destination_type="none",
        )
        # Add a child so parent has children
        MenuItem.objects.create(
            menu=self.menu, title="Child", parent=parent,
            destination_type="category", destination_category=self.category,
        )
        # Re-validate parent — should pass since it has children
        parent.refresh_from_db()
        parent.full_clean()  # Should not raise

    def test_parent_without_destination_without_children_rejected(self):
        """Top-level item with no destination and no children → rejected."""
        item = MenuItem(menu=self.menu, title="Orphan", destination_type="none")
        with self.assertRaises(ValidationError):
            item.full_clean()

    def test_no_href_hash_in_storefront(self):
        """Storefront must never produce href='#' for menu items."""
        menu = Menu.objects.create(title="H", location="footer_1", is_active=True)
        MenuItem.objects.create(
            menu=menu, title="Valid",
            destination_type="category", destination_category=self.category,
            is_active=True,
        )
        response = self.client.get("/")
        content = response.content.decode()
        import re
        footer_match = re.search(r'<h5>H</h5>(.*?)</ul>', content, re.DOTALL)
        if footer_match:
            self.assertNotIn('href="#"', footer_match.group(1))

    def test_non_clickable_parent_renders_as_span(self):
        """Parent with no URL renders as <span>, not <a href='#'>."""
        # Use a location that won't conflict with setUp's header menu
        hmenu = Menu.objects.create(title="HH", location="footer_1", is_active=True)
        p = MenuItem.objects.create(menu=hmenu, title="HeadingItem", destination_type="none")
        MenuItem.objects.create(
            menu=hmenu, title="Sub", parent=p,
            destination_type="external", destination_external_url="https://sub.com",
            is_active=True,
        )
        response = self.client.get("/")
        content = response.content.decode()
        # HeadingItem has no URL so should not produce href="#"
        self.assertIn("HeadingItem", content)
        self.assertNotIn('href="#">HeadingItem', content)

    def test_exactly_one_destination_enforced(self):
        """Multiple destinations still rejected by DestinationMixin validation."""
        item = MenuItem(
            menu=self.menu, title="Multi",
            destination_type="category",
            destination_category=self.category,
            destination_external_url="https://x.com",
        )
        with self.assertRaises(ValidationError):
            item.full_clean()


# ============================================================ MENU DELETION PROTECTION TESTS


class MenuDeletionProtectionTests(TestCase):
    """تست‌های حفاظت حذف منو در سطح داده."""

    def setUp(self):
        self.staff = User.objects.create_user(username="staff_del", password="p!", is_staff=True)
        self.client.login(username="staff_del", password="p!")

    def test_orm_deletion_of_populated_menu_raises_protected(self):
        """Direct ORM deletion of menu with items → ProtectedError."""
        menu = Menu.objects.create(title="P", location="header")
        MenuItem.objects.create(menu=menu, title="I", destination_type="none")
        with self.assertRaises(ProtectedError):
            menu.delete()

    def test_dashboard_deletion_of_populated_menu_blocked(self):
        """Dashboard delete of populated menu → blocked with message."""
        menu = Menu.objects.create(title="P", location="footer_1")
        MenuItem.objects.create(menu=menu, title="I", destination_type="none")
        self.client.post(reverse("dashboard:menu-delete", args=[menu.pk]))
        self.assertTrue(Menu.objects.filter(pk=menu.pk).exists())

    def test_empty_menu_deletion_succeeds(self):
        """Empty menu can be deleted."""
        menu = Menu.objects.create(title="E", location="footer_2")
        self.client.post(reverse("dashboard:menu-delete", args=[menu.pk]))
        self.assertFalse(Menu.objects.filter(pk=menu.pk).exists())

    def test_items_remain_after_blocked_deletion(self):
        """Items remain intact after blocked menu deletion."""
        menu = Menu.objects.create(title="P", location="footer_3")
        item = MenuItem.objects.create(menu=menu, title="I", destination_type="none")
        self.client.post(reverse("dashboard:menu-delete", args=[menu.pk]))
        self.assertTrue(MenuItem.objects.filter(pk=item.pk).exists())

    def test_no_silent_cascade(self):
        """PROTECT prevents cascade — items survive."""
        menu = Menu.objects.create(title="P", location="mobile")
        item = MenuItem.objects.create(menu=menu, title="I", destination_type="none")
        try:
            menu.delete()
        except ProtectedError:
            pass
        self.assertTrue(MenuItem.objects.filter(pk=item.pk).exists())
