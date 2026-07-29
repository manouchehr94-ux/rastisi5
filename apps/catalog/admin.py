from django.contrib import admin

from .models import (
    Brand,
    Category,
    CategoryAttributeSchema,
    CategoryRecommendedOption,
    IndustryTemplate,
    IndustryTemplateAttribute,
    IndustryTemplateAttributeValue,
    IndustryTemplateCategory,
    IndustryTemplateCategoryAttributeMapping,
    IndustryTemplateRecommendedOption,
    Product,
    ProductImage,
    ProductVariant,
    Review,
    Specification,
    SpecificationTemplate,
    SpecificationTemplateField,
    StockMovement,
    StoreIndustryInstallation,
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


# =============================================================================
# قالب‌های صنف پلتفرم (Phase 1E) — نگاه کنید به ADR-22. این مدل‌ها هیچ FK به
# Store ندارند و عمداً فقط از طریق این پنل (superuser) یا دستور مدیریتی
# seed_industry_templates قابل‌نوشتن‌اند — هرگز از مسیر StoreMembership.
# =============================================================================


class IndustryTemplateCategoryInline(admin.TabularInline):
    model = IndustryTemplateCategory
    extra = 0
    fields = ("code", "name", "icon", "parent", "display_order")


class IndustryTemplateAttributeInline(admin.TabularInline):
    model = IndustryTemplateAttribute
    extra = 0
    fields = ("code", "label", "data_type", "is_variant_axis", "display_order")


@admin.register(IndustryTemplate)
class IndustryTemplateAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "version", "is_active", "display_order")
    list_filter = ("is_active",)
    search_fields = ("name", "slug")
    inlines = [IndustryTemplateCategoryInline, IndustryTemplateAttributeInline]


@admin.register(IndustryTemplateCategory)
class IndustryTemplateCategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "industry_template", "parent", "display_order")
    list_filter = ("industry_template",)
    search_fields = ("name", "code")


@admin.register(IndustryTemplateAttribute)
class IndustryTemplateAttributeAdmin(admin.ModelAdmin):
    list_display = ("label", "code", "industry_template", "data_type", "is_variant_axis")
    list_filter = ("industry_template", "data_type", "is_variant_axis")
    search_fields = ("label", "code")


@admin.register(IndustryTemplateAttributeValue)
class IndustryTemplateAttributeValueAdmin(admin.ModelAdmin):
    list_display = ("label", "template_attribute", "display_order")
    list_filter = ("template_attribute__industry_template",)
    search_fields = ("label",)


@admin.register(IndustryTemplateCategoryAttributeMapping)
class IndustryTemplateCategoryAttributeMappingAdmin(admin.ModelAdmin):
    list_display = ("template_category", "template_attribute", "group", "is_required", "display_order")
    list_filter = ("template_category__industry_template", "is_required")


@admin.register(IndustryTemplateRecommendedOption)
class IndustryTemplateRecommendedOptionAdmin(admin.ModelAdmin):
    list_display = ("template_category", "template_attribute", "display_order")
    list_filter = ("template_category__industry_template",)


@admin.register(StoreIndustryInstallation)
class StoreIndustryInstallationAdmin(admin.ModelAdmin):
    """پنل بازرسی نصب قالب صنف — فقط‌خواندنی؛ نصب واقعی فقط از طریق
    install_industry_template انجام می‌شود تا قوانین اتمیک/idempotency
    دور زده نشوند."""

    list_display = ("store", "industry_template", "installed_version", "status", "created_at")
    list_filter = ("status", "industry_template")
    search_fields = ("store__name",)
    actions = None

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(StockMovement)
class StockMovementAdmin(admin.ModelAdmin):
    """پنل بازرسی دفتر موجودی — فقط‌خواندنی؛ هر تغییرِ موجودی فقط از طریق
    apps.catalog.services.inventory_service ثبت می‌شود تا حسابرسی کامل
    (stock_before/stock_after) هرگز دور زده نشود."""

    list_display = ("product", "variant", "reason", "delta", "stock_before", "stock_after", "store", "created_at")
    list_filter = ("reason", "store")
    search_fields = ("product__name", "variant__attribute", "variant__value", "order__code")
    actions = None

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(CategoryAttributeSchema)
class CategoryAttributeSchemaAdmin(StoreLockedOnEditMixin, admin.ModelAdmin):
    list_display = ("category", "attribute", "group", "is_required", "display_order")
    list_filter = ("is_required",)
    search_fields = ("category__name", "attribute__label")


@admin.register(CategoryRecommendedOption)
class CategoryRecommendedOptionAdmin(StoreLockedOnEditMixin, admin.ModelAdmin):
    list_display = ("category", "attribute", "display_order")
    search_fields = ("category__name", "attribute__label")
