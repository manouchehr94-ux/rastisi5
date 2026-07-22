from django.contrib import admin

from .models import Address, Customer, Wishlist


class AddressInline(admin.TabularInline):
    model = Address
    extra = 0


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ("full_name", "phone", "city", "is_vip", "orders_count", "total_spent")
    list_filter = ("is_vip", "city")
    search_fields = ("full_name", "phone", "email")
    inlines = [AddressInline]


@admin.register(Address)
class AddressAdmin(admin.ModelAdmin):
    list_display = ("receiver_name", "customer", "city", "is_default")
    list_filter = ("province", "is_default")
    search_fields = ("receiver_name", "phone", "full_address")


@admin.register(Wishlist)
class WishlistAdmin(admin.ModelAdmin):
    list_display = ("customer", "product", "created_at")
    search_fields = ("customer__full_name", "product__name")
