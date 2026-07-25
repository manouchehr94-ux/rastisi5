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


def remove_akhlaghi_store(apps, schema_editor):
    """Reverse: remove only the specific Store row this migration created.

    This never touches Users or any other business data — it deletes at
    most one row, matched by the exact slug this migration is responsible
    for. If memberships or domains were later attached to this Store by a
    subsequent migration/PR, the FK ``on_delete=CASCADE`` means reversing
    this migration also removes those — which is expected, since a
    membership/domain has no meaning without its Store.
    """
    Store = apps.get_model("stores", "Store")
    Store.objects.filter(slug=AKHLAGHI_STORE_SLUG).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("stores", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(create_akhlaghi_store, remove_akhlaghi_store),
    ]
