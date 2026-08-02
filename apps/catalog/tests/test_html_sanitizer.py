from django.test import SimpleTestCase

from apps.catalog.services.html_sanitizer import (
    render_description_html,
    sanitize_product_description,
    strip_to_text,
)


class SanitizeProductDescriptionTests(SimpleTestCase):
    def test_empty_input_returns_empty_string(self):
        self.assertEqual(sanitize_product_description(""), "")
        self.assertEqual(sanitize_product_description(None), "")

    def test_script_tag_and_content_are_removed(self):
        out = sanitize_product_description('<p onclick="alert(1)">hello <script>alert(2)</script></p>')
        self.assertNotIn("<script", out)
        self.assertNotIn("alert(2)", out)
        self.assertNotIn("onclick", out)
        self.assertIn("hello", out)

    def test_iframe_object_embed_removed_entirely(self):
        out = sanitize_product_description('<iframe src="evil"></iframe><p>after</p>')
        self.assertNotIn("<iframe", out)
        self.assertIn("<p>after</p>", out)

    def test_javascript_url_stripped_from_href(self):
        out = sanitize_product_description('<a href="javascript:alert(1)">bad</a>')
        self.assertNotIn("javascript:", out)

    def test_safe_https_link_with_target_blank_gets_noopener(self):
        out = sanitize_product_description('<a href="https://example.com" target="_blank">good</a>')
        self.assertIn('href="https://example.com"', out)
        self.assertIn("noopener", out)

    def test_onerror_attribute_stripped_from_img(self):
        out = sanitize_product_description('<img src="https://x.com/a.png" onerror="alert(1)" alt="x">')
        self.assertNotIn("onerror", out)
        self.assertIn('src="https://x.com/a.png"', out)

    def test_disallowed_style_properties_stripped_allowed_kept(self):
        out = sanitize_product_description(
            '<p style="color:red;position:absolute;background:url(javascript:alert(1))">styled</p>'
        )
        self.assertIn("color: red", out)
        self.assertNotIn("position", out)
        self.assertNotIn("url(", out)

    def test_table_structure_preserved(self):
        out = sanitize_product_description("<table><tr><td>cell</td></tr></table>")
        self.assertIn("<table>", out)
        self.assertIn("<td>cell</td>", out)

    def test_headings_and_lists_preserved(self):
        out = sanitize_product_description("<h2>Title</h2><ul><li>one</li><li>two</li></ul>")
        self.assertIn("<h2>Title</h2>", out)
        self.assertIn("<li>one</li>", out)


class RenderDescriptionHtmlTests(SimpleTestCase):
    def test_legacy_plain_text_newlines_become_br(self):
        out = render_description_html("خط اول\nخط دوم")
        self.assertIn("<br", out)
        self.assertIn("خط اول", out)
        self.assertIn("خط دوم", out)

    def test_rich_html_with_block_tags_passed_through_unchanged(self):
        raw = "<p>پاراگراف اول</p><p>پاراگراف دوم</p>"
        out = render_description_html(raw)
        self.assertEqual(out, raw)

    def test_still_sanitizes_dangerous_content(self):
        out = render_description_html('<script>alert(1)</script>plain text')
        self.assertNotIn("<script", out)
        self.assertIn("plain text", out)


class StripToTextTests(SimpleTestCase):
    def test_strips_tags_and_collapses_whitespace(self):
        self.assertEqual(strip_to_text("<p>Hello   <b>World</b></p>"), "Hello World")

    def test_truncates_to_max_length(self):
        out = strip_to_text("<p>" + ("a" * 500) + "</p>", max_length=50)
        self.assertEqual(len(out), 50)
