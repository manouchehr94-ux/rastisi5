from django.contrib import admin

from .models import AuditLogEntry


@admin.register(AuditLogEntry)
class AuditLogEntryAdmin(admin.ModelAdmin):
    """پنل بازرسی فقط‌خواندنی دفتر حسابرسی — نگاه کنید به ADR-36. رخدادها
    فقط از طریق apps.core.services.audit_service.record_audit_event ثبت
    می‌شوند، هرگز مستقیماً از این پنل."""

    list_display = ("action_code", "object_label", "store", "actor", "result", "created_at")
    list_filter = ("result", "action_code", "store")
    search_fields = ("action_code", "object_label", "object_id")
    actions = None

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
