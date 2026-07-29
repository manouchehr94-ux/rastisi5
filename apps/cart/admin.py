from django.contrib import admin

from .models import Cart, CartItem, Coupon


class CartItemInline(admin.TabularInline):
    model = CartItem
    extra = 0


@admin.register(Cart)
class CartAdmin(admin.ModelAdmin):
    list_display = ("id", "customer", "session_key", "created_at")
    search_fields = ("customer__full_name", "session_key")
    inlines = [CartItemInline]


@admin.register(Coupon)
class CouponAdmin(admin.ModelAdmin):
    """نگاه کنید به ADR-32 — ``store`` پس از ایجاد فقط‌خواندنی می‌شود تا
    مالکیتِ کدِ تخفیف از این پنلِ عملیاتی جابه‌جا نشود."""

    list_display = ("code", "store", "type", "value", "min_order", "used_count", "usage_limit", "is_active", "expires_at")
    list_filter = ("type", "is_active", "store")
    search_fields = ("code", "label")

    def get_readonly_fields(self, request, obj=None):
        if obj is None:
            return ()
        return ("store",)


@admin.register(CartItem)
class CartItemAdmin(admin.ModelAdmin):
    list_display = ("cart", "product", "variant", "quantity", "unit_price")
    search_fields = ("product__name",)
