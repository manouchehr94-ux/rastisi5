from __future__ import annotations

import json
import os
import shutil
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import connections
from django.test import Client

from apps.stores.models import Store, StoreMembership
from apps.storefront_builder import section_registry
from apps.storefront_builder.models import StorefrontEditHistoryEntry, StorefrontPage, StorefrontSection
from apps.storefront_builder.services import layout_service


class Command(BaseCommand):
    help = (
        "Run the Storefront Builder exhaustive QA harness: Django regression suite + "
        "real-browser interaction/layout checks. The browser pass uses a temporary copy "
        "of the current Draft and restores the local SQLite database byte-for-byte when done."
    )

    def add_arguments(self, parser):
        parser.add_argument("--store-subdomain", required=True)
        parser.add_argument("--username", required=True)
        parser.add_argument("--port", type=int, default=8765)
        parser.add_argument("--headed", action="store_true", help="Show the QA browser while it runs.")
        parser.add_argument(
            "--browser-channel",
            default="auto",
            choices=("auto", "chrome", "msedge"),
            help="Use installed Chrome/Edge. No Playwright browser download is required.",
        )
        parser.add_argument("--skip-django-suite", action="store_true")
        parser.add_argument("--skip-browser", action="store_true")
        parser.add_argument(
            "--install-node-deps",
            action="store_true",
            help="Run npm install in tools/storefront_builder_qa before browser QA.",
        )
        parser.add_argument("--report-dir", default="")

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError("این QA مخرب-موقت فقط در DEBUG مجاز است.")

        base_dir = Path(settings.BASE_DIR).resolve()
        tool_dir = base_dir / "tools" / "storefront_builder_qa"
        node_script = tool_dir / "run.mjs"
        if not node_script.exists():
            raise CommandError(f"QA runner پیدا نشد: {node_script}")

        store = self._get_store(options["store_subdomain"])
        user = self._get_user(options["username"], store)

        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        report_dir = (
            Path(options["report_dir"]).expanduser().resolve()
            if options["report_dir"]
            else base_dir.parent / "RastiSi4_qa_reports" / stamp
        )
        report_dir.mkdir(parents=True, exist_ok=True)

        node = shutil.which("node")
        npm = shutil.which("npm") or shutil.which("npm.cmd")
        if not options["skip_browser"]:
            if node is None:
                raise CommandError("Node.js پیدا نشد؛ Browser QA بدون Node اجرا نمی‌شود.")
            if options["install_node_deps"]:
                if npm is None:
                    raise CommandError("npm پیدا نشد.")
                self.stdout.write(self.style.WARNING("Installing browser QA dependency (playwright-core)..."))
                install_code = self._run_logged(
                    [npm, "install", "--no-audit", "--no-fund"],
                    cwd=tool_dir,
                    log_path=report_dir / "npm-install.log",
                )
                if install_code:
                    raise CommandError(f"npm install شکست خورد؛ گزارش: {report_dir / 'npm-install.log'}")
            if not (tool_dir / "node_modules" / "playwright-core").exists():
                raise CommandError(
                    "playwright-core نصب نیست. یک‌بار اجرا کنید:\n"
                    f"  cd {tool_dir}\n"
                    "  npm install\n"
                    "سپس همین دستور QA را دوباره اجرا کنید."
                )

        if not options["skip_browser"] and not self._port_is_free(options["port"]):
            raise CommandError(f"پورت {options['port']} در حال استفاده است؛ --port دیگری بدهید.")

        unit_exit = 0
        browser_exit = 0
        if not options["skip_django_suite"]:
            self.stdout.write(self.style.MIGRATE_HEADING("[1/2] Django Storefront Builder regression suite"))
            unit_exit = self._run_logged(
                [sys.executable, "manage.py", "test", "apps.storefront_builder", "-v", "1"],
                cwd=base_dir,
                log_path=report_dir / "django-suite.log",
            )

        if options["skip_browser"]:
            self._write_python_summary(report_dir, unit_exit, None, None)
            self._zip_report(report_dir)
            if unit_exit:
                raise CommandError(f"Django QA failed. Report: {report_dir}")
            self.stdout.write(self.style.SUCCESS(f"QA PASS — report: {report_dir}"))
            return

        db_path = self._sqlite_db_path()
        backup_dir = base_dir.parent / "RastiSi4_qa_backups"
        backup_dir.mkdir(parents=True, exist_ok=True)
        db_backup = backup_dir / f"storefront-builder-qa-{stamp}.sqlite3"
        self._sqlite_backup(db_path, db_backup)
        (report_dir / "RECOVERY.txt").write_text(
            "اگر QA به‌صورت غیرعادی قطع شد و restore خودکار اجرا نشد، ابتدا همه runserverها را ببندید و سپس:\n"
            f'Copy-Item "{db_backup}" "{db_path}" -Force\n',
            encoding="utf-8",
        )
        self.stdout.write(self.style.WARNING(f"Safety DB backup: {db_backup}"))

        server_proc = None
        server_log_handle = None
        browser_result_path = report_dir / "browser-result.json"
        runtime_manifest_path = None
        try:
            self._prepare_builder_sandbox(store, user)
            session_cookie = self._make_session_cookie(user)
            manifest = self._build_manifest(
                store=store,
                user=user,
                port=options["port"],
                session_cookie=session_cookie,
                report_dir=report_dir,
                headed=options["headed"],
                browser_channel=options["browser_channel"],
            )
            fd, runtime_manifest_path = tempfile.mkstemp(prefix="rastisi-sfb-qa-", suffix=".json")
            os.close(fd)
            Path(runtime_manifest_path).write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

            self.stdout.write(self.style.MIGRATE_HEADING("[2/2] Real-browser exhaustive QA"))
            server_log_handle = (report_dir / "runserver.log").open("w", encoding="utf-8", errors="replace")
            server_proc = subprocess.Popen(
                [sys.executable, "manage.py", "runserver", f"127.0.0.1:{options['port']}", "--noreload"],
                cwd=base_dir,
                stdout=server_log_handle,
                stderr=subprocess.STDOUT,
                text=True,
                env={**os.environ, "PYTHONUNBUFFERED": "1"},
            )
            if not self._wait_for_port(options["port"], server_proc, timeout=20):
                raise CommandError(f"QA runserver بالا نیامد؛ لاگ: {report_dir / 'runserver.log'}")

            browser_exit = self._run_logged(
                [node, str(node_script), runtime_manifest_path],
                cwd=tool_dir,
                log_path=report_dir / "browser.log",
            )
        finally:
            if server_proc is not None:
                self._stop_process(server_proc)
            if server_log_handle is not None:
                server_log_handle.close()
            if runtime_manifest_path:
                Path(runtime_manifest_path).unlink(missing_ok=True)
            # Exact local-state restoration: sessions, Draft, Published pointers,
            # media placements, history entries, and rate-limit rows are all put
            # back to the pre-QA SQLite image.
            self._sqlite_restore(db_backup, db_path)
            self.stdout.write(self.style.SUCCESS("Local database restored to its pre-QA state."))

        browser_payload = None
        if browser_result_path.exists():
            try:
                browser_payload = json.loads(browser_result_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                browser_payload = None

        self._write_python_summary(report_dir, unit_exit, browser_exit, browser_payload)
        zip_path = self._zip_report(report_dir)

        fail_count = int((browser_payload or {}).get("summary", {}).get("failed", 0))
        warn_count = int((browser_payload or {}).get("summary", {}).get("warnings", 0))
        if unit_exit or browser_exit or fail_count:
            raise CommandError(
                f"QA found problems — failed={fail_count}, warnings={warn_count}. "
                f"Report: {report_dir} | ZIP: {zip_path}"
            )
        self.stdout.write(
            self.style.SUCCESS(
                f"QA PASS — warnings={warn_count}. Report: {report_dir} | ZIP: {zip_path}"
            )
        )

    def _get_store(self, admin_subdomain: str) -> Store:
        try:
            return Store.objects.get(admin_subdomain=admin_subdomain)
        except Store.DoesNotExist as exc:
            raise CommandError(f"فروشگاه با admin_subdomain={admin_subdomain!r} پیدا نشد.") from exc

    def _get_user(self, username: str, store: Store):
        User = get_user_model()
        try:
            user = User.objects.get(username=username)
        except User.DoesNotExist as exc:
            raise CommandError(f"کاربر {username!r} پیدا نشد.") from exc
        if not user.is_staff:
            raise CommandError("کاربر QA باید is_staff=True باشد.")
        membership = StoreMembership.objects.filter(
            store=store,
            user=user,
            status=StoreMembership.MembershipStatus.ACTIVE,
        ).first()
        if membership is None:
            raise CommandError("کاربر QA عضویت فعال همین فروشگاه را ندارد.")
        return user

    def _sqlite_db_path(self) -> Path:
        connection = connections["default"]
        if connection.vendor != "sqlite":
            raise CommandError(
                "Browser QA مخرب-موقت فعلاً فقط روی SQLite محلی اجرا می‌شود تا restore دقیق و اتمیک باشد."
            )
        name = str(connection.settings_dict["NAME"])
        if name == ":memory:":
            raise CommandError("SQLite in-memory برای این QA پشتیبانی نمی‌شود.")
        return Path(name).resolve()

    def _sqlite_backup(self, source: Path, target: Path) -> None:
        connections.close_all()
        with sqlite3.connect(source) as src, sqlite3.connect(target) as dst:
            src.backup(dst)

    def _sqlite_restore(self, backup: Path, target: Path) -> None:
        connections.close_all()
        for suffix in ("-wal", "-shm"):
            Path(str(target) + suffix).unlink(missing_ok=True)
        shutil.copy2(backup, target)

    def _prepare_builder_sandbox(self, store: Store, user) -> None:
        draft = layout_service.get_or_create_draft(store, user=user)
        # The full SQLite image is restored after QA. Clearing every Draft page
        # gives the browser matrix a deterministic surface without touching the
        # Published storefront permanently. A hidden announcement-bar sentinel
        # stays at order 0 on each page so move/reorder controls can be exercised.
        StorefrontEditHistoryEntry.objects.filter(draft_version=draft).delete()
        sentinel_definition = section_registry.get_definition("announcement_bar")
        for page in draft.pages.all():
            page.sections.all().delete()
            StorefrontSection.objects.create(
                page=page,
                section_key="announcement_bar",
                order=0,
                settings=sentinel_definition.default_settings(),
            )

    def _make_session_cookie(self, user) -> str:
        client = Client()
        client.force_login(user)
        cookie = client.cookies.get(settings.SESSION_COOKIE_NAME)
        if cookie is None:
            raise CommandError("نتوانستم session QA بسازم.")
        return cookie.value

    def _build_manifest(self, *, store, user, port, session_cookie, report_dir, headed, browser_channel):
        suffix = settings.RASTISI_ADMIN_DOMAIN_SUFFIX
        host = f"{store.admin_subdomain}.{suffix}"
        origin = f"http://{host}:{port}"
        page_types = [
            {"value": value, "label": str(label)}
            for value, label in StorefrontPage.PageType.choices
        ]
        library_by_page = {}
        for value, _label in StorefrontPage.PageType.choices:
            members = []
            for category, definitions in section_registry.list_library_groups(page_type=value):
                for definition in definitions:
                    members.append(
                        {
                            "key": definition.key,
                            "label": definition.label_fa,
                            "category": category,
                            "duplicable": bool(definition.duplicable),
                            "removable": bool(definition.removable),
                            "max_instances": definition.max_instances,
                        }
                    )
            library_by_page[value] = members

        all_definitions = [
            {
                "key": definition.key,
                "label": definition.label_fa,
                "category": definition.category_fa,
                "hidden_from_library": bool(definition.hidden_from_library),
                "duplicable": bool(definition.duplicable),
                "removable": bool(definition.removable),
                "max_instances": definition.max_instances,
                "page_types": sorted(definition.page_types),
            }
            for definition in section_registry.list_definitions()
        ]

        same_site = str(settings.SESSION_COOKIE_SAMESITE or "Lax").capitalize()
        if same_site not in {"Lax", "Strict", "None"}:
            same_site = "Lax"
        return {
            "origin": origin,
            "host": host,
            "builder_url": f"{origin}/admin-portal/storefront-builder/?page=home",
            "report_dir": str(report_dir),
            "headed": bool(headed),
            "browser_channel": browser_channel,
            "session": {
                "name": settings.SESSION_COOKIE_NAME,
                "value": session_cookie,
                "domain": host,
                "path": settings.SESSION_COOKIE_PATH or "/",
                "httpOnly": bool(settings.SESSION_COOKIE_HTTPONLY),
                "secure": bool(settings.SESSION_COOKIE_SECURE),
                "sameSite": same_site,
            },
            "store": {"id": store.pk, "name": store.name, "admin_subdomain": store.admin_subdomain},
            "user": {"id": user.pk, "username": user.username},
            "page_types": page_types,
            "library_by_page": library_by_page,
            "all_definitions": all_definitions,
            "expected_registry_count": len(all_definitions),
        }

    @staticmethod
    def _port_is_free(port: int) -> bool:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.2)
            return sock.connect_ex(("127.0.0.1", port)) != 0

    @staticmethod
    def _wait_for_port(port: int, proc, timeout: int) -> bool:
        deadline = time.time() + timeout
        while time.time() < deadline:
            if proc.poll() is not None:
                return False
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(0.3)
                if sock.connect_ex(("127.0.0.1", port)) == 0:
                    return True
            time.sleep(0.2)
        return False

    @staticmethod
    def _stop_process(proc) -> None:
        if proc.poll() is not None:
            return
        proc.terminate()
        try:
            proc.wait(timeout=6)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=3)

    def _run_logged(self, command, *, cwd: Path, log_path: Path) -> int:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("w", encoding="utf-8", errors="replace") as log:
            process = subprocess.Popen(
                command,
                cwd=cwd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            assert process.stdout is not None
            for line in process.stdout:
                self.stdout.write(line.rstrip("\n"))
                log.write(line)
                log.flush()
            return process.wait()

    @staticmethod
    def _write_python_summary(report_dir: Path, unit_exit, browser_exit, browser_payload):
        payload = {
            "django_suite_exit_code": unit_exit,
            "browser_exit_code": browser_exit,
            "browser_summary": (browser_payload or {}).get("summary") if browser_payload else None,
            "database_restored": browser_exit is not None,
        }
        (report_dir / "qa-summary.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    @staticmethod
    def _zip_report(report_dir: Path) -> Path:
        archive = shutil.make_archive(str(report_dir), "zip", root_dir=report_dir)
        return Path(archive)
