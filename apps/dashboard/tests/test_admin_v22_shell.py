from pathlib import Path

from django.conf import settings
from django.http import HttpResponse
from django.test import SimpleTestCase
from types import SimpleNamespace

from apps.dashboard.middleware import AdminEmbedFrameOptionsMiddleware


class AdminV22ShellContractTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.root = Path(settings.BASE_DIR)

    def _read(self, relpath: str) -> str:
        return (self.root / relpath).read_text(encoding="utf-8")

    def test_base_shell_loads_v22_assets_and_command_palette(self):
        base = self._read("apps/dashboard/templates/dashboard/base_admin.html")
        self.assertIn("css/admin_v2.css", base)
        self.assertIn("js/admin_v2.js", base)
        self.assertIn('id="adminV2CommandPalette"', base)
        self.assertIn('{% block page_actions %}{% endblock %}', base)

    def test_storefront_primary_navigation_is_prioritized(self):
        base = self._read("apps/dashboard/templates/dashboard/base_admin.html")
        self.assertIn('data-admin-v2-priority="1"', base)
        self.assertIn('data-admin-v2-priority="2"', base)
        self.assertIn('data-admin-v2-priority="3"', base)
        self.assertIn("سازنده فروشگاه", base)
        self.assertIn("ظاهر و طراحی", base)
        self.assertIn("محتوا", base)

    def test_command_search_exposes_deep_merchant_destinations(self):
        base = self._read("apps/dashboard/templates/dashboard/base_admin.html")
        for term in ("لوگو", "سازنده فروشگاه", "کالاها", "دسته‌بندی‌ها"):
            self.assertIn(term, base)
        self.assertIn("panel=header", base)
        self.assertIn("panel=appearance", base)

    def test_command_search_includes_sms_and_harvests_visible_navigation(self):
        base = self._read("apps/dashboard/templates/dashboard/base_admin.html")
        js = self._read("apps/dashboard/static/js/admin_v2.js")
        for route_name in ("settings-sms-connection", "sms-log-list", "sms-outbox-list"):
            self.assertIn(route_name, base)
        self.assertIn("پیامک", base)
        self.assertIn("collectNavigationItems", js)
        self.assertIn("rankItems", js)
        self.assertIn(".sidebar a.nav-item[href]", js)

    def test_dashboard_setup_checklist_contract_is_preserved(self):
        dashboard = self._read("apps/dashboard/templates/dashboard/dashboard.html")
        self.assertIn("setup_checklist.all_complete", dashboard)
        self.assertIn("چک‌لیست راه‌اندازی فروشگاه", dashboard)
        self.assertIn("setup_checklist.steps", dashboard)
        self.assertIn("setup_checklist.percent", dashboard)
        self.assertIn("step.is_unlocked", dashboard)
        self.assertIn("step.is_next", dashboard)

    def test_settings_remains_top_tab_navigation(self):
        settings_template = self._read("apps/dashboard/templates/dashboard/settings.html")
        self.assertIn('class="settings-nav"', settings_template)
        self.assertIn('aria-label="بخش‌های تنظیمات"', settings_template)
        self.assertNotIn("settings-sidebar", settings_template)

    def test_admin_v22_supports_embedded_real_editor_pages(self):
        js = self._read("apps/dashboard/static/js/admin_v2.js")
        css = self._read("apps/dashboard/static/css/admin_v2.css")
        self.assertIn("embed", js)
        self.assertIn("admin-v2-embedded", js)
        self.assertIn(".admin-v2-embedded", css)

    def test_deep_workspace_embed_is_sameorigin_only_and_explicit(self):
        middleware = AdminEmbedFrameOptionsMiddleware(lambda request: HttpResponse("ok"))
        dashboard_match = SimpleNamespace(namespace="dashboard")
        user = SimpleNamespace(is_authenticated=True)

        embedded = SimpleNamespace(GET={"embed": "1"}, resolver_match=dashboard_match, user=user)
        response = middleware(embedded)
        self.assertEqual(response.headers.get("X-Frame-Options"), "SAMEORIGIN")

        ordinary = SimpleNamespace(GET={}, resolver_match=dashboard_match, user=user)
        ordinary_response = middleware(ordinary)
        self.assertIsNone(ordinary_response.headers.get("X-Frame-Options"))

        anonymous = SimpleNamespace(
            GET={"embed": "1"},
            resolver_match=dashboard_match,
            user=SimpleNamespace(is_authenticated=False),
        )
        anonymous_response = middleware(anonymous)
        self.assertIsNone(anonymous_response.headers.get("X-Frame-Options"))

    def test_settings_installs_embed_middleware_after_global_xframe_middleware(self):
        source = self._read("shop_core/settings.py")
        global_index = source.index("django.middleware.clickjacking.XFrameOptionsMiddleware")
        embed_index = source.index("apps.dashboard.middleware.AdminEmbedFrameOptionsMiddleware")
        self.assertGreater(embed_index, global_index)
