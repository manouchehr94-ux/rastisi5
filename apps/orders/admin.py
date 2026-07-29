from django.contrib import admin

from .models import (
    Order,
    OrderItem,
    OrderStatusHistory,
    PaymentGateway,
    Refund,
    RefundItem,
    ReturnItem,
    ReturnRequest,
    ShippingMethod,
    Transaction,
)


@admin.register(ShippingMethod)
class ShippingMethodAdmin(admin.ModelAdmin):
    list_display = ("name", "store", "cost", "free_over", "is_active")
    list_filter = ("store", "is_active")
    prepopulated_fields = {"slug": ("name",)}


@admin.register(PaymentGateway)
class PaymentGatewayAdmin(admin.ModelAdmin):
    list_display = ("name", "store", "fee_percent", "is_active")
    list_filter = ("store", "is_active")
    prepopulated_fields = {"slug": ("name",)}


class ReadOnlyFinancialRecordMixin:
    """هیچ رکورد مالی/تاریخی (Order، اقلام آن، تراکنش، تاریخچه‌ی وضعیت) نباید
    مستقیماً از Django Admin ساخته، ویرایش یا حذف شود — حتی توسط superuser.

    تنها مسیر مجازِ تغییرِ این داده‌ها سرویس‌های
    ``apps.orders.services.order_service``/``payment_service`` هستند
    (``create_order_from_cart``/``change_order_status``/``simulate_payment``)
    که گردش‌کار وضعیت را اعمال و ``OrderStatusHistory`` را حتماً ثبت
    می‌کنند. بدون این override، چون Django به superuser به‌طور پیش‌فرض همه‌ی
    مجوزها را می‌دهد، محدودیت دسترسی Admin (``apps.stores.admin_permissions``
    — فقط superuser فعال) به‌تنهایی از دور زدنِ گردش‌کار وضعیت جلوگیری
    نمی‌کند؛ این mixin همان کاری است که واقعاً جلویش را می‌گیرد.

    ``has_view_permission`` عمداً override نشده — یک superuser هنوز می‌تواند
    برای بازرسی/حسابرسی این رکوردها را ببیند، فقط نمی‌تواند تغییرشان دهد."""

    def has_add_permission(self, request, obj=None):
        # obj=None default: ModelAdmin calls this with just `request`;
        # InlineModelAdmin calls it with (request, obj) — one signature
        # must satisfy both call conventions.
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class OrderItemInline(ReadOnlyFinancialRecordMixin, admin.TabularInline):
    model = OrderItem
    extra = 0


class OrderStatusHistoryInline(ReadOnlyFinancialRecordMixin, admin.TabularInline):
    model = OrderStatusHistory
    extra = 0
    readonly_fields = ("from_status", "to_status", "changed_by", "note", "created_at")


@admin.register(Order)
class OrderAdmin(ReadOnlyFinancialRecordMixin, admin.ModelAdmin):
    list_display = ("code", "store", "customer", "status", "payment_status", "grand_total", "created_at")
    list_filter = ("store", "status", "payment_status", "vendor")
    search_fields = ("code", "customer__full_name")
    inlines = [OrderItemInline, OrderStatusHistoryInline]


@admin.register(Transaction)
class TransactionAdmin(ReadOnlyFinancialRecordMixin, admin.ModelAdmin):
    list_display = ("code", "order", "gateway", "amount", "status", "created_at")
    list_filter = ("status", "gateway")
    search_fields = ("code", "order__code", "ref_id")


@admin.register(OrderItem)
class OrderItemAdmin(ReadOnlyFinancialRecordMixin, admin.ModelAdmin):
    list_display = ("order", "product_name", "sku", "variant_label", "quantity", "unit_price", "line_total")
    search_fields = ("order__code", "product_name", "sku")


@admin.register(OrderStatusHistory)
class OrderStatusHistoryAdmin(ReadOnlyFinancialRecordMixin, admin.ModelAdmin):
    list_display = ("order", "from_status", "to_status", "changed_by", "created_at")
    list_filter = ("to_status",)
    search_fields = ("order__code",)


class RefundItemInline(admin.TabularInline):
    model = RefundItem
    extra = 0
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Refund)
class RefundAdmin(ReadOnlyFinancialRecordMixin, admin.ModelAdmin):
    """نگاه کنید به ADR-33 — استرداد فقط از طریق
    ``apps.orders.services.refund_service`` ساخته/اجرا می‌شود."""

    list_display = ("order", "store", "status", "requested_amount", "approved_amount", "refund_method", "created_at")
    list_filter = ("status", "refund_method", "reason", "store")
    search_fields = ("order__code",)
    inlines = [RefundItemInline]


class ReturnItemInline(admin.TabularInline):
    model = ReturnItem
    extra = 0
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(ReturnRequest)
class ReturnRequestAdmin(ReadOnlyFinancialRecordMixin, admin.ModelAdmin):
    """نگاه کنید به ADR-34 — گردشِ وضعیتِ مرجوعی فقط از طریق
    ``apps.orders.services.return_service`` اعمال می‌شود."""

    list_display = ("return_number", "order", "customer", "status", "reason", "created_at")
    list_filter = ("status", "reason", "store")
    search_fields = ("return_number", "order__code", "customer__full_name")
    inlines = [ReturnItemInline]
