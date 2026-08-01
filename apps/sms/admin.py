"""Django Admin برای مدل‌های سطحِ پلتفرمِ اعتبار/بسته‌ی پیامک — فقط
superuser (SmsTemplate/SmsLog/SmsOutboxItem/OtpCode عمداً اینجا ثبت
نمی‌شوند؛ آن‌ها Store-scoped و از مسیرِ پنلِ مدیریتِ همان Store دیده
می‌شوند، نه Django Admin)."""

from django.contrib import admin, messages

from .models import SmsBalance, SmsPackage, SmsPackagePurchase
from .services.balance_service import PurchaseNotPendingError, complete_purchase


class SuperuserOnlySmsAdmin(admin.ModelAdmin):
    def has_module_permission(self, request):
        return bool(request.user and request.user.is_superuser)

    def has_view_permission(self, request, obj=None):
        return bool(request.user and request.user.is_superuser)


@admin.register(SmsPackage)
class SmsPackageAdmin(SuperuserOnlySmsAdmin):
    list_display = ("name", "credit_amount", "price", "is_active", "display_order")
    list_editable = ("is_active", "display_order")

    def has_add_permission(self, request):
        return bool(request.user and request.user.is_superuser)

    def has_change_permission(self, request, obj=None):
        return bool(request.user and request.user.is_superuser)

    def has_delete_permission(self, request, obj=None):
        return bool(request.user and request.user.is_superuser)


@admin.register(SmsBalance)
class SmsBalanceAdmin(SuperuserOnlySmsAdmin):
    """فقط خواندنی — تغییرِ اعتبار همیشه از مسیرِ تکمیلِ خرید یا کسرِ ارسال
    انجام می‌شود، نه ویرایشِ دستیِ این عدد."""

    list_display = ("store", "credits", "updated_at")
    search_fields = ("store__name", "store__slug")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(SmsPackagePurchase)
class SmsPackagePurchaseAdmin(SuperuserOnlySmsAdmin):
    list_display = ("store", "package", "credit_amount", "price", "status", "created_at", "completed_at")
    list_filter = ("status",)
    search_fields = ("store__name", "store__slug")
    actions = ["mark_completed"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    @admin.action(description="تکمیلِ خریدهایِ انتخاب‌شده (افزودنِ اعتبار)")
    def mark_completed(self, request, queryset):
        completed = 0
        for purchase in queryset:
            try:
                complete_purchase(purchase=purchase)
            except PurchaseNotPendingError:
                continue
            completed += 1
        self.message_user(request, f"{completed} خرید تکمیل و اعتبار افزوده شد.", messages.SUCCESS)
