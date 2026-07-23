from django.template.loader import render_to_string
from django.test import Client, TestCase, override_settings


@override_settings(DEBUG=False, ALLOWED_HOSTS=["testserver"])
class Custom404Tests(TestCase):
    def test_unknown_url_renders_custom_404_page(self):
        response = self.client.get("/this-path-does-not-exist/")
        self.assertEqual(response.status_code, 404)
        self.assertContains(response, "۴۰۴", status_code=404)
        self.assertContains(response, "این صفحه پیدا نشد", status_code=404)

    def test_404_page_includes_real_site_header(self):
        """۴۰۴ باید base.html را extend کند تا هدر/فوتر واقعی سایت (با context processors) نمایش داده شود."""
        response = self.client.get("/this-path-does-not-exist/")
        self.assertContains(response, "دیجی‌مارکت", status_code=404)


class Custom500TemplateTests(TestCase):
    def test_500_template_renders_without_any_context(self):
        """مطابق رفتار واقعی django.views.defaults.server_error که template.render() را بدون context صدا می‌زند."""
        html = render_to_string("500.html")
        self.assertIn("۵۰۰", html)
        self.assertIn("خطایی در سرور رخ داد", html)

    def test_500_template_does_not_reference_context_processor_variables(self):
        html = render_to_string("500.html")
        self.assertNotIn("{{", html)
