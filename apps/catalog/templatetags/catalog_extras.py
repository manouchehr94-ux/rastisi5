from django import template
from django.utils.safestring import mark_safe

register = template.Library()


@register.filter
def product_description_html(value):
    """توضیحاتِ کالا را برایِ نمایش آماده می‌کند — پاک‌سازیِ allowlist و امنِ
    رندرِ مستقیم؛ نگاه کنید به apps.catalog.services.html_sanitizer."""
    from apps.catalog.services.html_sanitizer import render_description_html

    return mark_safe(render_description_html(value))


@register.filter
def star_rating(value):
    """امتیاز عددی (۰ تا ۵) را به رشته‌ی ستاره تبدیل می‌کند، مثل ★★★★☆."""
    try:
        rounded = round(float(value))
    except (TypeError, ValueError):
        rounded = 0
    rounded = max(0, min(5, rounded))
    return "★" * rounded + "☆" * (5 - rounded)
