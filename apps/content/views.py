from django.shortcuts import get_object_or_404, render

from apps.stores.resolution import resolve_store_for_storefront

from .models import ContentPage


def page_detail(request, slug):
    """نمایش صفحه‌ی محتوایی منتشرشده — مقیّد به فروشگاه جاری."""
    store = resolve_store_for_storefront(request)
    page = get_object_or_404(
        ContentPage, slug=slug, status=ContentPage.Status.PUBLISHED, store=store,
    )
    return render(request, "content/page_detail.html", {"page": page})
