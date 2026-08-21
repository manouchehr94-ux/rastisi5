"""apps.core.storage — proves the private-media storage backend is resolved
through Django's built-in STORAGES setting (config-driven), not hardcoded,
and that swapping the concrete backend behind the "private" alias can never
produce migration drift for ExportJob/ImportJob's FileFields. See
MEDIA_STORAGE_SCALABILITY in
docs/reports/10K_ARCHITECTURAL_SCALABILITY_READINESS_REVIEW.md and
core/migrations/0014_private_storage_deconstructible.py.

Application-code independence from local-filesystem ``.path`` semantics
(ExportJob/ImportJob, product images, etc.) is verified by direct source
inspection, not by a runtime test here: Django's own ``FileSystemStorage``
implementation legitimately calls ``.path()`` internally (``exists()``,
``save()``, ...) — that is expected and correct for a filesystem backend,
and patching it to raise would fail for the wrong reason. What actually
matters is that *application* code (models/services/views under ``apps/``)
never calls ``.field.path`` itself; grepping confirms zero such call sites
outside test-only Pillow reopen helpers."""

import json
import subprocess
import sys
import textwrap
from pathlib import Path

from django.core.files.base import ContentFile
from django.core.files.storage import Storage, storages
from django.test import TestCase, override_settings

from apps.core.storage import PrivateFileSystemStorage, _PrivateStorageProxy


class _NoPathStorage(Storage):
    """یک Storage جعلیِ کاملاً درون‌حافظه‌ای — دقیقاً مثلِ یک backend
    غیرِ‌فایل‌سیستمیِ واقعی (مثلاً ``S3Boto3Storage``)، عمداً هیچ ``.path``ای
    ندارد؛ فراخوانیِ آن باید بلافاصله ``NotImplementedError`` بدهد."""

    def __init__(self, *args, **kwargs):
        self._files = {}
        super().__init__()

    def _open(self, name, mode="rb"):
        return ContentFile(self._files[name], name=name)

    def _save(self, name, content):
        self._files[name] = content.read()
        return name

    def exists(self, name):
        return name in self._files

    def delete(self, name):
        self._files.pop(name, None)

    def size(self, name):
        return len(self._files[name])

    def url(self, name):
        raise NotImplementedError("no public URL for private storage")

    def path(self, name):
        raise NotImplementedError("this backend has no local filesystem path")


_SWAPPED_STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    "private": {"BACKEND": "apps.core.tests.test_storage._NoPathStorage"},
}


class PrivateStorageIsConfigDrivenTests(TestCase):
    def test_private_storage_is_the_stable_deconstructible_proxy(self):
        from apps.core import storage as storage_module

        self.assertIsInstance(storage_module.private_storage, _PrivateStorageProxy)
        # همان تاپلِ دقیقاً منجمدشده در core/migrations/
        # 0014_private_storage_deconstructible.py — نگاه کنید به
        # test_fresh_process_migration_state_is_stable_across_backends برای
        # اثباتِ این‌که این پایدار می‌ماند حتی وقتی بک‌اندِ واقعی عوض شود.
        self.assertEqual(
            storage_module.private_storage.deconstruct(),
            ("apps.core.storage.PrivateFileSystemStorage", [], {}),
        )

    def test_private_storage_proxies_real_operations_to_the_resolved_backend(self):
        """پراکسی بودنِ ``private_storage`` نباید مانعِ عملیاتِ واقعیِ فایل
        شود — عملیات باید دقیقاً همان چیزی باشد که خودِ ``storages["private"]``
        برمی‌گرداند (نگاه کنید به ``LazyObject.__getattr__``)."""
        from apps.core import storage as storage_module

        name = storage_module.private_storage.save(
            "exports/probe/proxy-check.csv", ContentFile(b"a,b\n1,2\n")
        )
        try:
            self.assertTrue(storage_module.private_storage.exists(name))
            self.assertTrue(storages["private"].exists(name))
            with storage_module.private_storage.open(name) as fh:
                self.assertEqual(fh.read(), b"a,b\n1,2\n")
        finally:
            storage_module.private_storage.delete(name)

    @override_settings(STORAGES=_SWAPPED_STORAGES)
    def test_storages_setting_resolves_a_path_less_backend_for_the_private_alias(self):
        """اثباتِ مکانیزمِ تعویض: اگر یک استقرارِ واقعی پیش از راه‌اندازیِ
        فرایند ``STORAGES["private"]["BACKEND"]`` را به یک backend
        غیرِ‌فایل‌سیستمی تغییر دهد (مثلاً یک backend سازگار با S3)، تنها
        نقطه‌ای که resolve می‌شود همین alias در تنظیمات است — نه هیچ
        ارجاعِ سخت‌کدشده در apps/core/storage.py."""
        resolved = storages["private"]
        self.assertIsInstance(resolved, _NoPathStorage)

        name = resolved.save("exports/probe/example.csv", ContentFile(b"id,name\n1,test\n"))
        self.assertTrue(resolved.exists(name))
        with resolved.open(name) as fh:
            self.assertEqual(fh.read(), b"id,name\n1,test\n")
        with self.assertRaises(NotImplementedError):
            resolved.path(name)
        resolved.delete(name)
        self.assertFalse(resolved.exists(name))


