"""apps.core.storage — proves the private-media storage backend is resolved
through Django's built-in STORAGES setting (config-driven), not hardcoded.
See MEDIA_STORAGE_SCALABILITY in
docs/reports/10K_ARCHITECTURAL_SCALABILITY_READINESS_REVIEW.md.

Application-code independence from local-filesystem ``.path`` semantics
(ExportJob/ImportJob, product images, etc.) is verified by direct source
inspection, not by a runtime test here: Django's own ``FileSystemStorage``
implementation legitimately calls ``.path()`` internally (``exists()``,
``save()``, ...) — that is expected and correct for a filesystem backend,
and patching it to raise would fail for the wrong reason. What actually
matters is that *application* code (models/services/views under ``apps/``)
never calls ``.field.path`` itself; grepping confirms zero such call sites
outside test-only Pillow reopen helpers."""

from django.core.files.base import ContentFile
from django.core.files.storage import Storage, storages
from django.test import TestCase, override_settings

from apps.core.storage import PrivateFileSystemStorage


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
    def test_private_storage_singleton_is_resolved_via_storages_registry(self):
        from apps.core import storage as storage_module

        self.assertIs(storage_module.private_storage, storages["private"])
        self.assertIsInstance(storage_module.private_storage, PrivateFileSystemStorage)

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
