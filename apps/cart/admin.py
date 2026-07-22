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
    list_display = ("code", "type", "value", "min_order", "used_count", "usage_limit", "is_active", "expires_at")
    list_filter = ("type", "is_active")
    search_fields = ("code", "label")


@admin.register(CartItem)
class CartItemAdmin(admin.ModelAdmin):
    list_display = ("cart", "product", "variant", "quantity", "unit_price")
    search_fields = ("product__name",)
