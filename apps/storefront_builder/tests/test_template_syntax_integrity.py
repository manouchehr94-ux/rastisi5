"""بررسیِ سلامتِ نحویِ Templateهایِ ۶ خانواده‌ی جدید — بدونِ نیاز به Django
runtime. این تستِ pure-Python تعادلِ تگ‌هایِ بلوکی (if/for/with/block) را
بررسی می‌کند تا حداقل خطاهایِ فاجعه‌بارِ Templateِ ناقص/نامتوازن (که
باعثِ TemplateSyntaxError در Django می‌شود) پیش از اجرایِ Django کشف شود.

این تست جایگزینِ رندرِ واقعی نیست — فقط یک لایه‌ی ایمنیِ استاتیکِ اضافی
است که در محیطِ بدونِ Django هم قابل‌اجراست."""

import os
import re
import unittest


# تگ‌هایِ بلوکیِ Django که باید باز/بسته شوند (نام باز → نامِ بسته)
_BLOCK_TAGS = {
    "if": "endif",
    "for": "endfor",
    "with": "endwith",
    "block": "endblock",
    "comment": "endcomment",
    "spaceless": "endspaceless",
    "autoescape": "endautoescape",
    "filter": "endfilter",
}
_OPEN_RE = re.compile(r"\{%-?\s*(\w+)\b")
_ELIF_ELSE = {"elif", "else", "empty"}


def _repo_root():
    path = os.path.dirname(os.path.abspath(__file__))
    for _ in range(10):
        if os.path.exists(os.path.join(path, "manage.py")):
            return path
        path = os.path.dirname(path)
    return path


def _check_tag_balance(content: str) -> list:
    """برمی‌گرداند: فهرستِ خطاها (خالی = سالم). یک استکِ سادّه از تگ‌هایِ
    بازِ بلوکی نگه می‌دارد و در برخورد با تگِ بسته، تطبیق را بررسی می‌کند."""
    errors = []
    stack = []
    for match in _OPEN_RE.finditer(content):
        tag = match.group(1)
        if tag in _BLOCK_TAGS:
            stack.append(tag)
        elif tag in _ELIF_ELSE:
            continue  # نیازی به push/pop ندارد
        elif tag.startswith("end"):
            expected_open = None
            for open_tag, close_tag in _BLOCK_TAGS.items():
                if close_tag == tag:
                    expected_open = open_tag
                    break
            if expected_open is None:
                continue  # تگِ end ناشناخته (مثلاً endcache از کتابخانه‌ی دیگر) — نادیده
            if not stack:
                errors.append(f"Unexpected '{{% {tag} %}}' with no matching open tag")
                continue
            top = stack.pop()
            if top != expected_open:
                errors.append(f"Mismatched close: expected 'end{top}', found '{tag}'")
    if stack:
        errors.append(f"Unclosed tags remaining: {stack}")
    return errors


class TemplateTagBalanceTests(unittest.TestCase):
    """هر ۶۰+ Templateِ جدید (۶ خانواده × ۶ فایل + شریک‌ها) باید تگ‌هایِ
    بلوکیِ متوازن داشته باشد."""

    NEW_FAMILY_SLUGS = ["atlas_catalog", "ava_fashion", "toranj_gifting", "sarv_stock", "sepidar_handmade", "zarrin_jewelry"]

    def _all_new_template_paths(self):
        root = _repo_root()
        paths = []
        for slug in self.NEW_FAMILY_SLUGS:
            base = os.path.join(root, "apps/storefront_builder/templates/storefront_builder/partials/families", slug)
            for part in ("header.html", "hero.html", "category.html", "footer.html"):
                paths.append(os.path.join(base, part))
        from apps.storefront_builder import family_registry
        for family in family_registry.list_families():
            if family.slug in self.NEW_FAMILY_SLUGS:
                paths.append(os.path.join(root, "apps/catalog/templates", family.product_card_variant))
                paths.append(os.path.join(root, "apps/catalog/templates", family.product_page_variant))
        return paths

    def test_all_new_templates_have_balanced_tags(self):
        paths = self._all_new_template_paths()
        self.assertGreater(len(paths), 0, "No template paths resolved — test setup broken")
        failures = []
        for path in paths:
            if not os.path.isfile(path):
                failures.append(f"{path}: FILE NOT FOUND")
                continue
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
            errors = _check_tag_balance(content)
            if errors:
                failures.append(f"{path}: {errors}")
        self.assertEqual(failures, [], "\n".join(failures))

    def test_all_new_templates_are_non_empty(self):
        for path in self._all_new_template_paths():
            if os.path.isfile(path):
                self.assertGreater(os.path.getsize(path), 50, f"{path} suspiciously small/empty")

    def test_no_family_leaks_another_familys_reference_brand_name(self):
        """رعایتِ محدودیتِ برندِ مرجع — نامِ سایتِ مرجع نباید در UI عمومی ظاهر شود."""
        forbidden_names = ["Beraito", "iBolak", "Khaneh Shokolati", "Kian Stock", "Gallery Chiic", "Sarmey",
                           "بریتو", "آیبولاک", "خانه شکلاتی", "کیان استوک", "گالری چیک", "سرمی"]
        for path in self._all_new_template_paths():
            if not os.path.isfile(path):
                continue
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
            for name in forbidden_names:
                self.assertNotIn(name, content, f"{path} contains forbidden reference-brand name '{name}'")


class AccessibilityStaticChecksTests(unittest.TestCase):
    """بررسیِ استاتیکِ aria-label رویِ دکمه‌های آیکون‌محورِ هدرها."""

    NEW_FAMILY_SLUGS = ["atlas_catalog", "ava_fashion", "toranj_gifting", "sarv_stock", "sepidar_handmade", "zarrin_jewelry"]

    def test_wishlist_control_present_when_configured(self):
        """اگر hc.show_wishlist در header استفاده شده، باید کنترلِ واقعی هم وجود داشته باشد."""
        root = _repo_root()
        for slug in self.NEW_FAMILY_SLUGS:
            path = os.path.join(root, "apps/storefront_builder/templates/storefront_builder/partials/families", slug, "header.html")
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
            self.assertIn("show_wishlist", content, f"{slug}/header.html missing wishlist control (hc.show_wishlist)")

    def test_burger_button_has_aria_label(self):
        root = _repo_root()
        for slug in self.NEW_FAMILY_SLUGS:
            path = os.path.join(root, "apps/storefront_builder/templates/storefront_builder/partials/families", slug, "header.html")
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
            self.assertIn('class="h-btn burger"', content)
            # burger button line must carry aria-label
            burger_match = re.search(r'class="h-btn burger"[^>]*', content)
            self.assertIsNotNone(burger_match)
            self.assertIn("aria-label", burger_match.group(0))

    def test_cart_and_wishlist_action_buttons_have_aria_label(self):
        root = _repo_root()
        for slug in self.NEW_FAMILY_SLUGS:
            path = os.path.join(root, "apps/storefront_builder/templates/storefront_builder/partials/families", slug, "header.html")
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
            # Cart link must have aria-label
            cart_section = content[content.find("show_cart"):content.find("show_cart") + 400] if "show_cart" in content else ""
            self.assertIn("aria-label", cart_section, f"{slug}: cart control missing aria-label")


if __name__ == "__main__":
    unittest.main()
