"""End-to-end checks that shop_core/settings.py actually wires env_config's
functions correctly.

settings.py is imported exactly once by this very test process (Django is
already running), so its module-level code cannot be re-exercised with a
different environment inside this process — these tests spawn a fresh
`python manage.py check` subprocess with a controlled environment instead.
This is slower than a plain unit test, so it is used sparingly, only to
confirm the wiring in settings.py itself; the parsing/validation logic is
covered exhaustively (and fast) in test_env_config.py.
"""

import os
import subprocess
import sys

from django.test import SimpleTestCase

from shop_core.env_config import DEV_INSECURE_SECRET_KEY

MANAGE_PY = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "manage.py")


def _run_check(extra_env):
    """Run `manage.py check` in a subprocess with a minimal, controlled env."""
    env = {
        "PATH": os.environ.get("PATH", ""),
        "PYTHONPATH": os.environ.get("PYTHONPATH", ""),
    }
    env.update(extra_env)
    return subprocess.run(
        [sys.executable, MANAGE_PY, "check"],
        cwd=os.path.dirname(MANAGE_PY),
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )


class DevelopmentDefaultsRemainUsableTests(SimpleTestCase):
    def test_no_env_vars_at_all_still_passes_check(self):
        result = _run_check({})
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertIn("System check identified no issues", result.stdout + result.stderr)


class ProductionSafetyEnforcedEndToEndTests(SimpleTestCase):
    def test_debug_false_without_secret_key_fails_fast(self):
        result = _run_check({"DJANGO_DEBUG": "False", "DJANGO_ALLOWED_HOSTS": "example.com"})
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("DJANGO_SECRET_KEY is required", result.stderr)

    def test_debug_false_with_dev_secret_key_fails_fast(self):
        result = _run_check(
            {
                "DJANGO_DEBUG": "False",
                "DJANGO_ALLOWED_HOSTS": "example.com",
                "DJANGO_SECRET_KEY": DEV_INSECURE_SECRET_KEY,
            }
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("known development-only insecure key", result.stderr)

    def test_debug_false_without_allowed_hosts_fails_fast(self):
        result = _run_check(
            {"DJANGO_DEBUG": "False", "DJANGO_SECRET_KEY": "a-real-unique-production-secret"}
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("DJANGO_ALLOWED_HOSTS must be set", result.stderr)

    def test_debug_false_fully_configured_passes(self):
        result = _run_check(
            {
                "DJANGO_DEBUG": "False",
                "DJANGO_SECRET_KEY": "a-real-unique-production-secret",
                "DJANGO_ALLOWED_HOSTS": "example.com,www.example.com",
                "DJANGO_CSRF_TRUSTED_ORIGINS": "https://example.com",
            }
        )
        self.assertEqual(result.returncode, 0, msg=result.stderr)

    def test_invalid_boolean_env_var_fails_with_clear_message(self):
        result = _run_check({"DJANGO_SECURE_SSL_REDIRECT": "maybe"})
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("is not a valid boolean", result.stderr)

    def test_invalid_database_url_fails_with_clear_message(self):
        result = _run_check({"DATABASE_URL": "mysql://user:pass@host/db"})
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("DATABASE_URL scheme", result.stderr)
