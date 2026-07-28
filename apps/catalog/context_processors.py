from apps.stores.resolution import StoreResolutionError, resolve_store_for_service

from .models import Category


def nav_categories(request):
    """دسته‌های سطح‌بالای همین Store به‌همراه زیردسته‌ها — برای منوی ناوبری در base.html.

    یک Host ناشناخته/غیرمجاز با بیش از یک Store در دیتابیس باعث
    ``StoreResolutionError`` می‌شود (نگاه کنید به
    ``apps.core.context_processors.shop_settings`` برای شرح کامل) — چون
    این context processor روی هر صفحه از جمله ۴۰۴ اجرا می‌شود، این حالت
    باید به فهرست خالی برسد، نه یک ۵۰۰ جدید."""
    try:
        store = resolve_store_for_service(request)
    except StoreResolutionError:
        return {"nav_categories": Category.objects.none()}
    categories = (
        Category.objects.filter(store=store, parent__isnull=True, is_active=True)
        .prefetch_related("children")
        .order_by("order", "name")
    )
    return {"nav_categories": categories}
