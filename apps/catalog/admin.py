from django.contrib import admin

from .models import (
    Brand,
    Category,
    Product,
    ProductImage,
    ProductVariant,
    Review,
    Specification,
    SpecificationTemplate,
    SpecificationTemplateField,
    Vendor,
)


@admin.register(Vendor)
class VendorAdmin(admin.ModelAdmin):
    list_display = ("name", "owner", "is_active", "created_at")
    list_filter = ("is_active",)
    search_fields = ("name", "slug")
    prepopulated_fields = {"slug": ("name",)}


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "parent", "order", "is_active")
    list_filter = ("is_active", "parent")
    search_fields = ("name", "slug")
    prepopulated_fields = {"slug": ("name",)}


@admin.register(Brand)
class BrandAdmin(admin.ModelAdmin):
    list_display = ("name",)
    search_fields = ("name", "slug")
    prepopulated_fields = {"slug": ("name",)}


class ProductImageInline(admin.TabularInline):
    model = ProductImage
    extra = 1


class ProductVariantInline(admin.TabularInline):
    model = ProductVariant
    extra = 1
    fields = ("attribute", "value", "value_hex", "sku", "stock", "extra_price", "is_active", "display_order")


class SpecificationInline(admin.TabularInline):
    model = Specification
    extra = 1


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = (
        "name", "sku", "vendor", "category", "price", "discount_percent",
        "final_price", "stock", "product_type", "status", "tag",
    )
    list_filter = ("status", "product_type", "tag", "category", "vendor")
    search_fields = ("name", "sku", "slug")
    prepopulated_fields = {"slug": ("name",)}
    inlines = [ProductImageInline, ProductVariantInline, SpecificationInline]


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ("product", "customer", "rating", "is_approved", "created_at")
    list_filter = ("is_approved", "rating")
    search_fields = ("product__name", "customer__full_name")


@admin.register(ProductImage)
class ProductImageAdmin(admin.ModelAdmin):
    list_display = ("product", "order", "alt")
    search_fields = ("product__name", "alt")


@admin.register(ProductVariant)
class ProductVariantAdmin(admin.ModelAdmin):
    list_display = ("product", "attribute", "value", "sku", "stock", "extra_price", "is_active", "display_order")
    list_filter = ("attribute", "is_active")
    search_fields = ("product__name", "value", "sku")


class SpecificationTemplateFieldInline(admin.TabularInline):
    model = SpecificationTemplateField
    extra = 1


@admin.register(SpecificationTemplate)
class SpecificationTemplateAdmin(admin.ModelAdmin):
    list_display = ("name", "category")
    list_filter = ("category",)
    search_fields = ("name",)
    inlines = [SpecificationTemplateFieldInline]


@admin.register(Specification)
class SpecificationAdmin(admin.ModelAdmin):
    list_display = ("product", "label", "value", "order")
    search_fields = ("product__name", "label")
