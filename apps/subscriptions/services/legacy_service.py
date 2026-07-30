"""مهاجرتِ legacy — نگاه کنید به ADR-65.

منطقِ ساختِ «پلنِ legacyِ پنهان» + نسخه‌ی منتشرشده‌ی legacy با دسترسیِ
نامحدود، و اشتراکِ فعالِ legacy برایِ هر Store موجود، این‌جا در یک تابعِ
واحد متمرکز شده تا هم *data migration* (با مدل‌هایِ تاریخیِ ``apps.get_model``)
و هم فرمانِ ``provision_legacy_subscriptions`` (با مدل‌هایِ واقعی) از همان
منطق استفاده کنند — بدونِ دو نسخه‌ی موازی.

همه‌چیز idempotent است: اجرایِ دوباره هیچ ردیفِ تکراری نمی‌سازد و هیچ
Storeِ موجود را محدود نمی‌کند."""

LEGACY_PLAN_CODE = "legacy"


def _entitlement_definitions():
    from apps.subscriptions.entitlements import ENTITLEMENT_DEFINITIONS

    return ENTITLEMENT_DEFINITIONS


def provision_legacy(*, Plan, PlanVersion, EntitlementDefinition, PlanEntitlement,
                     StoreSubscription, Store, now):
    """پلن/نسخه/Entitlement/اشتراک‌هایِ legacy را idempotent می‌سازد.

    خروجی: دیکشنریِ شمارشِ آنچه ساخته شد (برایِ گزارشِ فرمان/تست)."""
    counts = {"plan": 0, "version": 0, "entitlements": 0, "subscriptions": 0}

    plan, created = Plan.objects.get_or_create(
        code=LEGACY_PLAN_CODE,
        defaults={
            "name": "Legacy (پیش از اشتراک)",
            "public_title": "",
            "description": "پلنِ پنهانِ مهاجرت — فروشگاه‌هایِ موجود پیش از معرفیِ اشتراک. عمومی نیست.",
            "is_active": True,
            "is_publicly_selectable": False,
            "is_recommended": False,
            "display_order": 9999,
        },
    )
    counts["plan"] = int(created)

    version, v_created = PlanVersion.objects.get_or_create(
        plan=plan, version_number=1,
        defaults={
            "status": "published",
            "billing_interval": "none",
            "display_price": 0,
            "trial_days": 0,
            "grace_period_days": 0,
            "public_description_snapshot": "دسترسیِ کاملِ legacy (نامحدود).",
            "published_at": now,
            "effective_from": now,
        },
    )
    counts["version"] = int(v_created)

    if version.status != "published":
        version.status = "published"
        version.published_at = version.published_at or now
        version.effective_from = version.effective_from or now
        version.save()

    for key, _name, etype, _default in _entitlement_definitions():
        definition, _d = EntitlementDefinition.objects.get_or_create(
            key=key,
            defaults={"name": _name, "entitlement_type": etype, "default_enabled": _default, "is_active": True},
        )
        is_limit = definition.entitlement_type in ("integer_limit", "decimal_limit")
        _pe, pe_created = PlanEntitlement.objects.get_or_create(
            plan_version=version, entitlement=definition,
            defaults={
                "is_enabled": True,
                "is_unlimited": bool(is_limit),
                "integer_limit": None,
                "decimal_limit": None,
                "text_value": "",
            },
        )
        counts["entitlements"] += int(pe_created)

    for store in Store.objects.all().iterator(chunk_size=200):
        if StoreSubscription.objects.filter(store=store, is_current=True).exists():
            continue
        StoreSubscription.objects.create(
            store=store, plan_version=version, status="active", is_current=True,
            start_at=now, current_period_start=now, source="legacy",
        )
        counts["subscriptions"] += 1

    return counts


def provision_legacy_real(*, now=None):
    """همان ``provision_legacy`` امّا با مدل‌هایِ واقعی — نقطه‌ی ورودِ فرمانِ
    ``provision_legacy_subscriptions`` (data migration از ``apps.get_model``
    استفاده می‌کند). idempotent."""
    from django.utils import timezone

    from apps.stores.models import Store
    from apps.subscriptions.models import (
        EntitlementDefinition,
        Plan,
        PlanEntitlement,
        PlanVersion,
        StoreSubscription,
    )

    return provision_legacy(
        Plan=Plan, PlanVersion=PlanVersion, EntitlementDefinition=EntitlementDefinition,
        PlanEntitlement=PlanEntitlement, StoreSubscription=StoreSubscription, Store=Store,
        now=now or timezone.now(),
    )
