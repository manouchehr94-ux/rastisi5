# Phase 1A — step F of the owner's required migration sequence: remove the
# direct StorefrontSection.version FK now that every section has been
# safely backfilled onto a page (0008) and `page` is the sole required
# ownership column (0009).
#
# This is the actual schema-level resolution of "do NOT leave two
# long-term competing ownership sources" — `apps/storefront_builder/models.py`
# no longer declares a `version` database field on StorefrontSection at all
# (only `page`); the model exposes `version` purely as a read-only Python
# `@property` (`self.page.version`) plus an `__init__`-level convenience
# shim that accepts `version=` as a constructor kwarg and resolves it to
# the corresponding page — this migration is what makes that model
# declaration match reality in the database.
#
# No compatibility blocker was found that would make this drop unsafe at
# this point in the sequence: every existing row already has a `page_id`
# (guaranteed NOT NULL by 0009), and every production code call site that
# previously read/wrote `.version`/`version=` on StorefrontSection was
# updated in this same commit to go through `.page`/`page=` (or the
# `version` property, for read-only convenience) — see the Phase 1A report
# for the full call-site inventory.

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("storefront_builder", "0009_storefrontsection_page_not_null_and_stable_id_scope"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="storefrontsection",
            name="version",
        ),
    ]
