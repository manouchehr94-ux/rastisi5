from django.shortcuts import get_object_or_404, render

from .models import ContentPage


def page_detail(request, slug):
    """نمایش صفحه‌ی محتوایی منتشرشده."""
    page = get_object_or_404(ContentPage, slug=slug, status=ContentPage.Status.PUBLISHED)
    return render(request, "content/page_detail.html", {"page": page})