# ---------------------------------------------------------------------------
# Fresh-process verification.
#
# override_settings() cannot exercise the real risk here: apps.core.storage's
# module-level `private_storage` singleton is constructed exactly once, the
# first time the process imports apps.core.models (which Django's own
# django.setup() already does, while populating the app registry) — and
# LazyObject caches `_wrapped` permanently after its first attribute access.
# By the time any test method runs, something has almost certainly already
# touched `private_storage`, so a same-process override_settings("STORAGES")
# call can no longer change what it resolves to. Only a genuinely separate
# Python process, with the alternate backend configured *before*
# django.setup() ever runs, can prove what a real fresh deployment process
# would see.
# ---------------------------------------------------------------------------

_FRESH_PROCESS_SCRIPT = textwrap.dedent(
    """
    import json
    import os
    import sys

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "shop_core.settings")

    # Installed BEFORE django.setup() — which is what actually imports
    # apps.core.models and binds ExportJob/ImportJob's FileFields to
    # whatever apps.core.storage.private_storage resolves to at that
    # moment — so this mirrors a real fresh deployment process, not an
    # in-process override_settings() applied after the fact.
    use_alt_backend = os.environ.get("USE_ALT_PRIVATE_BACKEND") == "1"
    if use_alt_backend:
        import shop_core.settings as _settings_module
        _settings_module.STORAGES = {
            **_settings_module.STORAGES,
            "private": {"BACKEND": "apps.core.tests.test_storage._NoPathStorage"},
        }

    import django
    django.setup()

    from django.core.files.base import ContentFile
    from apps.core.models import ExportJob, ImportJob

    def _field_storage_deconstruct(model, field_name):
        field = model._meta.get_field(field_name)
        _, _, _, kwargs = field.deconstruct()
        return list(kwargs["storage"].deconstruct())

    result = {
        "export_file_storage_deconstruct": _field_storage_deconstruct(ExportJob, "file"),
        "import_source_file_storage_deconstruct": _field_storage_deconstruct(ImportJob, "source_file"),
        "import_error_report_storage_deconstruct": _field_storage_deconstruct(ImportJob, "error_report_file"),
    }

    # Real, model-bound FieldFile I/O through whichever backend is
    # actually configured in *this* process — save=False avoids needing a
    # database connection at all (this script proves storage wiring, not
    # persistence).
    job = ExportJob(export_type=ExportJob.ExportType.PRODUCTS)
    job.file.save("export.csv", ContentFile(b"id,name\\n1,test\\n"), save=False)
    result["resolved_backend_class"] = type(job.file.storage._wrapped).__name__
    result["file_exists_after_save"] = job.file.storage.exists(job.file.name)
    with job.file.open("rb") as fh:
        result["file_contents"] = fh.read().decode()
    try:
        job.file.path
        result["path_access_raised_not_implemented"] = False
    except NotImplementedError:
        result["path_access_raised_not_implemented"] = True
    except AttributeError:
        result["path_access_raised_not_implemented"] = "AttributeError (no .path at all)"
    job.file.delete(save=False)
    result["file_exists_after_delete"] = job.file.storage.exists(
        job.file.name or "export.csv"
    )

    print(json.dumps(result))
    """
)


