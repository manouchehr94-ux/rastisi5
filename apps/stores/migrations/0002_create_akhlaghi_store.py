from django.db import migrations

# Stable, documented seed values for the platform's first Store. Keeping
# these constants in the migration itself (rather than a runtime seeder)
# means the initial Store's identity is part of the reviewable migration
# history, not something that can silently drift between environments.
AKHLAGHI_STORE_SLUG = "akhlaghi"
AKHLAGHI_STORE_NAME = "Akhlaghi"


def create_akhlaghi_store(apps, schema_editor):
    """Idempotently create the initial Akhlaghi Store.

    No StoreDomain is created here: inventing a "production" domain in a
    migration would be a guess, not a fact, and this program explicitly
    prefers creating the Store without one over fabricating a verified
    domain. No StoreMembership is created either: there is no deterministic,
    safe way to pick an Owner here (no ``User.objects.first()``, no
    arbitrary superuser) — Owner membership backfill is deferred to the
    dedicated authorization migration once a real owner user is identified.
    """
    Store = apps.get_model("stores", "Store")
    Store.objects.get_or_create(
        slug=AKHLAGHI_STORE_SLUG,
        defaults={
            "name": AKHLAGHI_STORE_NAME,
            "status": "active",
        },
    )


class Migration(migrations.Migration):

    dependencies = [
        ("stores", "0001_initial"),
    ]

    operations = [
        # Reverse is intentionally migrations.RunPython.noop, not a delete.
        #
        # An earlier version of this migration reversed by deleting the Store
        # row matched by slug. That looked safe in isolation, but
        # StoreDomain/StoreMembership both use on_delete=CASCADE from Store
        # (a domain or membership has no meaning without its Store — see
        # ADR-2/ADR-4 in docs/architecture/SAAS_DOMAIN_DECISIONS.md). Once any
        # later PR attaches real domains, memberships, or — eventually —
        # Store-owned business records to this Store, an "innocuous" reverse
        # of this seed migration would cascade-delete all of it. A seed
        # migration for a live tenant must never be the thing that silently
        # deletes that tenant's dependent data as a side effect of an
        # unrelated rollback elsewhere in the migration graph. Making the
        # reverse a no-op means unapplying this migration only changes
        # Django's recorded migration state; it never deletes the Store or
        # anything the Store owns. Recovering a genuinely-unwanted seed Store
        # is an explicit, manual, reviewed action, not an automatic one.
        migrations.RunPython(create_akhlaghi_store, migrations.RunPython.noop),
    ]
