from django.contrib import admin

from .models import Store, StoreDomain, StoreMembership


class StoreDomainInline(admin.TabularInline):
    model = StoreDomain
    extra = 0
    fields = ("hostname", "is_primary", "verification_status", "verified_at")
    readonly_fields = ("verified_at",)


class StoreMembershipInline(admin.TabularInline):
    model = StoreMembership
    extra = 0
    fields = ("user", "role", "status", "invited_by", "accepted_at", "revoked_at")
    readonly_fields = ("invited_at",)


@admin.register(Store)
class StoreAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "status", "public_id", "created_at")
    list_filter = ("status",)
    search_fields = ("name", "slug", "public_id")
    readonly_fields = ("public_id", "created_at", "updated_at")
    inlines = [StoreDomainInline, StoreMembershipInline]


@admin.register(StoreDomain)
class StoreDomainAdmin(admin.ModelAdmin):
    list_display = ("hostname", "store", "is_primary", "verification_status", "verified_at")
    list_filter = ("verification_status", "is_primary")
    search_fields = ("hostname", "store__name")
    # verification_token is deliberately excluded from list_display / search_fields
    # so it is never exposed in a broad, easily-browsable admin list view.
    readonly_fields = ("created_at", "updated_at")


@admin.register(StoreMembership)
class StoreMembershipAdmin(admin.ModelAdmin):
    list_display = ("user", "store", "role", "status", "accepted_at", "revoked_at")
    list_filter = ("role", "status")
    search_fields = ("user__username", "user__email", "store__name")
    readonly_fields = ("invited_at", "created_at", "updated_at")
