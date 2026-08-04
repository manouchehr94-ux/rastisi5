from django import template
from django.utils.safestring import mark_safe

register = template.Library()


@register.filter
def section_label(section_key):
    """برچسب فارسیِ یک section_key از Section Registry — «؟» برای کلید
    ناشناخته (هرگز crash نمی‌کند)."""
    from ..section_registry import UnknownSectionTypeError, get_definition

    try:
        return get_definition(section_key).label_fa
    except UnknownSectionTypeError:
        return f"نوع ناشناخته ({section_key})"


@register.filter
def sanitize_rich_text(value):
    """پاک‌سازی allowlist محتوای بخش rich_text — همان ساینیتایزر توضیحات
    کالا (``apps.catalog.services.html_sanitizer``)، امن برای رندر مستقیم."""
    from apps.catalog.services.html_sanitizer import sanitize_product_description

    return mark_safe(sanitize_product_description(value or ""))
