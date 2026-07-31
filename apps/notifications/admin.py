from django.contrib import admin

from .models import NotificationOutbox


@admin.register(NotificationOutbox)
class NotificationOutboxAdmin(admin.ModelAdmin):
    list_display = ("channel", "recipient_user", "recipient_phone", "status", "is_security", "created_at")
    list_filter = ("channel", "status", "is_security")
    search_fields = ("recipient_user__username", "recipient_phone", "recipient_email", "subject")
    readonly_fields = (
        "channel", "recipient_user", "recipient_phone", "recipient_email", "store", "subject", "body",
        "is_security", "attempts", "last_error", "sent_at", "metadata", "created_at", "updated_at",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
