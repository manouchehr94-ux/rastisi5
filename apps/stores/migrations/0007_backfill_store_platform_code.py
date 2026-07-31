"""Backfill ``Store.platform_code`` for any row created before schema
migration 0006 added the field (in practice, just the seeded Akhlaghi row).

Deliberately reimplements the same alphabet/length ``apps.stores.services.
platform_code_service`` uses at the Python level, rather than importing the
real service (migrations must never import runtime app code — see
``docs/docs/product/00_PROJECT_MASTER_REFERENCE.md`` §23).
"""

import secrets

from django.db import migrations

_ALPHABET = "abcdefghjkmnpqrstuvwxyz23456789"
_LENGTH = 9


def _generate_code():
    return "".join(secrets.choice(_ALPHABET) for _ in range(_LENGTH))


def backfill_platform_code(apps, schema_editor):
    Store = apps.get_model("stores", "Store")
    for store in Store.objects.filter(platform_code__isnull=True):
        for _attempt in range(50):
            candidate = _generate_code()
            if not Store.objects.filter(platform_code=candidate).exists():
                store.platform_code = candidate
                store.save(update_fields=["platform_code"])
                break
        else:
            raise RuntimeError(
                f"could not generate a unique platform_code for store id={store.pk} "
                "after 50 attempts"
            )


def clear_platform_code(apps, schema_editor):
    Store = apps.get_model("stores", "Store")
    Store.objects.update(platform_code=None)


class Migration(migrations.Migration):

    dependencies = [
        ("stores", "0006_store_platform_code_schema"),
    ]

    operations = [
        migrations.RunPython(backfill_platform_code, clear_platform_code),
    ]
