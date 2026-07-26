"""Unit tests for shop_core.env_config.

These are plain unittest.TestCase tests (no Django DB access needed) against
pure functions that each accept an explicit `environ` mapping, so behavior
under different environment-variable combinations can be exercised directly
without touching the real process environment or re-importing settings.py
(which is only ever imported once per process).
"""

from pathlib import Path

from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase

from shop_core.env_config import (
    DEV_INSECURE_SECRET_KEY,
    build_database_config,
    env_bool,
    env_int,
    env_list,
    env_str,
    resolve_allowed_hosts,
    resolve_log_level,
    resolve_secret_key,
    resolve_secure_proxy_ssl_header,
)


class EnvBoolTests(SimpleTestCase):
    def test_missing_returns_default(self):
        self.assertTrue(env_bool("X", True, environ={}))
        self.assertFalse(env_bool("X", False, environ={}))

    def test_empty_string_returns_default(self):
        self.assertTrue(env_bool("X", True, environ={"X": ""}))

    def test_true_variants(self):
        for raw in ("1", "true", "True", "TRUE", "yes", "on", " true "):
            self.assertTrue(env_bool("X", False, environ={"X": raw}), raw)

    def test_false_variants(self):
        for raw in ("0", "false", "False", "no", "off"):
            self.assertFalse(env_bool("X", True, environ={"X": raw}), raw)

    def test_invalid_value_raises(self):
        with self.assertRaises(ImproperlyConfigured):
            env_bool("X", True, environ={"X": "maybe"})


class EnvIntTests(SimpleTestCase):
    def test_missing_returns_default(self):
        self.assertEqual(env_int("X", 42, environ={}), 42)

    def test_parses_integer(self):
        self.assertEqual(env_int("X", 0, environ={"X": "3600"}), 3600)

    def test_invalid_value_raises(self):
        with self.assertRaises(ImproperlyConfigured):
            env_int("X", 0, environ={"X": "not-a-number"})


class EnvListTests(SimpleTestCase):
    def test_missing_returns_default(self):
        self.assertEqual(env_list("X", default=["a"], environ={}), ["a"])

    def test_parses_comma_separated(self):
        self.assertEqual(
            env_list("X", environ={"X": "example.com, www.example.com ,api.example.com"}),
            ["example.com", "www.example.com", "api.example.com"],
        )

    def test_blank_entries_dropped(self):
        self.assertEqual(env_list("X", environ={"X": "a,,b,"}), ["a", "b"])

    def test_set_but_empty_returns_empty_list_not_default(self):
        self.assertEqual(env_list("X", default=["fallback"], environ={"X": ""}), [])


class EnvStrTests(SimpleTestCase):
    def test_missing_returns_default(self):
        self.assertEqual(env_str("X", "default", environ={}), "default")

    def test_strips_whitespace(self):
        self.assertEqual(env_str("X", environ={"X": "  value  "}), "value")


class ResolveSecretKeyTests(SimpleTestCase):
    def test_debug_true_no_env_uses_dev_key(self):
        self.assertEqual(resolve_secret_key(True, environ={}), DEV_INSECURE_SECRET_KEY)

    def test_debug_true_with_real_key_uses_it(self):
        self.assertEqual(
            resolve_secret_key(True, environ={"DJANGO_SECRET_KEY": "a-real-value"}),
            "a-real-value",
        )

    def test_debug_false_missing_key_raises(self):
        with self.assertRaises(ImproperlyConfigured):
            resolve_secret_key(False, environ={})

    def test_debug_false_dev_key_explicitly_set_raises(self):
        with self.assertRaises(ImproperlyConfigured):
            resolve_secret_key(False, environ={"DJANGO_SECRET_KEY": DEV_INSECURE_SECRET_KEY})

    def test_debug_false_real_key_accepted(self):
        self.assertEqual(
            resolve_secret_key(False, environ={"DJANGO_SECRET_KEY": "a-real-production-value"}),
            "a-real-production-value",
        )


