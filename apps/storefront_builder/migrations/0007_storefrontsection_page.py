# Phase 1A — step C of the owner's required migration sequence: add
# StorefrontSection.page as NULLABLE (not yet required, not yet the sole
# ownership source). The old `version` FK is left completely untouched by
# this migration — both fields coexist temporarily so the data backfill in
# 0008 has something to write into without any existing row becoming
# unreadable partway through the migration sequence.

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("storefront_builder", "0006_ensure_pages_for_existing_versions"),
    ]

    operations = [
        migrations.AddField(
            model_name="storefrontsection",
            name="page",
            # Deliberately no default= (same discipline as the Phase 0.5
            # stable_id repair) — every existing row must land on a
            # genuine NULL here so the backfill migration (0008) is the
            # only thing that ever assigns it, guaranteeing every section
            # ends up pointed at the correct page rather than risking any
            # SQLite table-rebuild default-leak behavior.
            field=models.ForeignKey(
                null=True, blank=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="sections", to="storefront_builder.storefrontpage",
                verbose_name="صفحه",
            ),
        ),
    ]
