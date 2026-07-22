from .models import Category


def nav_categories(request):
    """دسته‌های سطح‌بالا به‌همراه زیردسته‌ها — برای منوی ناوبری در base.html."""
    categories = (
        Category.objects.filter(parent__isnull=True, is_active=True)
        .prefetch_related("children")
        .order_by("order", "name")
    )
    return {"nav_categories": categories}
