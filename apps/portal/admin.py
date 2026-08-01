"""Django Admin برایِ مدل‌هایِ سطحِ پلتفرمِ ``apps.portal`` — فقط superuser.
``PlatformConfiguration``/``PlatformAuditLogEntry`` تصمیماتِ سراسریِ
پلتفرم‌اند (نه مالِ یک Store)، پس هرگز نباید در Merchant Admin دیده شوند."""

from django.contrib import admin

from .models import PlatformAuditLogEntry, PlatformConfiguration


class SuperuserOnlyAdmin(admin.ModelAdmin):
    def has_module_permission(self, request):
        return bool(request.user and request.user.is_superuser)

    def has_view_permission(self, request, obj=None):
        return bool(request.user and request.user.is_superuser)


@admin.register(PlatformConfiguration)
class PlatformConfigurationAdmin(SuperuserOnlyAdmin):
    """رابطِ اصلیِ ویرایش صفحه‌ی ``portal_platform_admin:configuration``
    است، نه این‌جا — این ثبت فقط یک راهِ پشتیبانِ خواندنی/اضطراری است."""

    list_display = (
        "pk", "default_trial_days", "deletion_retention_days",
        "default_payment_provider", "sms_backend", "updated_at",
    )

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(PlatformAuditLogEntry)
class PlatformAuditLogEntryAdmin(SuperuserOnlyAdmin):
    """تاریخچه‌ی تغییرناپذیر (Section 13) — فقط خواندنی."""

    list_display = ("action_code", "actor", "object_type", "object_label", "result", "created_at")
    list_filter = ("result", "action_code")
    search_fields = ("action_code", "object_type", "object_id", "object_label", "actor__username")
    ordering = ("-created_at",)
    readonly_fields = (
        "actor", "action_code", "object_type", "object_id", "object_label",
        "before_summary", "after_summary", "metadata", "result", "created_at",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
