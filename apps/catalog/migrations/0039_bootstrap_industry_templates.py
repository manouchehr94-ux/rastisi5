from django.db import migrations


def bootstrap_industry_templates(apps, schema_editor):
    """Ensure every fresh (or upgraded) database always has the platform's
    catalog of Industry Templates — never zero, never requiring a human to
    remember a manual post-deploy step.

    Root cause of the "no Industry Templates in production" bug: the only
    thing that ever wrote ``IndustryTemplate`` rows was the
    ``seed_industry_templates`` management command — idempotent and
    production-safe, but purely opt-in. ``python manage.py migrate`` is the
    one step every deployment always runs; a plain management command is
    not. A fresh production database that never had someone remember to
    run ``seed_industry_templates`` by hand silently ends up with zero
    Industry Templates, so the onboarding "choose your industry" step has
    nothing to show and falls back to its (otherwise correct) empty state.

    This migration closes that gap by running the exact same idempotent
    command as part of the schema migration itself, so it is applied on
    every deploy and can never silently be skipped. It reuses the live
    ``apps.catalog.industry_templates.registry`` (not historical
    ``apps.get_model`` snapshots) deliberately: the registry is living
    platform content that keeps evolving (new industries, new versions),
    and this bootstrap step's job is "make sure today's registry is
    installed," not "replay a frozen historical snapshot." The command
    itself is fully idempotent (``update_or_create`` keyed on natural keys)
    and wrapped in its own ``transaction.atomic``, so re-running it here on
    every ``migrate`` — including on a database that already has these
    rows — creates no duplicates and is safe to run any number of times.

    The command remains available and documented as
    ``python manage.py seed_industry_templates`` for operators who want to
    re-run it manually (e.g. right after a registry update, without
    waiting for the next migration).
    """
    from django.core.management import call_command

    call_command("seed_industry_templates")


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0038_productmetafield"),
    ]

    operations = [
        migrations.RunPython(bootstrap_industry_templates, migrations.RunPython.noop),
    ]
