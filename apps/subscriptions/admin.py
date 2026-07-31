"""Django Admin پلتفرمی برایِ دامنه‌ی اشتراک — فقط superuser. نگاه کنید به
ADR-63 (تغییرناپذیریِ نسخه‌ی منتشرشده، سمتِ سرور اجرا می‌شود، نه فقط UI).

هیچ‌کدام از این ثبت‌ها در Merchant Admin دیده نمی‌شوند — این‌ها فقط در
Django Admin (``/admin/``) هستند که خودش به superuser محدود شده است."""

from django.contrib import admin

from apps.subscriptions.models import (
    EntitlementDefinition,
    Plan,
    PlanEntitlement,
    PlanVersion,
    StoreSubscription,
    SubscriptionEvent,
    UsageRecord,
)


class SuperuserOnlyAdmin(admin.ModelAdmin):
    """پایه‌ی ثبت‌هایِ دامنه‌ی اشتراک — فقط superuser، حتی اگر یک کاربرِ
    ``is_staff`` مجوزِ مدلی داشته باشد. اشتراک/رخداد/مصرف داده‌ی حساسِ بین‌
    فروشگاهی‌اند و هرگز نباید در دسترسِ مرچنت باشند."""

    def has_module_permission(self, request):
        return bool(request.user and request.user.is_superuser)

    def has_view_permission(self, request, obj=None):
        return bool(request.user and request.user.is_superuser)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return bool(request.user and request.user.is_superuser)

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Plan)
class PlanAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "public_title", "is_active", "is_publicly_selectable", "is_recommended", "display_order")
    list_filter = ("is_active", "is_publicly_selectable", "is_recommended")
    search_fields = ("code", "name", "public_title")
    ordering = ("display_order", "code")

    def get_readonly_fields(self, request, obj=None):
        # ``code`` پس از ساخت تغییرناپذیر است (ADR-63) — کدِ پلن نباید عوض
        # شود چون اشتراک‌ها/کد از آن استفاده می‌کنند.
        if obj is not None:
            return ("code",)
        return ()


@admin.register(EntitlementDefinition)
class EntitlementDefinitionAdmin(admin.ModelAdmin):
    list_display = ("key", "name", "entitlement_type", "default_enabled", "is_active")
    list_filter = ("entitlement_type", "is_active", "default_enabled")
    search_fields = ("key", "name")
    ordering = ("key",)

    def get_readonly_fields(self, request, obj=None):
        if obj is not None:
            return ("key", "entitlement_type")
        return ()


class PlanEntitlementInline(admin.TabularInline):
    model = PlanEntitlement
    extra = 0
    autocomplete_fields = ("entitlement",)

    def has_change_permission(self, request, obj=None):
        # نسخه‌ی منتشرشده تغییرناپذیر است — Entitlementهایش قابلِ ویرایش نیست.
        if obj is not None and obj.status != PlanVersion.Status.DRAFT:
            return False
        return super().has_change_permission(request, obj)

    def has_add_permission(self, request, obj=None):
        if obj is not None and obj.status != PlanVersion.Status.DRAFT:
            return False
        return super().has_add_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        if obj is not None and obj.status != PlanVersion.Status.DRAFT:
            return False
        return super().has_delete_permission(request, obj)


@admin.register(PlanVersion)
class PlanVersionAdmin(admin.ModelAdmin):
    list_display = ("plan", "version_number", "status", "billing_interval", "display_price", "trial_days", "published_at")
    list_filter = ("status", "billing_interval", "plan")
    search_fields = ("plan__code", "plan__name")
    ordering = ("plan", "-version_number")
    inlines = [PlanEntitlementInline]

    _IMMUTABLE_FIELDS = (
        "plan", "version_number", "currency", "billing_interval", "display_price",
        "trial_days", "grace_period_days", "public_description_snapshot",
    )

    def get_readonly_fields(self, request, obj=None):
        # پس از انتشار، شرایطِ تاریخیِ نسخه سمتِ سرور قفل می‌شوند (ADR-63) —
        # نه فقط در تمپلیتِ Admin، بلکه در خودِ ModelAdmin.
        if obj is not None and obj.status != PlanVersion.Status.DRAFT:
            return ("status", "published_at", "retired_at", *self._IMMUTABLE_FIELDS)
        return ("published_at", "retired_at")

    def has_delete_permission(self, request, obj=None):
        # نسخه‌ی منتشرشده/بازنشسته را نمی‌توان حذف کرد (اشتراک‌هایِ تاریخی به
        # آن ارجاع می‌دهند؛ PROTECT هم در سطحِ DB این را می‌گیرد).
        if obj is not None and obj.status != PlanVersion.Status.DRAFT:
            return False
        return super().has_delete_permission(request, obj)


@admin.register(PlanEntitlement)
class PlanEntitlementAdmin(admin.ModelAdmin):
    list_display = ("plan_version", "entitlement", "is_enabled", "is_unlimited", "integer_limit", "decimal_limit")
    list_filter = ("is_enabled", "is_unlimited", "entitlement")
    search_fields = ("plan_version__plan__code", "entitlement__key")

    def has_change_permission(self, request, obj=None):
        if obj is not None and obj.plan_version.status != PlanVersion.Status.DRAFT:
            return False
        return super().has_change_permission(request, obj)


@admin.register(StoreSubscription)
class StoreSubscriptionAdmin(SuperuserOnlyAdmin):
    list_display = ("store", "plan_version", "status", "is_current", "source", "current_period_end", "created_at")
    list_filter = ("status", "is_current", "source")
    search_fields = ("store__slug", "store__name", "plan_version__plan__code", "external_reference")
    ordering = ("-created_at",)
    # وضعیت هرگز نباید مستقیم از Admin ویرایش شود — فقط ماشینِ حالت
    # (subscription_service) اجازه‌ی تغییرِ وضعیت دارد (ADR-66). فیلدهایِ
    # مشتق/زمانی همه read-only می‌مانند.
    readonly_fields = (
        "store", "plan_version", "status", "is_current", "source",
        "start_at", "trial_start_at", "trial_end_at",
        "current_period_start", "current_period_end", "grace_period_end",
        "cancel_at_period_end", "cancelled_at", "suspended_at", "expired_at",
        "external_reference", "created_at", "updated_at",
    )


@admin.register(SubscriptionEvent)
class SubscriptionEventAdmin(SuperuserOnlyAdmin):
    list_display = ("store", "subscription", "event_type", "from_status", "to_status", "actor", "created_at")
    list_filter = ("event_type",)
    search_fields = ("store__slug", "subscription__id", "idempotency_key")
    ordering = ("-created_at",)
    # تاریخچه‌ی تغییرناپذیر (ADR-71) — فقط خواندنی، هرگز قابلِ ویرایش.
    def has_change_permission(self, request, obj=None):
        return False


@admin.register(UsageRecord)
class UsageRecordAdmin(SuperuserOnlyAdmin):
    list_display = ("store", "metric_key", "used_quantity", "period_start", "period_end")
    list_filter = ("metric_key",)
    search_fields = ("store__slug", "metric_key")
    ordering = ("-period_start",)
    # شمارنده‌ها سیستم‌محورند (usage_service) — ویرایشِ دستی مجاز نیست.
    def has_change_permission(self, request, obj=None):
        return False
