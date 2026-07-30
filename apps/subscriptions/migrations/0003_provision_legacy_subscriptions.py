"""مهاجرتِ داده‌ای: پلنِ legacyِ پنهان + نسخه‌ی منتشرشده + Entitlementهایِ
نامحدود + اشتراکِ فعالِ legacy برایِ هر Store موجود — نگاه کنید به ADR-65.

idempotent است (منطق در ``legacy_service.provision_legacy``). معکوسِ آن
عمداً no-op است: حذفِ خودکارِ اشتراک‌ها/پلنِ legacy می‌تواند فروشگاه‌هایِ
موجود را بی‌صدا محدود کند، پس reverse فقط رکوردها را دست‌نخورده می‌گذارد
(اگر لازم شد، حذف باید صریح و دستی باشد)."""

from django.db import migrations
from django.utils import timezone


def forwards(apps, schema_editor):
    from apps.subscriptions.services.legacy_service import provision_legacy

    provision_legacy(
        Plan=apps.get_model("subscriptions", "Plan"),
        PlanVersion=apps.get_model("subscriptions", "PlanVersion"),
        EntitlementDefinition=apps.get_model("subscriptions", "EntitlementDefinition"),
        PlanEntitlement=apps.get_model("subscriptions", "PlanEntitlement"),
        StoreSubscription=apps.get_model("subscriptions", "StoreSubscription"),
        Store=apps.get_model("stores", "Store"),
        now=timezone.now(),
    )


def backwards(apps, schema_editor):
    # عمداً no-op — نگاه کنید به docstring و ADR-65.
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("subscriptions", "0002_storesubscription_subscriptionevent_usagerecord_and_more"),
        ("stores", "0005_store_admin_subdomain_enforce_not_null"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
