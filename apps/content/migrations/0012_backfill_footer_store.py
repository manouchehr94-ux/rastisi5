from django.db import migrations

AKHLAGHI_SLUG = "akhlaghi"


def _get_akhlaghi_or_fail(Store):
    """Resolve the Akhlaghi Store by its stable slug — never `.first()`,
    never a hard-coded primary key. Fails loudly if Akhlaghi is missing or
    duplicated; never silently creates a second Akhlaghi Store."""
    try:
        return Store.objects.get(slug=AKHLAGHI_SLUG)
    except Store.DoesNotExist:
        raise RuntimeError(
            "Cannot backfill footer models' store: no Store with slug "
            f"{AKHLAGHI_SLUG!r} exists. The stores.0002_create_akhlaghi_store "
            "migration must run before this one."
        )
    except Store.MultipleObjectsReturned:
        raise RuntimeError(
            "Cannot backfill footer models' store: more than one Store "
            f"with slug {AKHLAGHI_SLUG!r} exists. Refusing to guess which "
            "one is authoritative."
        )


def backfill_footer_store(apps, schema_editor):
    Store = apps.get_model("stores", "Store")
    FooterSettings = apps.get_model("content", "FooterSettings")
    FooterTrustBadge = apps.get_model("content", "FooterTrustBadge")
    FooterPaymentLogo = apps.get_model("content", "FooterPaymentLogo")

    akhlaghi = _get_akhlaghi_or_fail(Store)

    # FooterSettings: same singleton-until-now shape as ShopSettings — at
    # most one unowned row is possible, since save() always forced pk=1.
    unowned_settings = FooterSettings.objects.filter(store__isnull=True)
    unowned_settings_count = unowned_settings.count()
    if unowned_settings_count > 1:
        raise RuntimeError(
            f"Cannot backfill FooterSettings.store: found {unowned_settings_count} "
            "unowned rows, expected at most 1."
        )
    if unowned_settings_count == 1:
        unowned_settings.update(store=akhlaghi)
    else:
        # No legacy row exists yet (fresh database). FooterSettings has no
        # settings.py-derived bootstrap values (unlike ShopSettings) — every
        # field already has a model-level default, so a bare create() is
        # equivalent to the old get_or_create(pk=1) behavior.
        FooterSettings.objects.create(store=akhlaghi)

    # FooterTrustBadge / FooterPaymentLogo are not singletons — assign every
    # currently-unowned row to Akhlaghi (the only tenant that could have
    # created any of them so far). No "fresh database" branch is needed:
    # zero existing rows means nothing to backfill.
    FooterTrustBadge.objects.filter(store__isnull=True).update(store=akhlaghi)
    FooterPaymentLogo.objects.filter(store__isnull=True).update(store=akhlaghi)


def unlink_footer_store(apps, schema_editor):
    """Reverse: clear the store references only. Never deletes real
    merchant configuration/media rows."""
    Store = apps.get_model("stores", "Store")
    FooterSettings = apps.get_model("content", "FooterSettings")
    FooterTrustBadge = apps.get_model("content", "FooterTrustBadge")
    FooterPaymentLogo = apps.get_model("content", "FooterPaymentLogo")
    try:
        akhlaghi = Store.objects.get(slug=AKHLAGHI_SLUG)
    except Store.DoesNotExist:
        return
    FooterSettings.objects.filter(store=akhlaghi).update(store=None)
    FooterTrustBadge.objects.filter(store=akhlaghi).update(store=None)
    FooterPaymentLogo.objects.filter(store=akhlaghi).update(store=None)


class Migration(migrations.Migration):

    dependencies = [
        ("content", "0011_store_scope_settings_schema"),
    ]

    operations = [
        migrations.RunPython(backfill_footer_store, unlink_footer_store),
    ]
