from .models import ContentPage


def footer_pages(request):
    """صفحات محتوایی منتشرشده که باید در فوتر نمایش داده شوند."""
    pages = ContentPage.objects.filter(
        status=ContentPage.Status.PUBLISHED, show_in_footer=True
    ).only("title", "slug", "footer_column").order_by("display_order", "title")

    quick_access = [p for p in pages if p.footer_column == ContentPage.FooterColumn.QUICK_ACCESS]
    customer_service = [p for p in pages if p.footer_column == ContentPage.FooterColumn.CUSTOMER_SERVICE]

    return {
        "footer_pages_quick_access": quick_access,
        "footer_pages_customer_service": customer_service,
    }