class FreshProcessMigrationStabilityTests(TestCase):
    """TASK 2 + TASK 3 evidence: spawns a genuinely separate Python process
    for each configuration, with the alternate backend (or not) installed
    before django.setup() ever runs — proving both the migration-state
    claim and real model FieldFile I/O against a path-less backend, not
    merely storages["private"] in isolation."""

    def _run_fresh_process(self, *, use_alt_backend: bool) -> dict:
        import os

        env = {**os.environ, "USE_ALT_PRIVATE_BACKEND": "1" if use_alt_backend else "0"}
        completed = subprocess.run(
            [sys.executable, "-c", _FRESH_PROCESS_SCRIPT],
            cwd=str(Path(__file__).resolve().parents[3]),
            env=env,
            capture_output=True,
            text=True,
            timeout=60,
        )
        self.assertEqual(
            completed.returncode, 0,
            f"fresh process failed:\nSTDOUT: {completed.stdout}\nSTDERR: {completed.stderr}",
        )
        return json.loads(completed.stdout.strip().splitlines()[-1])

    def test_fresh_process_migration_state_is_stable_across_backends(self):
        """CORE CLAIM: changing the deployment storage backend must not
        require a model migration. Compares the deconstructed storage
        representation of ExportJob.file / ImportJob.source_file /
        ImportJob.error_report_file between a normal-filesystem-backend
        fresh process and an alternate-path-less-backend fresh process —
        they must be byte-for-byte identical, and must match the literal
        value already frozen in
        core/migrations/0014_private_storage_deconstructible.py."""
        normal = self._run_fresh_process(use_alt_backend=False)
        alternate = self._run_fresh_process(use_alt_backend=True)

        frozen_migration_value = ["apps.core.storage.PrivateFileSystemStorage", [], {}]

        for key in (
            "export_file_storage_deconstruct",
            "import_source_file_storage_deconstruct",
            "import_error_report_storage_deconstruct",
        ):
            self.assertEqual(normal[key], frozen_migration_value, key)
            self.assertEqual(alternate[key], frozen_migration_value, key)
            self.assertEqual(normal[key], alternate[key], key)

        # Sanity: the two processes actually resolved *different* concrete
        # backends at runtime — the migration-state equality above is not
        # an artifact of both processes silently using the same backend.
        self.assertEqual(normal["resolved_backend_class"], "PrivateFileSystemStorage")
        self.assertEqual(alternate["resolved_backend_class"], "_NoPathStorage")

    def test_fresh_process_makemigrations_check_reports_no_drift_under_alternate_backend(self):
        """Runs the actual `manage.py makemigrations --check --dry-run`
        management command in a fresh process with the alternate,
        path-less private backend configured before django.setup() —
        the strongest possible proof against migration drift, since it
        exercises Django's real autodetector, not a hand-rolled
        comparison."""
        import os

        env = {**os.environ, "USE_ALT_PRIVATE_BACKEND": "1"}
        script = textwrap.dedent(
            """
            import os
            os.environ.setdefault("DJANGO_SETTINGS_MODULE", "shop_core.settings")
            import shop_core.settings as _settings_module
            _settings_module.STORAGES = {
                **_settings_module.STORAGES,
                "private": {"BACKEND": "apps.core.tests.test_storage._NoPathStorage"},
            }
            import django
            django.setup()
            from django.core.management import call_command
            call_command("makemigrations", check=True, dry_run=True)
            """
        )
        completed = subprocess.run(
            [sys.executable, "-c", script],
            cwd=str(Path(__file__).resolve().parents[3]),
            env=env,
            capture_output=True,
            text=True,
            timeout=60,
        )
        # `makemigrations --check` exits 1 if it would generate any
        # migration, 0 if there is nothing to do — this is the real
        # command an operator would run after a backend swap.
        self.assertEqual(
            completed.returncode, 0,
            f"makemigrations --check detected drift under the alternate private "
            f"backend:\nSTDOUT: {completed.stdout}\nSTDERR: {completed.stderr}",
        )

    def test_fresh_process_real_fieldfile_io_through_pathless_backend(self):
        """TASK 3: proves the actual model-bound FieldFile (not
        storages["private"] called directly) round-trips through a
        path-less backend — save/open/exists/delete — and that accessing
        .path is impossible on that backend, exactly like a real S3-class
        backend."""
        result = self._run_fresh_process(use_alt_backend=True)

        self.assertEqual(result["resolved_backend_class"], "_NoPathStorage")
        self.assertTrue(result["file_exists_after_save"])
        self.assertEqual(result["file_contents"], "id,name\n1,test\n")
        self.assertEqual(result["path_access_raised_not_implemented"], True)
        self.assertFalse(result["file_exists_after_delete"])