class ResolveAllowedHostsTests(SimpleTestCase):
    def test_debug_true_empty_allowed(self):
        self.assertEqual(resolve_allowed_hosts(True, environ={}), [])

    def test_debug_false_missing_raises(self):
        with self.assertRaises(ImproperlyConfigured):
            resolve_allowed_hosts(False, environ={})

    def test_debug_false_with_hosts_accepted(self):
        self.assertEqual(
            resolve_allowed_hosts(False, environ={"DJANGO_ALLOWED_HOSTS": "example.com"}),
            ["example.com"],
        )


class ResolveSecureProxySslHeaderTests(SimpleTestCase):
    def test_unset_returns_none(self):
        self.assertIsNone(resolve_secure_proxy_ssl_header(environ={}))

    def test_valid_value_parsed(self):
        result = resolve_secure_proxy_ssl_header(
            environ={"DJANGO_SECURE_PROXY_SSL_HEADER": "X-Forwarded-Proto:https"}
        )
        self.assertEqual(result, ("HTTP_X_FORWARDED_PROTO", "https"))

    def test_missing_colon_raises(self):
        with self.assertRaises(ImproperlyConfigured):
            resolve_secure_proxy_ssl_header(
                environ={"DJANGO_SECURE_PROXY_SSL_HEADER": "X-Forwarded-Proto"}
            )

    def test_missing_value_raises(self):
        with self.assertRaises(ImproperlyConfigured):
            resolve_secure_proxy_ssl_header(
                environ={"DJANGO_SECURE_PROXY_SSL_HEADER": "X-Forwarded-Proto:"}
            )


class BuildDatabaseConfigTests(SimpleTestCase):
    def test_unset_returns_sqlite(self):
        base_dir = Path("/tmp/example-base-dir")
        config = build_database_config(base_dir, environ={})
        self.assertEqual(config["ENGINE"], "django.db.backends.sqlite3")
        self.assertEqual(config["NAME"], str(base_dir / "db.sqlite3"))

    def test_postgres_url_parsed_correctly(self):
        config = build_database_config(
            Path("/tmp"),
            environ={"DATABASE_URL": "postgres://myuser:mypass@dbhost:5433/mydb"},
        )
        self.assertEqual(
            config,
            {
                "ENGINE": "django.db.backends.postgresql",
                "NAME": "mydb",
                "USER": "myuser",
                "PASSWORD": "mypass",
                "HOST": "dbhost",
                "PORT": "5433",
            },
        )

    def test_postgresql_scheme_also_accepted(self):
        config = build_database_config(
            Path("/tmp"), environ={"DATABASE_URL": "postgresql://u:p@h/db"}
        )
        self.assertEqual(config["ENGINE"], "django.db.backends.postgresql")

    def test_unsupported_scheme_raises(self):
        with self.assertRaises(ImproperlyConfigured):
            build_database_config(Path("/tmp"), environ={"DATABASE_URL": "mysql://u:p@h/db"})

    def test_missing_database_name_raises(self):
        with self.assertRaises(ImproperlyConfigured):
            build_database_config(Path("/tmp"), environ={"DATABASE_URL": "postgres://u:p@h/"})

    def test_missing_host_raises(self):
        with self.assertRaises(ImproperlyConfigured):
            build_database_config(Path("/tmp"), environ={"DATABASE_URL": "postgres:///db"})

    def test_no_real_secret_in_test_fixtures(self):
        # Guard against accidentally committing a real-looking credential in
        # this test file itself.
        config = build_database_config(
            Path("/tmp"), environ={"DATABASE_URL": "postgres://myuser:mypass@dbhost:5433/mydb"}
        )
        self.assertNotIn("prod", config["PASSWORD"].lower())


class ResolveLogLevelTests(SimpleTestCase):
    def test_default_is_info(self):
        self.assertEqual(resolve_log_level(environ={}), "INFO")

    def test_valid_level_uppercased(self):
        self.assertEqual(resolve_log_level(environ={"DJANGO_LOG_LEVEL": "debug"}), "DEBUG")

    def test_invalid_level_raises(self):
        with self.assertRaises(ImproperlyConfigured):
            resolve_log_level(environ={"DJANGO_LOG_LEVEL": "VERBOSE"})
