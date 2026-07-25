from apps.stores.resolution import resolve_store_for_service

from .models import Category


def nav_categories(request):
    """دسته‌های سطح‌بالای همین Store به‌همراه زیردسته‌ها — برای منوی ناوبری در base.html."""
    store = resolve_store_for_service(request)
    categories = (
        Category.objects.filter(store=store, parent__isnull=True, is_active=True)
        .prefetch_related("children")
        .order_by("order", "name")
    )
    return {"nav_categories": categories}
