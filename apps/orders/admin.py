from django.contrib import admin

from .models import Order, OrderItem, OrderStatusHistory, PaymentGateway, ShippingMethod, Transaction


@admin.register(ShippingMethod)
class ShippingMethodAdmin(admin.ModelAdmin):
    list_display = ("name", "cost", "free_over", "is_active")
    list_filter = ("is_active",)
    prepopulated_fields = {"slug": ("name",)}


@admin.register(PaymentGateway)
class PaymentGatewayAdmin(admin.ModelAdmin):
    list_display = ("name", "fee_percent", "is_active")
    list_filter = ("is_active",)
    prepopulated_fields = {"slug": ("name",)}


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0


class OrderStatusHistoryInline(admin.TabularInline):
    model = OrderStatusHistory
    extra = 0
    readonly_fields = ("from_status", "to_status", "changed_by", "note", "created_at")


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ("code", "customer", "status", "payment_status", "grand_total", "created_at")
    list_filter = ("status", "payment_status", "vendor")
    search_fields = ("code", "customer__full_name")
    inlines = [OrderItemInline, OrderStatusHistoryInline]


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = ("code", "order", "gateway", "amount", "status", "created_at")
    list_filter = ("status", "gateway")
    search_fields = ("code", "order__code", "ref_id")


@admin.register(OrderItem)
class OrderItemAdmin(admin.ModelAdmin):
    list_display = ("order", "product_name", "quantity", "unit_price", "line_total")
    search_fields = ("order__code", "product_name")


@admin.register(OrderStatusHistory)
class OrderStatusHistoryAdmin(admin.ModelAdmin):
    list_display = ("order", "from_status", "to_status", "changed_by", "created_at")
    list_filter = ("to_status",)
    search_fields = ("order__code",)
