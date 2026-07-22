from django import template

register = template.Library()


@register.filter
def star_rating(value):
    """امتیاز عددی (۰ تا ۵) را به رشته‌ی ستاره تبدیل می‌کند، مثل ★★★★☆."""
    try:
        rounded = round(float(value))
    except (TypeError, ValueError):
        rounded = 0
    rounded = max(0, min(5, rounded))
    return "★" * rounded + "☆" * (5 - rounded)
