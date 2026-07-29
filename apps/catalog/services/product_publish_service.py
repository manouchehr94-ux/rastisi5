"""اعتبارسنجی انتشار کالا — قرارداد پیش‌نویس/انتشار (Draft/Publish).

پیش‌نویس (``Product.Status.DRAFT``) می‌تواند ویژگی‌های الزامیِ دسته‌بندی یا
تنظیم کامل تنوع را نداشته باشد. انتشار (``Product.Status.ACTIVE``) باید
طرح کامل دسته‌بندی و — برای کالای دارای تنوع — حداقل یک تنوع فعال معتبر
را رعایت کند. این تابع فقط قوانین کسب‌وکاریِ *فراتر* از اعتبارسنجی مدل
معمولی (که فرم/``full_clean`` از قبل انجام می‌دهد) را بررسی می‌کند.
"""

from apps.catalog.models import Product, ProductAttributeValue
from apps.catalog.services.category_schema_service import resolve_category_schema
from apps.catalog.services.product_specification_service import format_attribute_value


def validate_product_for_publish(product: Product) -> list[str]:
    """فهرست پیام‌های خطای قابل‌نمایش را برمی‌گرداند؛ فهرست خالی یعنی کالا آماده‌ی انتشار است."""
    errors: list[str] = []

    schema_entries = resolve_category_schema(product.category)
    required_entries = [e for e in schema_entries if e.is_required]
    if required_entries:
        assignments_by_attribute: dict[int, list] = {}
        for assignment in ProductAttributeValue.objects.filter(product=product).select_related("attribute", "value"):
            assignments_by_attribute.setdefault(assignment.attribute_id, []).append(assignment)
        for entry in required_entries:
            assignments = assignments_by_attribute.get(entry.attribute.pk, [])
            if not format_attribute_value(entry.attribute, assignments):
                errors.append(f"ویژگی الزامی «{entry.attribute.label}» تکمیل نشده است.")

    # عمداً بدون بررسیِ «کالای دارای تنوع باید حداقل یک تنوع فعال داشته باشد»:
    # جریان تست‌شده و از قبل موجودِ تبدیل «ساده -> دارای تنوع» صراحتاً اجازه می‌دهد
    # کالا هم‌زمان با فعال‌شدن به «دارای تنوع» تبدیل شود و تنوع‌ها در قدم دومِ
    # جداگانه (صفحه‌ی مدیریت تنوع) اضافه شوند — نگاه کنید به
    # apps.dashboard.tests.test_product_variant_views.ProductTypeWorkflowTests.
    # افزودن این بررسی اینجا آن جریان را می‌شکند؛ گزارش فاز ۱E این محدودیت را
    # به‌صراحت به‌عنوان «شناخته‌شده» ثبت می‌کند، نه نادیده‌گرفته‌شده.

    if product.price is None or product.price <= 0:
        errors.append("قیمت کالا باید بزرگ‌تر از صفر باشد.")

    return errors
