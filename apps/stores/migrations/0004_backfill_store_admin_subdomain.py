"""Backfill ``Store.admin_subdomain`` for any row created before schema
migration 0003 added the field (in practice, just the seeded Akhlaghi row).

Deliberately reimplements the same fallback ``Store._fallback_admin_subdomain``
uses at the Python level, rather than importing the real model (migrations
must never import a runtime model — see
``docs/docs/product/00_PROJECT_MASTER_REFERENCE.md`` §23) or calling
``instance.save()`` (the historical migration model returned by
``apps.get_model`` doesn't have that method).
"""

import re

from django.db import migrations

_LABEL_RE = re.compile(r"^(?!-)[a-z0-9-]{1,63}(?<!-)$")

RESERVED_ADMIN_SUBDOMAINS = frozenset({
    "www", "admin", "api", "app", "static", "media", "mail", "smtp", "ftp",
    "ns1", "ns2", "autodiscover", "rastisi", "dashboard", "panel", "portal",
    "support", "help", "status", "blog", "cdn", "assets", "docs", "shop",
    "store", "stores", "billing", "payments",
})


def _derive_admin_subdomain(store):
    candidate = (store.slug or "").strip().lower()
    if candidate and _LABEL_RE.match(candidate) and candidate not in RESERVED_ADMIN_SUBDOMAINS:
        return candidate
    return f"store-{store.public_id.hex[:12]}"


def backfill_admin_subdomain(apps, schema_editor):
    Store = apps.get_model("stores", "Store")
    for store in Store.objects.filter(admin_subdomain__isnull=True):
        store.admin_subdomain = _derive_admin_subdomain(store)
        store.save(update_fields=["admin_subdomain"])


def clear_admin_subdomain(apps, schema_editor):
    Store = apps.get_model("stores", "Store")
    Store.objects.update(admin_subdomain=None)


class Migration(migrations.Migration):

    dependencies = [
        ("stores", "0003_store_admin_subdomain_schema"),
    ]

    operations = [
        migrations.RunPython(backfill_admin_subdomain, clear_admin_subdomain),
    ]
