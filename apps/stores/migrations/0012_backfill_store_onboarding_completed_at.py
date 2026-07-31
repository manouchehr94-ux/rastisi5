"""Backfills ``Store.onboarding_completed_at`` for any row that predates
this field (in practice, the seeded Akhlaghi row, plus any Store created
before this migration in a real deployment). Treats every pre-existing
Store as already onboarded — this field only ever starts NULL for a
brand-new Store created through ``apps.portal.services.provisioning_
service.provision_trial_store`` going forward; retroactively marking
existing merchants' Stores as "still onboarding" would incorrectly
restrict their live storefronts (Section 6/ADR-103).
"""

from django.db import migrations, models


def backfill_onboarding_completed_at(apps, schema_editor):
    Store = apps.get_model("stores", "Store")
    Store.objects.filter(onboarding_completed_at__isnull=True).update(
        onboarding_completed_at=models.F("created_at")
    )


def clear_onboarding_completed_at(apps, schema_editor):
    Store = apps.get_model("stores", "Store")
    Store.objects.update(onboarding_completed_at=None)


class Migration(migrations.Migration):

    dependencies = [
        ("stores", "0011_store_onboarding_completed_at"),
    ]

    operations = [
        migrations.RunPython(backfill_onboarding_completed_at, clear_onboarding_completed_at),
    ]
