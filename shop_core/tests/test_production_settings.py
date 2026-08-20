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


def _run_check(extra_env, *, args=()):
    """Run ``manage.py check`` with controlled *application* config.

    On Windows, stripping the child process environment down to PATH and
    PYTHONPATH also removes OS networking/runtime variables that CPython's
    ``_overlapped``/``asyncio`` stack may need, causing WinError 10106 before
    Django settings are imported. Preserve the operating-system environment
    and remove only variables that can configure this application.
    """
    env = os.environ.copy()
    controlled_prefixes = (
        "DJANGO_", "RASTISI_", "STORES_", "AUTH_", "SHOP_", "PAYMENT_",
    )
    controlled_exact = {
        "DATABASE_URL", "LOG_LEVEL", "PAYMENTS_SIMULATION_ENABLED",
    }
    for key in list(env):
        upper = key.upper()
        if upper.startswith(controlled_prefixes) or upper in controlled_exact:
            env.pop(key, None)
    env.update(extra_env)
    return subprocess.run(
        [sys.executable, MANAGE_PY, "check", *args],
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

    def test_invalid_rate_limit_cache_url_fails_with_clear_message(self):
        result = _run_check({"RASTISI_RATE_LIMIT_CACHE_URL": "memcached://host:11211"})
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("RASTISI_RATE_LIMIT_CACHE_URL scheme", result.stderr)


class RateLimitBackendCheckTests(SimpleTestCase):
    """apps.core.checks.rate_limit_backend_check (rastisi.core.W001) — only
    ever a Warning (never blocks `check`/`check --deploy`, see the check's
    own docstring for why Error would be unsafe here), so it never appears
    outside `--deploy` output."""

    _base_env = {
        "DJANGO_DEBUG": "False",
        "DJANGO_SECRET_KEY": "a-real-unique-production-secret",
        "DJANGO_ALLOWED_HOSTS": "example.com",
    }

    def test_debug_false_no_redis_url_warns_under_deploy(self):
        result = _run_check(self._base_env, args=("--deploy",))
        self.assertEqual(result.returncode, 0, msg=result.stderr)  # Warning never fails check
        self.assertIn("rastisi.core.W001", result.stdout + result.stderr)

    def test_debug_false_no_redis_url_still_passes_plain_check(self):
        """Confirms Warning severity end-to-end: a DEBUG=False deployment
        with no Redis configured yet (i.e. today's actual production state)
        must still pass a plain `check` — this is the exact scenario Phase
        1C must not break."""
        result = _run_check(self._base_env)
        self.assertEqual(result.returncode, 0, msg=result.stderr)

    def test_debug_false_with_redis_url_configured_no_warning(self):
        env = dict(self._base_env, RASTISI_RATE_LIMIT_CACHE_URL="redis://127.0.0.1:6379/1")
        result = _run_check(env, args=("--deploy",))
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertNotIn("rastisi.core.W001", result.stdout + result.stderr)

    def test_debug_true_no_warning_even_without_redis(self):
        result = _run_check({}, args=("--deploy",))
        self.assertNotIn("rastisi.core.W001", result.stdout + result.stderr)


class TrustProxyDebugCheckTests(SimpleTestCase):
    """apps.core.checks.trust_proxy_debug_check (rastisi.core.W002)."""

    def test_trust_enabled_with_debug_warns_on_plain_check(self):
        result = _run_check({"RASTISI_TRUST_PROXY_CLIENT_IP": "true"})
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertIn("rastisi.core.W002", result.stdout + result.stderr)

    def test_trust_disabled_with_debug_no_warning(self):
        result = _run_check({})
        self.assertNotIn("rastisi.core.W002", result.stdout + result.stderr)

    def test_trust_enabled_without_debug_no_warning(self):
        env = {
            "RASTISI_TRUST_PROXY_CLIENT_IP": "true",
            "DJANGO_DEBUG": "False",
            "DJANGO_SECRET_KEY": "a-real-unique-production-secret",
            "DJANGO_ALLOWED_HOSTS": "example.com",
        }
        result = _run_check(env)
        self.assertNotIn("rastisi.core.W002", result.stdout + result.stderr)
