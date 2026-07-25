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


class StoreLockedOnEditMixin:
    """پس از ایجاد رکورد، فیلد «فروشگاه» فقط-خواندنی می‌شود تا مالکیت Store از
    طریق این پنل عملیاتی (که خودِ ADR-8 بازرسی/عملیات پلتفرم است، نه محل
    اجرای قواعد چندمستأجری) جابه‌جا نشود؛ هنگام ایجاد رکورد جدید همچنان
    باید صراحتاً انتخاب شود.
    """

    def get_readonly_fields(self, request, obj=None):
        if obj is None:
            return self.readonly_fields
        return (*self.readonly_fields, "store")


@admin.register(Vendor)
class VendorAdmin(StoreLockedOnEditMixin, admin.ModelAdmin):
    list_display = ("name", "store", "owner", "is_active", "created_at")
    list_filter = ("is_active", "store")
    search_fields = ("name", "slug")
    prepopulated_fields = {"slug": ("name",)}


@admin.register(Category)
class CategoryAdmin(StoreLockedOnEditMixin, admin.ModelAdmin):
    list_display = ("name", "store", "parent", "order", "is_active")
    list_filter = ("is_active", "store", "parent")
    search_fields = ("name", "slug")
    prepopulated_fields = {"slug": ("name",)}


@admin.register(Brand)
class BrandAdmin(StoreLockedOnEditMixin, admin.ModelAdmin):
    list_display = ("name", "store")
    list_filter = ("store",)
    search_fields = ("name", "slug")
    prepopulated_fields = {"slug": ("name",)}


class ProductImageInline(admin.TabularInline):
    model = ProductImage
    extra = 1


class ProductVariantInline(admin.TabularInline):
    """نمایش فقط-خواندنی تنوع‌های کالا در پنل Django Admin.

    مدیریت واقعی (ایجاد/ویرایش/حذف) تنوع باید از طریق پنل مدیریت اختصاصی
    فروشگاه (apps.dashboard) و apps.catalog.services.variant_service انجام
    شود، نه این پنل — چون این‌جا قواعد سرویس (یکتایی، حذف امن تنوع فروخته‌شده
    و...) اعمال نمی‌شود. این این‌لاین فقط برای بازرسی/پشتیبانی نگه داشته شده.
    """

    model = ProductVariant
    extra = 0
    can_delete = False
    fields = ("attribute", "value", "value_hex", "sku", "stock", "extra_price", "is_active", "display_order")

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class SpecificationInline(admin.TabularInline):
    model = Specification
    extra = 1


@admin.register(Product)
class ProductAdmin(StoreLockedOnEditMixin, admin.ModelAdmin):
    list_display = (
        "name", "store", "sku", "vendor", "category", "price", "discount_percent",
        "final_price", "stock", "product_type", "status", "tag",
    )
    list_filter = ("status", "product_type", "tag", "store", "category", "vendor")
    search_fields = ("name", "sku", "slug")
    prepopulated_fields = {"slug": ("name",)}
    # نوع کالا (ساده/دارای تنوع) فقط از طریق apps.catalog.services.variant_service.set_product_type
    # قابل تغییر است، چون این تغییر باید با وضعیت تنوع‌های کالا هماهنگ بماند؛
    # این‌جا فقط برای بازرسی نمایش داده می‌شود.
    readonly_fields = ("product_type",)
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
    """پنل بازرسی فقط-خواندنی تنوع کالا — برای پشتیبانی/دیباگ.

    ایجاد/ویرایش/حذف عمداً غیرفعال است: این مسیر قواعد سرویس (یکتایی مقدار،
    ممنوعیت حذف تنوعِ استفاده‌شده در سفارش و...) را اجرا نمی‌کند. عملیات‌های
    واقعی باید از apps.catalog.services.variant_service (و در آینده پنل
    مدیریت اختصاصی) انجام شوند.
    """

    list_display = ("product", "attribute", "value", "sku", "stock", "extra_price", "is_active", "display_order")
    list_filter = ("attribute", "is_active")
    search_fields = ("product__name", "value", "sku")
    actions = None

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


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
